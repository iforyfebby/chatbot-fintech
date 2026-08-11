import os
import pickle
import re
import sys
import warnings
 
import pandas as pd
import streamlit as st
from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_community.embeddings.sentence_transformer import (
    SentenceTransformerEmbeddings,
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
 
warnings.filterwarnings("ignore")

# PENGATURAN
try:
    os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    os.environ.setdefault("ANTHROPIC_API_KEY", "<API_KEY>")
 
FOLDER_DB = "vector_db"
BERKAS_POTONGAN = "potongan_teks.pkl"
MODEL_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"
MODEL_LLM = "claude-sonnet-4-5-20250929"
 
JUMLAH_KANDIDAT = 40      # fetch_k -- kandidat mentah sebelum MMR menyaring
JUMLAH_PER_MESIN = 20     # berapa yang diambil TIAP mesin SEBELUM digabung
JUMLAH_DIPAKAI = 10       # k -- jumlah akhir yang dikirim ke Claude setelah digabung
BOBOT_SEMANTIK = 0.6
BOBOT_BM25 = 0.4
K_RRF = 60
 
DAFTAR_PENYEDIA = ["Kredivo", "Indodana", "Akulaku"]
KATEGORI_LINTAS_PENYEDIA = "Umum"
 
# Penalti ringan untuk jenis dokumen tertentu saat bersaing dengan yang lain.
# RIPLAY dan Simulasi (1.0 = tidak dikurangi) diutamakan karena isinya
# tabel fakta/angka. Agreement diberi penalti (0.8 = dikurangi 20%) karena
# terbukti sering "menang" cuma karena isinya panjang & berulang (banyak
# pasal generik yang menyebut kata kunci serupa), bukan karena benar-benar
# lebih relevan. Penalti ini BUKAN diskualifikasi -- kalau tidak ada
# pesaing dari RIPLAY untuk topik yang sama, Agreement tetap bisa menang
# (contoh: pertanyaan soal cara tutup akun, yang cuma ada di Agreement).
PENALTI_JENIS_DOKUMEN = {
    "RIPLAY": 1.0,
    "Simulasi": 1.0,
    "Rangkuman": 1.0,
    "Agreement": 0.8,
}
 

# MEMUAT BASIS PENGETAHUAN
if not os.path.exists(BERKAS_POTONGAN):
    print(f"[GAGAL] '{BERKAS_POTONGAN}' tidak ada. Jalankan dulu: python ingest.py")
    sys.exit(1)
 
print("[INFO] Menghubungkan ke basis data vektor.")
model_embedding = SentenceTransformerEmbeddings(model_name=MODEL_EMBEDDING)
db = Chroma(persist_directory=FOLDER_DB, embedding_function=model_embedding)
 
with open(BERKAS_POTONGAN, "rb") as berkas:
    SEMUA_POTONGAN = pickle.load(berkas)
 
print(f"[INFO] {len(SEMUA_POTONGAN)} potongan teks dimuat untuk pencarian kata.")
 
 
# MESIN PENCARIAN 1 — BM25 (pencarian berbasis kata)
try:
    from rank_bm25 import BM25Okapi
except ImportError:
    print("[GAGAL] Pustaka rank_bm25 belum terpasang.")
    print("        Jalankan dulu: pip install rank_bm25")
    sys.exit(1)
 
 
def pecah_kata(teks):
    return re.findall(r"[a-z0-9]+", teks.lower())
 
 
print("[INFO] Membangun indeks BM25.")
KORPUS_KATA = [pecah_kata(p.page_content) for p in SEMUA_POTONGAN]
BM25 = BM25Okapi(KORPUS_KATA)
 
 
def penyedia_lolos_saring(potongan, penyedia_terdeteksi):
    """True kalau potongan ini boleh ikut dipertimbangkan.
 
    Dokumen kategori 'Umum' (lintas-penyedia) SELALU lolos, apa pun
    penyedia yang terdeteksi di pertanyaan -- karena dokumen itu memang
    relevan untuk semua penyedia (misal tabel perbandingan biaya).
    """
    if not penyedia_terdeteksi:
        return True
    penyedia_potongan = potongan.metadata.get("penyedia")
    if penyedia_potongan == KATEGORI_LINTAS_PENYEDIA:
        return True
    return penyedia_potongan in penyedia_terdeteksi
 
 
def cari_dengan_bm25(pertanyaan, penyedia_terdeteksi, jumlah):
    skor_semua = BM25.get_scores(pecah_kata(pertanyaan))
    hasil = []
    for nomor, skor in enumerate(skor_semua):
        potongan = SEMUA_POTONGAN[nomor]
        if not penyedia_lolos_saring(potongan, penyedia_terdeteksi):
            continue
        hasil.append((skor, potongan))
    hasil.sort(key=lambda pasangan: pasangan[0], reverse=True)
    return [potongan for _, potongan in hasil[:jumlah]]
 
 
# MESIN PENCARIAN 2 — SEMANTIK (MMR)
def cari_dengan_semantik(pertanyaan, penyedia_terdeteksi, jumlah):
    penyaring = None
    if penyedia_terdeteksi:
        # Penyedia yang disebut + kategori "Umum", supaya dokumen
        # lintas-penyedia tetap ikut dicari.
        daftar_izin = list(penyedia_terdeteksi) + [KATEGORI_LINTAS_PENYEDIA]
        penyaring = {"penyedia": {"$in": daftar_izin}}
 
    return db.max_marginal_relevance_search(
        pertanyaan,
        k=jumlah,
        fetch_k=JUMLAH_KANDIDAT,
        filter=penyaring,
    )
 
 
# DETEKSI PENYEDIA
def deteksi_penyedia(pertanyaan):
    pertanyaan_kecil = pertanyaan.lower()
    return [nama for nama in DAFTAR_PENYEDIA if nama.lower() in pertanyaan_kecil]
 
 
# PENGGABUNGAN HASIL — Reciprocal Rank Fusion
def gabungkan_hasil(daftar_hasil_berbobot, jumlah_akhir, penyedia_terdeteksi=None):
    """Menggabungkan beberapa daftar hasil pencarian jadi satu peringkat.
 
    Kalau penyedia_terdeteksi berisi 2 penyedia atau lebih, dijamin ada
    JATAH MINIMUM slot buat tiap penyedia -- supaya satu penyedia yang
    kontennya lebih "ramai" (contoh: dokumen agreement yang panjang dan
    berulang) tidak menyapu bersih semua slot dan mengubur penyedia lain
    yang disebutkan di pertanyaan yang sama.
 
    Terbukti perlu dari pengujian: tanpa jaminan ini, perbandingan
    Kredivo vs Indodana bisa berakhir 9:1 padahal BM25 sendiri sudah
    menghitung keduanya seimbang (10:9) sebelum digabung -- artinya isi
    dokumen yang lebih "ramai" bisa menang cuma karena kuantitas,
    bukan relevansi.
    """
    skor_gabungan = {}
    simpanan_potongan = {}
    for daftar_hasil, bobot in daftar_hasil_berbobot:
        for peringkat, potongan in enumerate(daftar_hasil, start=1):
            id_potongan = potongan.metadata.get("id_potongan")
            if id_potongan is None:
                continue
            skor_gabungan[id_potongan] = skor_gabungan.get(id_potongan, 0.0) + bobot / (
                K_RRF + peringkat
            )
            simpanan_potongan[id_potongan] = potongan
 
    # Terapkan penalti jenis dokumen SEBELUM pengurutan, supaya tahap
    # jatah minimum di bawah juga memilih dari peringkat yang sudah
    # disesuaikan -- bukan cuma penyesuaian kosmetik di akhir.
    for id_potongan, skor in skor_gabungan.items():
        jenis = simpanan_potongan[id_potongan].metadata.get("jenis_dokumen", "Rangkuman")
        pengali = PENALTI_JENIS_DOKUMEN.get(jenis, 1.0)
        skor_gabungan[id_potongan] = skor * pengali
 
    urutan = sorted(skor_gabungan.items(), key=lambda p: p[1], reverse=True)
    semua_terurut = [simpanan_potongan[i] for i, _ in urutan]
 
    if not penyedia_terdeteksi or len(penyedia_terdeteksi) < 2:
        return semua_terurut[:jumlah_akhir]
 
    jatah_per_penyedia = jumlah_akhir // len(penyedia_terdeteksi)
 
    JENIS_DIUTAMAKAN = {"RIPLAY", "Simulasi"}
 
    hasil_akhir = []
    id_terpakai = set()
 
    for penyedia in penyedia_terdeteksi:
        kandidat_penyedia_ini = [
            p for p in semua_terurut
            if p.metadata.get("penyedia") == penyedia
            and p.metadata.get("id_potongan") not in id_terpakai
        ]
 
        # Tahap A: coba isi jatah dari RIPLAY/Simulasi dulu (peringkat
        # terbaik di antara jenis ini). Kalau jumlahnya cukup, Agreement
        # dari penyedia ini TIDAK akan kepakai sama sekali untuk pertanyaan
        # multi-penyedia -- ini yang bikin Agreement (isinya panjang &
        # berulang, sering "menang" cuma karena kuantitas) tidak lagi bisa
        # mendominasi meski skor mentahnya tinggi.
        diutamakan = [p for p in kandidat_penyedia_ini
                      if p.metadata.get("jenis_dokumen") in JENIS_DIUTAMAKAN]
        diambil = diutamakan[:jatah_per_penyedia]
 
        # Tahap B: kalau RIPLAY/Simulasi tidak cukup buat penuhi jatah,
        # BARU boleh diisi dari Agreement/Rangkuman -- supaya pertanyaan
        # yang topiknya memang cuma ada di Agreement (misal cara tutup
        # akun) tetap bisa terjawab, bukan dipaksa kosong.
        if len(diambil) < jatah_per_penyedia:
            cadangan = [p for p in kandidat_penyedia_ini
                        if p.metadata.get("jenis_dokumen") not in JENIS_DIUTAMAKAN]
            diambil += cadangan[: jatah_per_penyedia - len(diambil)]
 
        for p in diambil:
            hasil_akhir.append(p)
            id_terpakai.add(p.metadata.get("id_potongan"))
 
    # Sisa slot (kalau ada) diisi dari peringkat terbaik keseluruhan,
    # termasuk kategori "Umum" dan sisa dari penyedia mana pun.
    for potongan in semua_terurut:
        if len(hasil_akhir) >= jumlah_akhir:
            break
        id_potongan = potongan.metadata.get("id_potongan")
        if id_potongan in id_terpakai:
            continue
        hasil_akhir.append(potongan)
        id_terpakai.add(id_potongan)
 
    return hasil_akhir[:jumlah_akhir]
 
 
# MERAKIT KONTEKS
def rakit_konteks(daftar_potongan):
    bagian = []
    for potongan in daftar_potongan:
        penyedia = potongan.metadata.get("penyedia", "Tidak diketahui")
        halaman = potongan.metadata.get("halaman", "?")
        berkas = potongan.metadata.get("berkas", "?")
        bagian.append(
            f"[Sumber: {penyedia}, berkas {berkas}, halaman {halaman}]\n{potongan.page_content}"
        )
    return "\n\n".join(bagian)
 
 
def ringkas_sumber(daftar_potongan):
    terkumpul = []
    for potongan in daftar_potongan:
        penanda = (potongan.metadata.get("penyedia"), potongan.metadata.get("halaman"))
        if penanda not in terkumpul:
            terkumpul.append(penanda)
    return "; ".join(f"{p} hal.{h}" for p, h in terkumpul)
 
 
# TEMPLATE INSTRUKSI
TEMPLATE = """Gunakan potongan dokumen berikut untuk menjawab pertanyaan pengguna.
 
ATURAN MENJAWAB:
1. Jawab HANYA berdasarkan potongan dokumen di bawah.
2. Jika pertanyaan menyebut satu penyedia tertentu, jawab HANYA mengenai
   penyedia tersebut. Jangan mencampur ketentuan milik penyedia lain.
3. Jika pertanyaan membutuhkan perhitungan, lakukan perhitungannya sendiri
   dan jabarkan langkah-langkahnya.
3b. PENTING: kalau dokumen menyediakan RATE/PERSENTASE umum untuk suatu
    tenor atau produk (misalnya "bunga 3% per bulan untuk tenor 3-24
    bulan"), PAKAI rate tersebut untuk menghitung meskipun nominal
    transaksi yang ditanyakan BERBEDA dari contoh simulasi siap pakai
    yang ada di dokumen. Jangan menganggap "tidak ada tabel simulasi
    persis untuk nominal ini" itu sama dengan "informasinya tidak ada".
    Selama rate/persentasenya tersedia, itu SUDAH CUKUP untuk dihitung
    sendiri -- tidak perlu menunggu tabel jadi yang persis cocok.
4. Jawab hanya komponen biaya yang DITANYAKAN.
5. Jika angka di dokumen berupa rentang, sebutkan rentangnya, jangan
   memilih sendiri satu angka diam-diam.
6. Jika ada dua potongan dokumen yang saling bertentangan, sampaikan
   perbedaan itu, jangan memilih salah satu diam-diam.
7. Jika angka yang dibutuhkan benar-benar tidak ada di dokumen, katakan
   bahwa informasinya tidak ditemukan.
 
Konteks Dokumen:
{context}
 
Pertanyaan: {question}
 
Jawaban:"""
 
prompt = PromptTemplate.from_template(TEMPLATE)
 
print("[INFO] Menginisialisasi model Claude.")
llm = ChatAnthropic(model=MODEL_LLM, temperature=0)
pengurai = StrOutputParser()
 
 
# FUNGSI UTAMA
def jawab_lengkap(pertanyaan):
    penyedia_terdeteksi = deteksi_penyedia(pertanyaan)
 
    # PENTING: tiap mesin dikasih jatah lebih lebar (JUMLAH_PER_MESIN=20)
    # dulu di sini, BUKAN langsung dipepetin ke 10. Baru pas gabungkan_hasil()
    # di bawah, hasil gabungan dipepetin ke JUMLAH_DIPAKAI=10. Kalau langsung
    # dipepetin ke 10 dari awal, kandidat yang lumayan relevan tapi nggak
    # masuk top-10 di SALAH SATU mesin bakal keburu hilang sebelum sempat
    # dibandingin bareng -- itu yang bikin hasil hybrid sempat lebih jelek
    # dari MMR biasa.
    hasil_bm25 = cari_dengan_bm25(pertanyaan, penyedia_terdeteksi, JUMLAH_PER_MESIN)
    hasil_semantik = cari_dengan_semantik(pertanyaan, penyedia_terdeteksi, JUMLAH_PER_MESIN)
 
    potongan_terpilih = gabungkan_hasil(
        [(hasil_semantik, BOBOT_SEMANTIK), (hasil_bm25, BOBOT_BM25)],
        JUMLAH_DIPAKAI,
        penyedia_terdeteksi=penyedia_terdeteksi,
    )
 
    konteks = rakit_konteks(potongan_terpilih)
    pesan = prompt.format(context=konteks, question=pertanyaan)
    jawaban = pengurai.invoke(llm.invoke(pesan))
 
    return {
        "jawaban": jawaban,
        "penyedia_terdeteksi": ", ".join(penyedia_terdeteksi) if penyedia_terdeteksi else "(umum/tidak spesifik)",
        "sumber": ringkas_sumber(potongan_terpilih),
    }
 
 
def tanya_ai(pertanyaan):
    """Dipanggil oleh final.py."""
    return jawab_lengkap(pertanyaan)["jawaban"]
 
 
# OTOMATISASI PENGUJIAN
if __name__ == "__main__":
    print("\n[SUCCESS] Sistem RAG berhasil dijalankan!\n")
 
    jalur_masuk = "dataset_csv/dataset_evaluasi_rag.csv"
    jalur_keluar = "dataset_csv/hasil_evaluasi.csv"
 
    print(f"[INFO] Membaca daftar pertanyaan dari: {jalur_masuk}")
    df = pd.read_csv(jalur_masuk, sep=";", encoding="utf-8")
 
    kolom_hasil = ["Jawaban_Claude", "Penyedia_Terdeteksi", "Sumber_Konteks", "Skor", "Alasan_Penilaian"]
    for kolom in kolom_hasil:
        if kolom not in df.columns:
            df[kolom] = ""
 
    if os.path.exists(jalur_keluar):
        print(f"[INFO] Ditemukan '{jalur_keluar}' dari percobaan sebelumnya.")
        try:
            df_lama = pd.read_csv(jalur_keluar, encoding="utf-8")
            if "ID_Soal" in df_lama.columns and "ID_Soal" in df.columns:
                peta_lama = df_lama.set_index("ID_Soal")
                for idx, baris in df.iterrows():
                    id_soal = baris["ID_Soal"]
                    if id_soal in peta_lama.index:
                        for kolom in ["Jawaban_Claude", "Penyedia_Terdeteksi", "Sumber_Konteks"]:
                            if kolom in peta_lama.columns:
                                nilai = peta_lama.loc[id_soal, kolom]
                                if pd.notna(nilai) and str(nilai).strip() != "":
                                    df.at[idx, kolom] = nilai
                print("[INFO] Jawaban lama dimuat ulang, hanya pertanyaan yang BELUM")
                print("       terjawab yang akan ditanyakan ke Claude kali ini.")
        except Exception as e:
            print(f"[PERINGATAN] Gagal membaca hasil lama ({e}), mulai dari awal.")
 
    def simpan_progres(df):
        try:
            df.to_csv(jalur_keluar, index=False, encoding="utf-8")
        except PermissionError:
            import datetime
            cap_waktu = datetime.datetime.now().strftime("%H%M%S")
            jalur_cadangan = jalur_keluar.replace(".csv", f"_{cap_waktu}.csv")
            df.to_csv(jalur_cadangan, index=False, encoding="utf-8")
            print(f"    [PERINGATAN] '{jalur_keluar}' terkunci, disimpan ke '{jalur_cadangan}'.")
            print("                 Tutup file lama sebelum menjalankan ulang.")
 
    jumlah_dilewati = 0
    jumlah_diproses = 0
 
    for nomor_baris, baris in df.iterrows():
        jawaban_lama = baris.get("Jawaban_Claude", "")
        if pd.notna(jawaban_lama) and str(jawaban_lama).strip() != "":
            jumlah_dilewati += 1
            continue  # sudah punya jawaban dari percobaan sebelumnya -- lewati
 
        teks_tanya = baris["Teks_Pertanyaan"]
        print(f"\n[PROSES {nomor_baris + 1}/{len(df)}] {teks_tanya[:70]}...")
 
        try:
            hasil = jawab_lengkap(teks_tanya)
        except Exception as e:
            print(f"\n[GAGAL] Terjadi error saat memproses baris ini: {e}")
            print(f"[INFO] {jumlah_diproses} pertanyaan baru berhasil dijawab dan SUDAH TERSIMPAN")
            print(f"       sebelum error ini terjadi (lihat '{jalur_keluar}').")
            break
 
        df.at[nomor_baris, "Jawaban_Claude"] = hasil["jawaban"]
        df.at[nomor_baris, "Penyedia_Terdeteksi"] = hasil["penyedia_terdeteksi"]
        df.at[nomor_baris, "Sumber_Konteks"] = hasil["sumber"]
        jumlah_diproses += 1
 
        print(f"    Penyedia terdeteksi : {hasil['penyedia_terdeteksi']}")
        print(f"    Sumber terambil     : {hasil['sumber']}")
 
        simpan_progres(df)
 
    if jumlah_dilewati:
        print(f"\n[INFO] {jumlah_dilewati} pertanyaan dilewati (sudah punya jawaban dari sebelumnya).")
    print(f"[INFO] {jumlah_diproses} pertanyaan baru diproses pada percobaan kali ini.")
    print(f"\n[SELESAI] Hasil tersimpan di: {jalur_keluar}")
 
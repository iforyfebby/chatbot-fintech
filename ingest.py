import os
import pickle
import shutil
import sys
import warnings
 
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings.sentence_transformer import (
    SentenceTransformerEmbeddings,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
 
warnings.filterwarnings("ignore")
 

# PENGATURAN 
FOLDER_PDF = "dataset_teks"
FOLDER_DB = "vector_db"
BERKAS_POTONGAN = "potongan_teks.pkl"
 
UKURAN_POTONGAN = 1500
IRISAN_POTONGAN = 300
MODEL_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"
 
# Kunci = kata kunci yang dicari di NAMA BERKAS (huruf kecil).
# Kalau nambah penyedia baru, tambahin baris di sini.
PETA_PENYEDIA = {
    "kredivo": "Kredivo",
    "indodana": "Indodana",
    "akulaku": "Akulaku",
}
 
# Kategori khusus untuk dokumen yang isinya lintas-penyedia
# (perbandingan/rangkuman semua penyedia dalam satu berkas).
KATEGORI_LINTAS_PENYEDIA = "Umum"
 
 
def kenali_jenis_dokumen(nama_berkas):
    """Menandai jenis dokumen berdasarkan nama berkas.
 
    Dipakai nanti di app.py untuk memberi prioritas ringan ke RIPLAY
    dibanding Agreement saat keduanya bersaing untuk slot yang sama --
    soalnya RIPLAY isinya tabel fakta/angka, sedangkan Agreement isinya
    pasal hukum/prosedural yang sering "berisik" (banyak & berulang)
    walau tidak selalu relevan langsung ke pertanyaan.
    """
    nama_kecil = nama_berkas.lower()
    if "riplay" in nama_kecil:
        return "RIPLAY"
    if "agreement" in nama_kecil:
        return "Agreement"
    if "simulasi" in nama_kecil:
        return "Simulasi"
    return "Rangkuman"  # Rincian_Biaya_Denda_Fintech, Syarat_Pendaftaran_Fintech, dsb
 
 

# FUNGSI BANTU
def deteksi_penyedia_dalam_halaman(teks_halaman):
    """Menebak SATU penyedia dominan di dalam satu halaman dokumen lintas-
    penyedia (kategori 'Umum'), berdasarkan penanda bagian atau frekuensi
    penyebutan nama penyedia.
 
    Dipakai khusus untuk dokumen seperti Rincian_Biaya_Denda_Fintech yang
    strukturnya berupa bagian bernomor per penyedia ("1. Indodana...",
    "2. Kredivo...", dst). Tanpa ini, semua potongan dari dokumen tersebut
    berlabel 'Umum' rata, sehingga kalau proses pemotongan kebetulan
    memisahkan judul bagian dari isinya, Claude tidak tahu potongan itu
    sebenarnya membahas penyedia mana -- dan bisa salah menebak (terbukti
    di kasus Q-29: biaya administrasi KTA Kredivo malah dikira "penyedia
    lain" karena judul bagiannya tidak ikut terbawa dalam potongan yang
    sama).
 
    Mengembalikan nama penyedia kalau yakin, atau None kalau memang
    campuran/tidak jelas (dibiarkan tetap 'Umum').
    """
    teks_kecil = teks_halaman.lower()
 
    # Sinyal terkuat: penanda bagian bernomor eksplisit
    penanda_bagian = {
        "kredivo": ["2. kredivo", "kredivo\n"],
        "indodana": ["1. indodana", "indodana paylater dan pinjaman"],
        "akulaku": ["3. akulaku", "akulaku paylater dan pinjaman"],
    }
    for penyedia_kecil, penanda_list in penanda_bagian.items():
        for penanda in penanda_list:
            if penanda in teks_kecil:
                return penyedia_kecil.capitalize()
 
    # Sinyal kedua: penyedia mana yang paling sering disebut di halaman ini
    hitungan = {
        "Kredivo": teks_kecil.count("kredivo"),
        "Indodana": teks_kecil.count("indodana"),
        "Akulaku": teks_kecil.count("akulaku"),
    }
    penyedia_terbanyak = max(hitungan, key=hitungan.get)
    jumlah_terbanyak = hitungan[penyedia_terbanyak]
    jumlah_lain = sum(v for k, v in hitungan.items() if k != penyedia_terbanyak)
 
    # Cuma dianggap dominan kalau jelas menang jauh, bukan cuma unggul tipis
    if jumlah_terbanyak >= 2 and jumlah_terbanyak > jumlah_lain * 2:
        return penyedia_terbanyak
 
    return None  # campuran/tidak jelas -> tetap "Umum"
 
 
def kenali_penyedia(nama_berkas):
    """Menebak penyedia dari nama berkas.
 
    Mengembalikan salah satu dari 'Kredivo'/'Indodana'/'Akulaku' kalau
    nama berkas mengandung kata kuncinya, atau 'Umum' kalau berkas
    memang tidak menyebut satu penyedia spesifik (misalnya dokumen
    rangkuman/perbandingan lintas-penyedia).
    """
    nama_tanpa_ekstensi = os.path.splitext(nama_berkas)[0].lower()
    for kata_kunci, nama_resmi in PETA_PENYEDIA.items():
        if kata_kunci in nama_tanpa_ekstensi:
            return nama_resmi
    return KATEGORI_LINTAS_PENYEDIA
    """Menebak penyedia dari nama berkas.
 
    Mengembalikan salah satu dari 'Kredivo'/'Indodana'/'Akulaku' kalau
    nama berkas mengandung kata kuncinya, atau 'Umum' kalau berkas
    memang tidak menyebut satu penyedia spesifik (misalnya dokumen
    rangkuman/perbandingan lintas-penyedia).
    """
    nama_tanpa_ekstensi = os.path.splitext(nama_berkas)[0].lower()
    for kata_kunci, nama_resmi in PETA_PENYEDIA.items():
        if kata_kunci in nama_tanpa_ekstensi:
            return nama_resmi
    return KATEGORI_LINTAS_PENYEDIA
 
 

# PROSES UTAMA 
print("[INFO] MEMULAI PROSES INGESTION (PEMBUATAN BASIS PENGETAHUAN)")
 
if not os.path.isdir(FOLDER_PDF):
    print(f"[GAGAL] Folder '{FOLDER_PDF}' tidak ditemukan.")
    sys.exit(1)
 
daftar_pdf = sorted(f for f in os.listdir(FOLDER_PDF) if f.lower().endswith(".pdf"))
 
if not daftar_pdf:
    print(f"[GAGAL] Tidak ada berkas PDF di dalam folder '{FOLDER_PDF}'.")
    sys.exit(1)
 
print(f"[INFO] Ditemukan {len(daftar_pdf)} berkas PDF.\n")
 
# Bersihkan hasil proses sebelumnya
if os.path.exists(FOLDER_DB):
    print(f"[INFO] Menghapus '{FOLDER_DB}' lama agar tidak bentrok.")
    shutil.rmtree(FOLDER_DB)
if os.path.exists(BERKAS_POTONGAN):
    os.remove(BERKAS_POTONGAN)
 
# Muat tiap PDF, beri penanda penyedia (atau "Umum" kalau lintas-penyedia)
semua_halaman = []
 
for nama_berkas in daftar_pdf:
    penyedia = kenali_penyedia(nama_berkas)
    jalur_berkas = os.path.join(FOLDER_PDF, nama_berkas)
 
    pemuat = PyPDFLoader(jalur_berkas)
    halaman_berkas_ini = pemuat.load()
 
    for halaman in halaman_berkas_ini:
        penyedia_halaman_ini = penyedia
        if penyedia == KATEGORI_LINTAS_PENYEDIA:
            tebakan = deteksi_penyedia_dalam_halaman(halaman.page_content)
            if tebakan is not None:
                penyedia_halaman_ini = tebakan
 
        halaman.metadata["penyedia"] = penyedia_halaman_ini
        halaman.metadata["jenis_dokumen"] = kenali_jenis_dokumen(nama_berkas)
        halaman.metadata["berkas"] = nama_berkas
        halaman.metadata["halaman"] = int(halaman.metadata.get("page", 0)) + 1
 
    tanda = " (LINTAS-PENYEDIA)" if penyedia == KATEGORI_LINTAS_PENYEDIA else ""
    print(f"[INFO] {nama_berkas:<35} -> {penyedia:<8}{tanda} ({len(halaman_berkas_ini)} halaman)")
    semua_halaman.extend(halaman_berkas_ini)
 
print(f"\n[INFO] Total {len(semua_halaman)} halaman berhasil dimuat.")
 
# Ringkasan khusus: dari halaman berkategori Umum, berapa yang berhasil
# ditebak jadi penyedia spesifik vs yang tetap Umum
halaman_umum_asli = [h for h in semua_halaman if kenali_penyedia(h.metadata["berkas"]) == KATEGORI_LINTAS_PENYEDIA]
if halaman_umum_asli:
    tertebak = sum(1 for h in halaman_umum_asli if h.metadata["penyedia"] != KATEGORI_LINTAS_PENYEDIA)
    print(f"[INFO] Dari {len(halaman_umum_asli)} halaman dokumen lintas-penyedia,")
    print(f"       {tertebak} berhasil ditebak penyedia spesifiknya,")
    print(f"       {len(halaman_umum_asli) - tertebak} tetap berlabel 'Umum'.")
 
# Potong dokumen
print("[INFO] Memotong dokumen menjadi ukuran yang optimal.")
pemotong_teks = RecursiveCharacterTextSplitter(
    chunk_size=UKURAN_POTONGAN,
    chunk_overlap=IRISAN_POTONGAN,
    separators=["\n\n", "\n", " ", ""],
)
potongan_teks = pemotong_teks.split_documents(semua_halaman)
 
for nomor, potongan in enumerate(potongan_teks):
    potongan.metadata["id_potongan"] = nomor
 
print(f"[INFO] Dokumen dipotong menjadi {len(potongan_teks)} bagian (chunks).")
 
print("\n[INFO] Jumlah potongan per kategori:")
hitungan = {}
for potongan in potongan_teks:
    nama = potongan.metadata["penyedia"]
    hitungan[nama] = hitungan.get(nama, 0) + 1
for nama, jumlah in sorted(hitungan.items()):
    print(f"        {nama:<10}: {jumlah} potongan")
 
# Hitung embedding dan simpan
print("\n[INFO] Memproses embedding dan membangun basis data vektor.")
model_embedding = SentenceTransformerEmbeddings(model_name=MODEL_EMBEDDING)
 
db = Chroma.from_documents(
    documents=potongan_teks,
    embedding=model_embedding,
    persist_directory=FOLDER_DB,
)
 
with open(BERKAS_POTONGAN, "wb") as berkas:
    pickle.dump(potongan_teks, berkas)
 
print(f"[INFO] Daftar potongan disimpan ke '{BERKAS_POTONGAN}'.")
print("\n[SUCCESS] Proses selesai! Basis pengetahuan siap dipakai oleh app.py")
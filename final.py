import base64
import os

import streamlit as st
from app import tanya_ai

st.set_page_config(
    page_title="Tanya Fintech",
    page_icon="◆",
    layout="centered",
)

# GAYA TAMPILAN 
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap');

* {
    font-family: 'Public Sans', sans-serif;
}

#MainMenu, footer, header[data-testid="stHeader"] {
    visibility: hidden;
    height: 0;
}

.block-container {
    max-width: 700px;
    padding-top: 2.5rem;
    padding-bottom: 6rem;
}

/* Header nempel di atas pas discroll. z-index tinggi biar nggak ketiban
   konten chat yang lewat di bawahnya, background solid biar nggak
   tembus pandang. */
.sticky-header {
    padding: 0.5rem 0 0.6rem 0;
}
.sticky-header > * {
    width: 100%;
    max-width: 700px;
}
/* Kasih jarak kosong di atas konten biar nggak ketiban header yang
   sekarang "melayang" di luar aliran halaman biasa -- diatur langsung
   di .block-container (padding-top: 8.5rem) di atas. Sesuaikan angka
   itu kalau headernya kepotong atau jaraknya kerasa kurang/lebih. */

/* ---------- Header ---------- */
.masthead-title {
    font-weight: 700 !important;
    font-size: 2rem !important;
    color: #1A1A1A !important;
    margin: 0 !important;
    letter-spacing: -0.01em;
}
.provider-row {
    display: flex;
    gap: 0.45rem;
    flex-wrap: wrap;
    margin-top: 0.7rem;
    margin-bottom: 0.6rem;
}
.provider-chip {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: #6B6B6F;
    background: #F5F5F6;
    border: 1px solid #E7E7E9;
    border-radius: 6px;
    padding: 0.3rem 0.65rem;
}
.provider-chip-logo {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem 0.7rem;
    background: #FFFFFF;
    border: 1px solid #E7E7E9;
    border-radius: 10px;
}
.provider-logo-img {
    height: 26px;
    width: auto;
    object-fit: contain;
}
.masthead-rule {
    border: none;
    border-top: 1px solid #EEEEEF;
    margin: 0 0 1.5rem 0;
}

/* ---------- Bubble chat ---------- */
[data-testid="stChatMessage"] {
    display: flex;
    max-width: 82%;
    margin-bottom: 0.6rem;
}
/* Avatar dimatiin -- posisi kanan/kiri + warna bubble udah cukup buat
   bedain siapa yang ngomong, avatar warna-warni cuma bikin ramai */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    display: none;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    margin-left: auto;
    margin-right: 0;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    margin-right: auto;
    margin-left: 0;
}
[data-testid="stChatMessageContent"] {
    font-size: 0.95rem;
    line-height: 1.6;
    color: #1F1F1F;
}
/* Batesin ukuran heading Markdown -- kalau dibiarin, jawaban yang
   pake #/## dirender gede banget kayak judul artikel */
[data-testid="stChatMessageContent"] h1,
[data-testid="stChatMessageContent"] h2,
[data-testid="stChatMessageContent"] h3 {
    font-size: 1rem;
    font-weight: 700;
    margin: 0.7rem 0 0.35rem 0;
    line-height: 1.4;
}
[data-testid="stChatMessageContent"] ul,
[data-testid="stChatMessageContent"] ol {
    margin: 0.3rem 0;
    padding-left: 1.2rem;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
    background: #F7F7F8;
    border-radius: 14px;
    padding: 0.9rem 1.1rem;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
    background: #EDF3FF;
    border: 1px solid #DCE7FB;
    border-radius: 14px;
    padding: 0.9rem 1.1rem;
}

/* ---------- Pertanyaan contoh ---------- */
.empty-hint {
    font-size: 0.85rem;
    color: #8A8A8E;
    margin: 0.5rem 0 0.75rem 0;
}
.stButton > button {
    width: 100%;
    text-align: left;
    font-size: 0.87rem;
    color: #4A4A4E;
    background: #FFFFFF;
    border: 1px solid #E7E7E9;
    border-radius: 10px;
    padding: 0.65rem 0.9rem;
    transition: border-color 0.15s ease, background 0.15s ease;
}
.stButton > button:hover {
    border-color: #C9C9CC;
    background: #FAFAFA;
    color: #1A1A1A;
}

[data-testid="stSpinner"] p {
    color: #8A8A8E;
    font-size: 0.85rem;
}

/* Kotak contoh prompt (st.code) -- defaultnya digeser ke samping kayak
   kode program, ini dipaksa turun ke bawah (wrap) karena isinya kalimat
   biasa, bukan kode. Tombol salin bawaan tetap jalan normal. */
[data-testid="stCode"] pre,
[data-testid="stCode"] code {
    white-space: pre-wrap !important;
    word-break: break-word !important;
    overflow-x: hidden !important;
}
</style>
""", unsafe_allow_html=True)

# HEADER
def buat_chip_penyedia(nama_label, nama_file):
    jalur = f"assets/{nama_file}"
    if os.path.exists(jalur):
        with open(jalur, "rb") as f:
            data_base64 = base64.b64encode(f.read()).decode()
        ekstensi = nama_file.split(".")[-1]
        return (
            f'<span class="provider-chip provider-chip-logo" title="{nama_label}">'
            f'<img src="data:image/{ekstensi};base64,{data_base64}" '
            f'alt="{nama_label}" class="provider-logo-img" /></span>'
        )
    else:
        return f'<span class="provider-chip">{nama_label}</span>'


chip_kredivo = buat_chip_penyedia("KREDIVO", "kredivo.png")
chip_indodana = buat_chip_penyedia("INDODANA", "indodana.png")
chip_akulaku = buat_chip_penyedia("AKULAKU", "akulaku.png")

st.markdown(f"""
<div class="sticky-header">
<p class="masthead-title">Tanya Fintech</p>
<div class="provider-row">
    {chip_kredivo}
    {chip_indodana}
    {chip_akulaku}
</div>
<hr class="masthead-rule" />
</div>
""", unsafe_allow_html=True)

# BUBBLE SAPAAN
with st.chat_message("assistant"):
    st.markdown(
        "Halo! Aku bisa bantu jawab pertanyaan seputar **bunga, biaya, denda, "
        "dan syarat pendaftaran** layanan *paylater* dari tiga penyedia "
        "(Kredivo, Indodana, dan Akulaku) berdasarkan dokumen resmi mereka "
        "(RIPLAY dan Syarat & Ketentuan).\n\n"
        "Cocok dipakai buat bandingin biaya sebelum kamu mutusin pakai salah "
        "satu layanan. Ada yang mau ditanyain?"
    )

# CONTOH PROMPT LENGKAP
with st.expander("💡 Lihat contoh pertanyaan lengkap", expanded=not st.session_state.get("messages")):
    st.markdown(
        "Contoh pertanyaan yang bisa langsung disalin dan disesuaikan "
        "nominal/tenornya sesuai kebutuhanmu:"
    )
    st.code(
        "Simulasikan dan hitungkan jika saya mau minjam Rp5.000.000 dengan "
        "tenor 12 bulan di Kredivo, Akulaku, dan Indodana, mana yang paling "
        "murah? Syarat dan ketentuannya apa aja untuk meminjam?",
        language=None,
    )
    st.caption("Arahkan kursor ke kotak di atas untuk memunculkan ikon salin.")

# STATE
if "messages" not in st.session_state:
    st.session_state.messages = []

CONTOH_PERTANYAAN = [
    "Berapa bunga Kredivo buat cicilan 12 bulan?",
    "Bandingin denda telat bayar Akulaku sama Indodana",
    "Syarat daftar Indodana PayLater apa aja?",
]

pertanyaan_terpilih = None

if not st.session_state.messages:
    st.markdown('<p class="empty-hint">Coba salah satu, atau ketik pertanyaanmu sendiri di bawah</p>', unsafe_allow_html=True)
    for i, contoh in enumerate(CONTOH_PERTANYAAN):
        if st.button(contoh, key=f"contoh_{i}"):
            pertanyaan_terpilih = contoh

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# INPUT & JAWABAN
prompt = st.chat_input("Tanya soal bunga, biaya, atau denda...")
if pertanyaan_terpilih:
    prompt = pertanyaan_terpilih

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Menelusuri dokumen..."):
            jawaban = tanya_ai(prompt)
            st.markdown(jawaban)
    st.session_state.messages.append({"role": "assistant", "content": jawaban})

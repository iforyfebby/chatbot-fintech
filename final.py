import streamlit as st
from app import tanya_ai

st.set_page_config(
    page_title="Tanya Fintech",
    page_icon="◆",
    layout="centered",
)

# GAYA TAMPILAN -- clean, latar putih
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

/* ---------- Header ---------- */
.masthead-title {
    font-weight: 700;
    font-size: 1.7rem;
    color: #1A1A1A;
    margin: 0;
}
.masthead-sub {
    font-size: 0.9rem;
    color: #8A8A8E;
    margin: 0.3rem 0 1rem 0;
}
.provider-row {
    display: flex;
    gap: 0.45rem;
    flex-wrap: wrap;
    margin-bottom: 1.3rem;
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
</style>
""", unsafe_allow_html=True)

# HEADER
st.markdown("""
<p class="masthead-title">Tanya Fintech</p>
<p class="masthead-sub">Eksplorasi bunga, biaya, dan denda dari dokumen resmi penyedia</p>
<div class="provider-row">
    <span class="provider-chip">KREDIVO</span>
    <span class="provider-chip">INDODANA</span>
    <span class="provider-chip">AKULAKU</span>
</div>
<hr class="masthead-rule" />
""", unsafe_allow_html=True)

kata_sandi_diatur = "APP_PASSWORD" in st.secrets if hasattr(st, "secrets") else False

if kata_sandi_diatur and not st.session_state.get("sudah_login", False):
    st.markdown("##### Masukkan kode akses")
    kode_masuk = st.text_input("Kode akses", type="password", label_visibility="collapsed")
    if kode_masuk:
        if kode_masuk == st.secrets["APP_PASSWORD"]:
            st.session_state.sudah_login = True
            st.rerun()
        else:
            st.error("Kode akses salah.")
    st.stop()  # hentikan render halaman di sini kalau belum login


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
from fastapi import FastAPI
from pydantic import BaseModel
from mesin_agent import buat_brief   # ambil mesin agent yang tadi kita bikin
from mesin_seo import cek_seo        # mesin cek SEO/readability ala Yoast

# Bikin aplikasi backend-nya
app = FastAPI()

# Ini "bentuk pesanan" yang harus dikirim ke loket kita.
# Artinya: siapa pun yang mau minta brief, harus kasih topik, link, dan daftar platform.
class PesananBrief(BaseModel):
    topik: str
    link: str = ""                 # boleh kosong
    platform: list[str]            # contoh: ["Instagram", "LinkedIn"]
    jumlah: int = 1                # jumlah brief per platform (1-8)

# Loket pertama: cuma buat ngecek backend hidup atau nggak
@app.get("/")
def cek_hidup():
    return {"status": "Backend agent hidup!"}

# Loket utama: nerima pesanan, jalanin mesin agent, balikin brief
@app.post("/buat-brief")
def endpoint_buat_brief(pesanan: PesananBrief):
    hasil = buat_brief(pesanan.topik, pesanan.link, pesanan.platform, pesanan.jumlah)
    return {"brief": hasil}

# Pesanan untuk cek SEO sebuah artikel
class PesananCekSEO(BaseModel):
    title: str = ""
    content: str = ""
    meta_description: str = ""
    focus_keyphrase: str = ""
    perbaiki: bool = False         # kalau True, AI sekalian merevisi artikel

# Loket cek SEO: nilai artikel ala Yoast, balikin skor + checklist + saran (+revisi)
@app.post("/cek-seo")
def endpoint_cek_seo(pesanan: PesananCekSEO):
    hasil = cek_seo(
        pesanan.title,
        pesanan.content,
        pesanan.meta_description,
        pesanan.focus_keyphrase,
        pesanan.perbaiki,
    )
    return hasil
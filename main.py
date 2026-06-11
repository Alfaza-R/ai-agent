from fastapi import FastAPI
from pydantic import BaseModel
from mesin_agent import buat_brief   # ambil mesin agent yang tadi kita bikin

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
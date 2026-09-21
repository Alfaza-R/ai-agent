from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mesin_agent import buat_brief   # ambil mesin agent yang tadi kita bikin
from mesin_seo import cek_seo        # mesin cek SEO/readability ala Yoast
from mesin_brief_seo import buat_brief_seo  # rencana gambar untuk task SEO (input gambar artikel)
from mesin_analisis import analisa_kinerja  # narasi analisis kinerja intern (dashboard)
from mesin_brief_video import buat_brief_video  # brief video short (Reels/TikTok/Shorts)
from mesin_bms import analisa_bms    # asisten sales Building Management System
from mesin_penetrasi import analisa_penetrasi, rekomendasi_target  # sistem multi-agent penetrasi pasar
from mesin_konten_ig import buat_konten_ig  # multi-agent konten Instagram 4:5
from mesin_hobo import analisa_hobo    # asisten sales & service HOBO data logger
from mesin_fakopp import analisa_fakopp  # asisten sales & service alat Fakopp (pohon & kayu)
from mesin_hmp import analisa_hmp      # asisten sales & service alat HMP (uji tanah/geoteknik)
from mesin_timbangan import analisa_timbangan  # asisten sales & service timbangan (timbanganindonesia.com)
from mesin_loadcell import analisa_loadcell  # asisten sales & service load cell (rajaloadcell.com)
from mesin_microepsilon import analisa_microepsilon  # asisten sales & service sensor Micro-Epsilon (micro-epsilon.com)

# Bikin aplikasi backend-nya
app = FastAPI()

# Izinkan halaman web lain (mis. dashboard di WordPress) memanggil backend ini.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # semua domain boleh; aman karena endpoint ini memang publik
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ini "bentuk pesanan" yang harus dikirim ke loket kita.
# Artinya: siapa pun yang mau minta brief, harus kasih topik, link, dan daftar platform.
class PesananBrief(BaseModel):
    topik: str
    link: str = ""                 # boleh kosong
    platform: list[str]            # contoh: ["Instagram", "LinkedIn"]
    jumlah: int = 0                 # 0 = Agent Jumlah yang tentukan sendiri; >0 = dipakai apa adanya (1-8)
    brand: str = ""                 # akun/brand sosmed (alatuji, taharica, automationindo, loggerindo, timbangan, rajaloadcell)
    sudut: list[str] = []           # sudut konten pilihan user (mis. ["Product Knowledge"]); kosong = sistem pilih sendiri

# Loket pertama: cuma buat ngecek backend hidup atau nggak
@app.get("/")
def cek_hidup():
    return {"status": "Backend agent hidup!"}

# Loket utama: nerima pesanan, jalanin mesin agent, balikin brief
@app.post("/buat-brief")
def endpoint_buat_brief(pesanan: PesananBrief):
    hasil = buat_brief(pesanan.topik, pesanan.link, pesanan.platform, pesanan.jumlah, pesanan.brand, pesanan.sudut)
    if not any(hasil.values()):
        # Semua brief gagal walau sudah retry + model cadangan -> server AI sedang benar-benar down.
        raise HTTPException(status_code=503, detail="Server AI sedang sibuk. Coba generate lagi dalam 1-2 menit.")
    return {"brief": hasil}

# Pesanan brief SEO "input gambar": mentor kirim daftar keyword (artikel sudah tayang,
# gambarnya belum ada) + website mana. Kredensial login TIDAK dikirim ke sini — bagian itu
# disusun di WordPress, karena endpoint ini publik.
class ItemKeywordSEO(BaseModel):
    keyword: str = ""
    referensi: list[str] = []      # link referensi gambar dari mentor (opsional)

class PesananBriefSEO(BaseModel):
    situs: str = ""                # cth: "alatuji.co.id" (cuma buat konteks, bukan kredensial)
    daftar: list[ItemKeywordSEO] = []
    catatan: str = ""              # instruksi tambahan dari mentor (opsional)

# Loket brief SEO: balikin rencana gambar per keyword (featured + gambar dalam artikel)
@app.post("/brief-seo-gambar")
def endpoint_brief_seo_gambar(pesanan: PesananBriefSEO):
    daftar = [item.model_dump() for item in pesanan.daftar]
    if not any((item.get("keyword") or "").strip() for item in daftar):
        raise HTTPException(status_code=400, detail="Daftar keyword kosong.")
    hasil = buat_brief_seo(daftar, pesanan.situs, pesanan.catatan)
    if hasil["jumlah_gagal"] and hasil["jumlah_gagal"] == hasil["jumlah_keyword"]:
        raise HTTPException(status_code=503, detail="Server AI sedang sibuk. Coba generate lagi dalam 1-2 menit.")
    return hasil

# Pesanan brief video short (9:16, 30-60 detik)
class PesananBriefVideo(BaseModel):
    topik: str
    link: str = ""                 # link produk/referensi (dibaca Agent Research)
    gambar: list[str] = []         # link gambar produk dari mentor
    brand: str = ""                # key BRAND_INFO (alatuji, taharica, dst.)
    durasi: int = 0                # 0 = AI pilih 30-60 detik; 30/45/60 = dipaksa
    jumlah: int = 1                # 1-3 video per permintaan
    sudut: list[str] = []          # key sudut konten; kosong = sistem pilih bergiliran
    catatan: str = ""

@app.post("/buat-brief-video")
def endpoint_buat_brief_video(pesanan: PesananBriefVideo):
    hasil = buat_brief_video(
        pesanan.topik, pesanan.link, pesanan.gambar, pesanan.brand,
        pesanan.durasi, pesanan.jumlah, pesanan.sudut, pesanan.catatan,
    )
    if not hasil:
        raise HTTPException(status_code=503, detail="Server AI sedang sibuk. Coba generate lagi dalam 1-2 menit.")
    return {"brief": hasil}

# Pesanan analisis kinerja intern: dashboard kirim ANGKA hasil hitungannya, backend
# yang menulis narasinya. Dibikin begini supaya API key Gemini tidak lagi ditaruh di
# admin-dashboard.html (dulu ikut terkirim ke browser semua orang yang buka dashboard).
class PesananAnalisis(BaseModel):
    nama: str = ""
    divisi: str = ""
    skor: int = 0
    maks: int = 0
    tier: str = ""
    done: int = 0
    progress: int = 0
    pending: int = 0
    blocked: int = 0
    total: int = 0
    rincian: str = ""
    daftar_task: list[str] = []

@app.post("/analisis-intern")
def endpoint_analisis_intern(pesanan: PesananAnalisis):
    try:
        return analisa_kinerja(pesanan.model_dump())
    except Exception:
        raise HTTPException(status_code=503, detail="Server AI sedang sibuk. Coba buka analisis lagi sebentar.")

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

# Pesanan untuk asisten sales BMS (chat customer + gambar CAD opsional)
class PesananBMS(BaseModel):
    chat: str = ""
    image_base64: str = ""         # gambar CAD dalam base64 (opsional)
    image_mime: str = "image/png"  # mis. image/png, image/jpeg
    riwayat: str = ""              # transkrip percakapan sebelumnya (untuk chat lanjutan)

# Loket asisten sales BMS: balikin informasi permintaan + rekomendasi respond
@app.post("/bms-sales")
def endpoint_bms_sales(pesanan: PesananBMS):
    return analisa_bms(pesanan.chat, pesanan.image_base64, pesanan.image_mime, pesanan.riwayat)

# Pesanan untuk sistem multi-agent penetrasi pasar (form terstruktur)
class PesananPenetrasi(BaseModel):
    nama_produk: str = ""
    deskripsi: str = ""
    target_market: str = ""
    lokasi: str = ""
    kompetitor: str = ""           # opsional
    budget: str = ""               # opsional
    tujuan: str = ""               # opsional

# Pesanan tahap 1: minta rekomendasi target market & lokasi (kalau user tak isi)
class PesananRekomendasi(BaseModel):
    nama_produk: str = ""
    deskripsi: str = ""
    target_market: str = ""        # kalau sudah diisi, tak diusulkan lagi
    lokasi: str = ""

# Loket rekomendasi: usulkan opsi target/lokasi (checkbox di frontend)
@app.post("/penetrasi-rekomendasi")
def endpoint_penetrasi_rekomendasi(pesanan: PesananRekomendasi):
    return rekomendasi_target(
        pesanan.nama_produk,
        pesanan.deskripsi,
        pesanan.target_market,
        pesanan.lokasi,
    )

# Loket penetrasi pasar: jalankan pipeline 10 agent + analytics, balikin semua hasil
@app.post("/penetrasi-market")
def endpoint_penetrasi(pesanan: PesananPenetrasi):
    return analisa_penetrasi(
        pesanan.nama_produk,
        pesanan.deskripsi,
        pesanan.target_market,
        pesanan.lokasi,
        pesanan.kompetitor,
        pesanan.budget,
        pesanan.tujuan,
    )

# Pesanan konten Instagram 4:5 (multi-agent: detailing/layouting/checker/checker-visual)
class PesananKontenIG(BaseModel):
    brief: str = ""
    jumlah: int = 0                # 0 = agent tentukan sendiri (1-5)
    produk_base64: str = ""        # foto produk untuk konten ini (opsional)
    produk_mime: str = "image/png"

@app.post("/konten-ig")
def endpoint_konten_ig(pesanan: PesananKontenIG):
    return buat_konten_ig(pesanan.brief, pesanan.jumlah, pesanan.produk_base64, pesanan.produk_mime)

# Pesanan asisten sales & service HOBO data logger (chat customer + file opsional)
class PesananHOBO(BaseModel):
    chat: str = ""
    image_base64: str = ""
    image_mime: str = "image/png"
    riwayat: str = ""             # transkrip percakapan sebelumnya (chat lanjutan)
    sebelumnya: dict | None = None  # hasil turn sebelumnya (untuk routing agent)

@app.post("/hobo-sales")
def endpoint_hobo_sales(pesanan: PesananHOBO):
    return analisa_hobo(pesanan.chat, pesanan.image_base64, pesanan.image_mime, pesanan.riwayat, pesanan.sebelumnya)

# Pesanan asisten sales & service alat Fakopp (uji pohon & kayu)
class PesananFakopp(BaseModel):
    chat: str = ""
    image_base64: str = ""
    image_mime: str = "image/png"
    riwayat: str = ""
    sebelumnya: dict | None = None

@app.post("/fakopp-sales")
def endpoint_fakopp_sales(pesanan: PesananFakopp):
    return analisa_fakopp(pesanan.chat, pesanan.image_base64, pesanan.image_mime, pesanan.riwayat, pesanan.sebelumnya)

# Pesanan asisten sales & service alat HMP (uji daya dukung & pemadatan tanah)
class PesananHMP(BaseModel):
    chat: str = ""
    image_base64: str = ""
    image_mime: str = "image/png"
    riwayat: str = ""
    sebelumnya: dict | None = None

@app.post("/hmp-sales")
def endpoint_hmp_sales(pesanan: PesananHMP):
    return analisa_hmp(pesanan.chat, pesanan.image_base64, pesanan.image_mime, pesanan.riwayat, pesanan.sebelumnya)

# Pesanan asisten sales & service TIMBANGAN (timbanganindonesia.com)
class PesananTimbangan(BaseModel):
    chat: str = ""
    image_base64: str = ""
    image_mime: str = "image/png"
    riwayat: str = ""
    sebelumnya: dict | None = None

@app.post("/timbangan-sales")
def endpoint_timbangan_sales(pesanan: PesananTimbangan):
    return analisa_timbangan(pesanan.chat, pesanan.image_base64, pesanan.image_mime, pesanan.riwayat, pesanan.sebelumnya)

# Pesanan asisten sales & service LOAD CELL (rajaloadcell.com)
class PesananLoadcell(BaseModel):
    chat: str = ""
    image_base64: str = ""
    image_mime: str = "image/png"
    riwayat: str = ""
    sebelumnya: dict | None = None

@app.post("/loadcell-sales")
def endpoint_loadcell_sales(pesanan: PesananLoadcell):
    return analisa_loadcell(pesanan.chat, pesanan.image_base64, pesanan.image_mime, pesanan.riwayat, pesanan.sebelumnya)

# Pesanan asisten sales & service sensor MICRO-EPSILON (micro-epsilon.com)
class PesananMicroepsilon(BaseModel):
    chat: str = ""
    image_base64: str = ""
    image_mime: str = "image/png"
    riwayat: str = ""
    sebelumnya: dict | None = None

@app.post("/microepsilon-sales")
def endpoint_microepsilon_sales(pesanan: PesananMicroepsilon):
    return analisa_microepsilon(pesanan.chat, pesanan.image_base64, pesanan.image_mime, pesanan.riwayat, pesanan.sebelumnya)
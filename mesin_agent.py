import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

CONTOH_FORMAT = """Konten Carousel Instagram — Realita Kehidupan Laboran
Jenis Konten: Entertaining / Relatable
Format: Carousel
Warna Dominan: Merah
Sumber/Referensi: Timbangan Laboratorium / https://timbanganindonesia.com/product/orion-series/

---
SLIDE 1 — Thumbnail
Visual:
- Ilustrasi karakter laboran yang bingung di depan timbangan.
Headline:
Momen "Dugaan" di Laboratorium
Sub Headline:
Saat Kamu Sudah Yakin, Tapi Angka Terus Berubah

---
SLIDE 2 — Penyebabnya Apa?
Visual:
- Foto timbangan dengan area kerja sedikit berantakan.
Headline:
Penyebab Drama Timbangan
Isi:
- Pintu Kaca Belum Tertutup Rapat: aliran udara memengaruhi hasil.

---
SLIDE 3 — Call To Action
Visual:
- Template CTA yang biasa digunakan."""


def baca_link(url):
    if not url:
        return "(tidak ada link referensi)"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        halaman = requests.get(url, headers=headers, timeout=20)
        sup = BeautifulSoup(halaman.text, "html.parser")
        return sup.get_text(separator=" ", strip=True)[:2000]
    except Exception as e:
        return f"(Gagal baca link: {e})"


def buat_brief_satu_platform(topik, link, isi_link, platform):
    perintah = f"""Kamu adalah content planner profesional untuk brand alat industri/laboratorium.
Buatkan brief konten untuk platform {platform}, untuk dikerjakan tim desain.

PENTING:
- Ikuti PERSIS format dan gaya dari contoh di bawah.
- Sesuaikan NUANSA dengan platform {platform}: kalau Instagram lebih santai/relatable, kalau LinkedIn lebih profesional dan informatif.
- Jangan menambah bagian "Tips Tambahan", "Caption", atau "Hashtag".
- Maksimal 5 slide (termasuk CTA). Umumnya 3-4 slide. Slide terakhir selalu CTA.
- Pada bagian "Sumber/Referensi", tulis link ini: {link}

=== CONTOH FORMAT YANG HARUS DIIKUTI ===
{CONTOH_FORMAT}
=== AKHIR CONTOH ===

=== INFORMASI PRODUK (hasil baca link, pakai untuk konteks isi) ===
{isi_link}
=== AKHIR INFORMASI PRODUK ===

Sekarang buat brief BARU dengan format sama persis untuk:
Topik: {topik}
Platform: {platform}
Pastikan isi nyambung dengan produk dari informasi di atas."""

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=perintah,
    )
    return response.text


def buat_brief(topik, link, daftar_platform):
    isi_link = baca_link(link)
    hasil = {}
    for platform in daftar_platform:
        hasil[platform] = buat_brief_satu_platform(topik, link, isi_link, platform)
    return hasil
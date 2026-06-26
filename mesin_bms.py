"""
Mesin AI untuk membantu tim SALES Building Management System (BMS).

Sales menempel chat customer (kadang + gambar CAD/denah). Agent menerjemahkan
kebutuhan teknis yang rumit jadi mudah dipahami, lalu memberi rekomendasi
balasan yang siap dipakai sales.
"""
import re
import json
import base64
import binascii

from mesin_agent import client  # reuse client Gemini yang sudah ada

try:
    from google.genai import types
except Exception:  # jaga-jaga kalau path import beda
    types = None


PROMPT_BMS = """Kamu adalah asisten teknis untuk tim SALES Building Management System (BMS).
Customer sering memakai bahasa teknis yang rumit, dan kadang melampirkan gambar CAD/denah yang sulit dipahami sales.

Tugasmu: baca chat customer (dan gambar CAD bila ada), lalu bantu sales memahaminya.

Hasilkan TEPAT 2 bagian dalam Bahasa Indonesia yang jelas dan ringkas (boleh pakai poin dengan tanda "-" dan baris baru):

1. informasi_permintaan: Terjemahkan & rangkum kebutuhan customer ke bahasa sederhana yang mudah dipahami sales. Sebutkan:
   - Apa yang sebenarnya diminta customer.
   - Sistem/perangkat BMS yang relevan (mis. HVAC, fire alarm, access control, CCTV, lighting control, sensor, controller, integrasi SCADA/Modbus/BACnet, dll).
   - Skala / lokasi / jumlah titik bila disebut, dan poin teknis penting dari gambar CAD bila ada.
   - Jika ada info yang kurang atau ambigu, tuliskan daftar pertanyaan klarifikasi yang perlu ditanyakan ke customer.

2. rekomendasi_respond: Saran balasan yang SIAP PAKAI untuk sales (sopan, profesional, ramah). Termasuk:
   - Konfirmasi pemahaman atas permintaan.
   - Pertanyaan klarifikasi yang perlu diajukan.
   - Solusi / produk yang relevan untuk ditawarkan.
   - Langkah selanjutnya (mis. minta dokumen/spesifikasi, jadwalkan survei, kirim penawaran).

Jika gambar CAD tidak terbaca jelas, katakan terus terang dan minta sales mengonfirmasi, jangan mengarang.

Kembalikan HANYA JSON valid (tanpa backtick, tanpa teks lain):
{"informasi_permintaan":"...", "rekomendasi_respond":"..."}"""


def analisa_bms(chat, image_base64="", image_mime="image/png"):
    chat = (chat or "").strip()

    isi = PROMPT_BMS + "\n\n=== CHAT CUSTOMER ===\n" + (chat if chat else "(tidak ada teks chat)")

    contents = [isi]

    # Lampirkan gambar CAD (opsional)
    if image_base64 and types is not None:
        try:
            img_bytes = base64.b64decode(image_base64)
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=image_mime or "image/png"))
        except (binascii.Error, ValueError):
            pass  # gambar rusak → lanjut tanpa gambar

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=contents,
    )

    txt = re.sub(r"```json|```", "", response.text or "").strip()
    try:
        data = json.loads(txt)
    except Exception:
        # fallback kalau model tidak balas JSON rapi
        data = {"informasi_permintaan": response.text or "", "rekomendasi_respond": ""}

    return {
        "informasi_permintaan": (data.get("informasi_permintaan") or "").strip(),
        "rekomendasi_respond":  (data.get("rekomendasi_respond") or "").strip(),
    }

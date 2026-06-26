"""
Mesin AI untuk membantu tim SALES Building Management System (BMS).

Sales menempel chat customer (kadang + gambar CAD/denah). Agent menerjemahkan
kebutuhan teknis yang rumit jadi mudah dipahami, lalu memberi rekomendasi
balasan yang siap dipakai sales.
"""
import re
import os
import json
import base64
import binascii

import requests

from mesin_agent import client  # reuse client Gemini yang sudah ada

CC_API = "https://api.cloudconvert.com/v2"

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


def _is_dwg(b):
    # DWG diawali signature "AC10xx" (mis. AC1027, AC1032)
    return len(b) >= 6 and b[:2] == b"AC" and b[2:6].isdigit()


def _dwg_to_pdf_cloudconvert(dwg_bytes):
    """Konversi DWG -> PDF via CloudConvert. Butuh env CLOUDCONVERT_API_KEY."""
    api_key = os.getenv("CLOUDCONVERT_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CLOUDCONVERT_API_KEY belum diset di Secret backend")
    H = {"Authorization": "Bearer " + api_key}

    # 1) Buat job: upload -> convert(dwg->pdf) -> export url
    job = {"tasks": {
        "imp":  {"operation": "import/upload"},
        "conv": {"operation": "convert", "input": "imp", "input_format": "dwg", "output_format": "pdf"},
        "exp":  {"operation": "export/url", "input": "conv"},
    }}
    r = requests.post(CC_API + "/jobs", json=job, headers=H, timeout=60)
    r.raise_for_status()
    tasks = r.json()["data"]["tasks"]
    imp = next(t for t in tasks if t["name"] == "imp")
    exp = next(t for t in tasks if t["name"] == "exp")

    # 2) Upload file DWG ke form yang diberikan CloudConvert
    form = imp["result"]["form"]
    up = requests.post(form["url"], data=form["parameters"],
                       files={"file": ("drawing.dwg", dwg_bytes)}, timeout=180)
    up.raise_for_status()

    # 3) Tunggu task export selesai (long-poll), lalu unduh PDF
    w = requests.get(CC_API + "/tasks/" + exp["id"] + "/wait", headers=H, timeout=300)
    w.raise_for_status()
    task = w.json()["data"]
    if task.get("status") != "finished":
        raise RuntimeError("CloudConvert gagal: " + str(task.get("message") or task.get("status")))
    pdf_url = task["result"]["files"][0]["url"]
    pdf = requests.get(pdf_url, timeout=180)
    pdf.raise_for_status()
    return pdf.content


def analisa_bms(chat, image_base64="", image_mime="image/png"):
    chat = (chat or "").strip()

    isi = PROMPT_BMS + "\n\n=== CHAT CUSTOMER ===\n" + (chat if chat else "(tidak ada teks chat)")

    contents = [isi]

    # Lampirkan file CAD (gambar / PDF / DWG) — opsional
    if image_base64 and types is not None:
        try:
            file_bytes = base64.b64decode(image_base64)
        except (binascii.Error, ValueError):
            file_bytes = None

        if file_bytes:
            mime = image_mime or "image/png"
            # Kalau DWG: konversi dulu ke PDF via CloudConvert
            if _is_dwg(file_bytes) or (image_mime or "").lower().find("dwg") != -1:
                try:
                    file_bytes = _dwg_to_pdf_cloudconvert(file_bytes)
                    mime = "application/pdf"
                except Exception as e:
                    contents[0] += ("\n\n(CATATAN: file DWG gagal dikonversi otomatis: "
                                    + str(e)[:150] + ". Analisa hanya dari teks; minta sales kirim PDF/gambar.)")
                    file_bytes = None

            if file_bytes:
                contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime))

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

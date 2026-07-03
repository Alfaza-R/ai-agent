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
    if r.status_code >= 400:
        raise RuntimeError("buat job " + str(r.status_code) + ": " + r.text[:300])
    tasks = r.json()["data"]["tasks"]
    imp = next(t for t in tasks if t["name"] == "imp")
    exp = next(t for t in tasks if t["name"] == "exp")

    # 2) Upload file DWG ke form yang diberikan CloudConvert
    form = imp["result"]["form"]
    up = requests.post(form["url"], data=form["parameters"],
                       files={"file": ("drawing.dwg", dwg_bytes)}, timeout=180)
    if up.status_code >= 400:
        raise RuntimeError("upload " + str(up.status_code) + ": " + up.text[:200])

    # 3) Tunggu task export selesai (long-poll), lalu unduh PDF
    w = requests.get(CC_API + "/tasks/" + exp["id"] + "/wait", headers=H, timeout=300)
    if w.status_code >= 400:
        raise RuntimeError("wait " + str(w.status_code) + ": " + w.text[:200])
    task = w.json()["data"]
    if task.get("status") != "finished":
        raise RuntimeError("convert gagal: " + str(task.get("message") or task.get("status")))
    pdf_url = task["result"]["files"][0]["url"]
    pdf = requests.get(pdf_url, timeout=180)
    if pdf.status_code >= 400:
        raise RuntimeError("download pdf " + str(pdf.status_code))
    return pdf.content


def _gen(prompt, file_bytes=None, mime=None):
    contents = [prompt]
    if file_bytes and types is not None:
        contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime or "image/png"))
    resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=contents)
    return (resp.text or "").strip()


def _json(txt, fallback):
    t = re.sub(r"```json|```", "", txt or "").strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, dict) else fallback
    except Exception:
        return fallback


# ── Agent 1: Reader teks ──────────────────────────────────────────────
def _agent_reader_teks(chat):
    if not chat:
        return "(Tidak ada teks chat dari customer.)"
    prompt = (
        "Kamu Agent Reader (teks) untuk tim sales BMS. Baca chat customer, lalu ekstrak SEMUA info penting "
        "secara terstruktur (poin '-'): permintaan/kebutuhan, sistem/perangkat yang disebut (HVAC, fire alarm, "
        "CCTV, access control, lighting, sensor, controller, protokol BACnet/Modbus/SCADA, dll), skala/lokasi/"
        "jumlah titik, budget/timeline bila ada, serta hal yang ambigu/kurang jelas. JANGAN menyimpulkan solusi, "
        "hanya rangkum yang tertulis.\n\n=== CHAT CUSTOMER ===\n" + chat
    )
    return _gen(prompt)


# ── Agent 2: Reader visual (gambar / CAD / PDF) ───────────────────────
def _agent_reader_visual(file_bytes, mime):
    if not file_bytes:
        return "(Tidak ada gambar/CAD/PDF dari customer.)"
    prompt = (
        "Kamu Agent Reader (visual) untuk tim sales BMS. Baca gambar/CAD/PDF terlampir (denah/skema/diagram). "
        "Ekstrak info teknis terstruktur (poin '-'): jenis gambar (denah lantai, single-line diagram, diagram "
        "sistem, dll), sistem/perangkat yang terlihat, titik/zona/jumlah unit, label/anotasi/legenda penting, "
        "skala/dimensi bila ada. Kalau ada bagian tidak terbaca, katakan jujur. JANGAN mengarang."
    )
    return _gen(prompt, file_bytes, mime)


# ── Agent 3: Checker (konsistensi teks vs visual) ─────────────────────
def _agent_checker(teks_info, visual_info):
    prompt = (
        "Kamu Agent Checker untuk tim sales BMS. Bandingkan & satukan dua sumber info di bawah "
        "(dari teks customer & dari gambar/CAD). Tugasmu: cek konsistensi, temukan MISS/ambiguitas/kontradiksi "
        "antara teks dan gambar, lalu susun daftar informasi final yang sudah diverifikasi.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): "
        "{\"info_terverifikasi\":\"ringkasan poin yang sudah dicek\", \"inkonsistensi\":[\"...\"], "
        "\"pertanyaan_klarifikasi\":[\"...\"]}\n\n"
        "=== INFO DARI TEKS ===\n" + teks_info + "\n\n=== INFO DARI GAMBAR/CAD ===\n" + visual_info
    )
    return _json(_gen(prompt), {
        "info_terverifikasi": teks_info + "\n" + visual_info,
        "inkonsistensi": [], "pertanyaan_klarifikasi": [],
    })


# ── Agent 4: Result (2 output: awam & teknis) ─────────────────────────
def _agent_result(checker):
    info  = checker.get("info_terverifikasi", "") or ""
    inkon = checker.get("inkonsistensi", []) or []
    tanya = checker.get("pertanyaan_klarifikasi", []) or []
    prompt = (
        "Kamu Agent Result untuk tim sales BMS. Berdasarkan info terverifikasi + catatan di bawah, buat DUA output "
        "dalam Bahasa Indonesia:\n"
        "1. output_awam: penjelasan singkat + rekomendasi balasan untuk SALES yang tidak teknis (bahasa sederhana, "
        "siap dipakai membalas customer).\n"
        "2. output_technical: rangkuman teknis mendetail untuk tim teknik/engineer (sistem, perangkat, protokol, "
        "titik/zona, poin dari CAD, spesifikasi, dan pertanyaan teknis yang perlu).\n"
        "Sertakan pertanyaan klarifikasi bila ada. JANGAN mengarang di luar data.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"output_awam\":\"...\", \"output_technical\":\"...\"}\n\n"
        "=== INFO TERVERIFIKASI ===\n" + info +
        "\n\n=== INKONSISTENSI/CATATAN ===\n" + ("; ".join(map(str, inkon)) or "-") +
        "\n\n=== PERTANYAAN KLARIFIKASI ===\n" + ("; ".join(map(str, tanya)) or "-")
    )
    return _json(_gen(prompt), {"output_awam": "", "output_technical": ""})


def analisa_bms(chat, image_base64="", image_mime="image/png"):
    chat = (chat or "").strip()
    dwg_error = ""
    file_bytes = None
    mime = None

    # Siapkan file (gambar / PDF / DWG->PDF) — opsional
    if image_base64 and types is not None:
        try:
            file_bytes = base64.b64decode(image_base64)
        except (binascii.Error, ValueError):
            file_bytes = None
        if file_bytes:
            mime = image_mime or "image/png"
            if _is_dwg(file_bytes) or (image_mime or "").lower().find("dwg") != -1:
                try:
                    file_bytes = _dwg_to_pdf_cloudconvert(file_bytes)
                    mime = "application/pdf"
                except Exception as e:
                    dwg_error = str(e)
                    file_bytes = None

    # ── Pipeline multi-agent ──
    teks_info   = _agent_reader_teks(chat)
    visual_info = _agent_reader_visual(file_bytes, mime)
    checker     = _agent_checker(teks_info, visual_info)
    hasil       = _agent_result(checker)

    return {
        "output_awam":            (hasil.get("output_awam") or "").strip(),
        "output_technical":       (hasil.get("output_technical") or "").strip(),
        "inkonsistensi":          checker.get("inkonsistensi", []) or [],
        "pertanyaan_klarifikasi": checker.get("pertanyaan_klarifikasi", []) or [],
        "konversi_error":         dwg_error,
    }

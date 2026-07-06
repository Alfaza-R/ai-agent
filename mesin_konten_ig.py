"""
Mesin AI multi-agent untuk KONTEN INSTAGRAM (format 4:5).

Agent:
- Detailing      : dari brief -> arahan detail per slide untuk layouting.
- Layouting      : susun layout tiap slide, ambil aset dari folder GitHub milik user.
- Checker        : KOORDINATOR — cek konsistensi brief/detailing/layouting, kirim koreksi.
- Checker Visual  : bandingkan rencana layout dengan REFERENSI design (folder GitHub), beri feedback.

Referensi & aset diambil dari folder GitHub:
  agent-konten-ig/aset/       -> aset yang ditempel ke layout
  agent-konten-ig/referensi/  -> contoh design acuan

Output: daftar 1-5 "slide spec". Gambar 4:5 final dirender di browser (html2canvas).
Background bertipe "generate" dibuat via model image Gemini bila Secret GEMINI_IMAGE_MODEL diisi
(kalau tidak, otomatis fallback ke warna/gradient/aset — tetap jalan di free tier).
"""
import os
import re
import json
import base64

import requests

from mesin_agent import client

try:
    from google.genai import types
except Exception:
    types = None

MODEL = "gemini-3.1-flash-lite"
IMG_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "").strip()  # mis. "gemini-3-pro-image" (opsional, berbayar)

# Repo GitHub sumber aset & referensi
GH_REPO = os.getenv("KONTEN_GH_REPO", "Alfaza-R/ai-agent").strip()
GH_BRANCH = os.getenv("KONTEN_GH_BRANCH", "main").strip()
GH_DIR_ASET = "agent-konten-ig/aset"
GH_DIR_REF = "agent-konten-ig/referensi"
_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


# ── GitHub: list & unduh gambar dari folder ───────────────────────────
def _github_list(folder):
    """Kembalikan [{name, url}] gambar di folder repo (public, tanpa auth)."""
    url = "https://api.github.com/repos/" + GH_REPO + "/contents/" + folder + "?ref=" + GH_BRANCH
    try:
        r = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=30)
        if r.status_code >= 400:
            return []
        out = []
        for it in r.json():
            if it.get("type") == "file" and it.get("name", "").lower().endswith(_IMG_EXT):
                out.append({"name": it["name"], "url": it.get("download_url", "")})
        return out
    except Exception:
        return []


def _fetch_bytes(url):
    try:
        r = requests.get(url, timeout=30)
        if r.status_code < 400:
            ct = r.headers.get("Content-Type", "image/png")
            mime = ct.split(";")[0].strip() or "image/png"
            return r.content, mime
    except Exception:
        pass
    return None, None


# ── Helper generik ────────────────────────────────────────────────────
def _gen(prompt, images=None):
    contents = [prompt]
    if images and types is not None:
        for b, m in images:
            if b:
                contents.append(types.Part.from_bytes(data=b, mime_type=m or "image/png"))
    resp = client.models.generate_content(model=MODEL, contents=contents)
    return (resp.text or "").strip()


def _json(txt, fallback):
    t = re.sub(r"```json|```", "", txt or "").strip()
    try:
        d = json.loads(t)
        return d if isinstance(d, (dict, list)) else fallback
    except Exception:
        return fallback


def _gen_image(prompt):
    """Generate gambar via model image Gemini. Return base64 PNG atau '' (fallback)."""
    if not IMG_MODEL or types is None:
        return ""
    try:
        cfg = types.GenerateContentConfig(response_modalities=["IMAGE"])
        resp = client.models.generate_content(model=IMG_MODEL, contents=[prompt], config=cfg)
        for cand in (resp.candidates or []):
            for part in (cand.content.parts or []):
                data = getattr(getattr(part, "inline_data", None), "data", None)
                if data:
                    if isinstance(data, bytes):
                        return base64.b64encode(data).decode()
                    return str(data)  # sebagian SDK sudah base64 string
    except Exception:
        pass
    return ""


# ── Agent Detailing ───────────────────────────────────────────────────
def _agent_detailing(brief, jumlah, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB) ===\n" + koreksi) if koreksi else ""
    jml = ("Buat tepat " + str(jumlah) + " slide.") if jumlah else "Tentukan jumlah slide 1-5 sesuai kebutuhan brief."
    prompt = (
        "Kamu Agent Detailing untuk konten Instagram (format 4:5). Dari brief di bawah, buat ARAHAN DETAIL per slide "
        "yang akan dipakai Agent Layouting.\n" + jml + "\n"
        "Tiap slide tentukan: peran (cover/isi/cta), headline, subteks, poin isi (bila ada), CTA (bila slide cta), "
        "mood/nuansa, saran warna dominan, dan arahan visual singkat (aset seperti apa yang cocok).\n"
        "Bahasa Indonesia, ringkas & konkret. JANGAN mengarang klaim yang tak ada di brief.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"jumlah_slide\": N, \"slides\": [ {\"peran\":\"cover/isi/cta\", \"headline\":\"...\", \"subteks\":\"...\", "
        "\"poin\":[\"...\"], \"cta\":\"...\", \"mood\":\"...\", \"warna\":\"#hex atau nama\", \"arahan_visual\":\"...\"} ] }\n\n"
        "=== BRIEF ===\n" + brief + fb
    )
    d = _json(_gen(prompt), {"jumlah_slide": 0, "slides": []})
    return d if isinstance(d, dict) else {"jumlah_slide": 0, "slides": []}


# ── Agent Layouting ───────────────────────────────────────────────────
def _agent_layouting(detailing, aset_list, koreksi=""):
    fb = ("\n\n=== KOREKSI (WAJIB) ===\n" + koreksi) if koreksi else ""
    daftar_aset = "\n".join("- " + a["name"] for a in aset_list) or "(tidak ada aset — pakai warna/gradient)"
    prompt = (
        "Kamu Agent Layouting konten Instagram 4:5 (1080x1350). Dari arahan Detailing di bawah, susun LAYOUT tiap slide.\n"
        "Kamu HANYA boleh memakai aset gambar dari DAFTAR ASET (sebut persis nama filenya). Kalau tidak ada aset yang cocok, "
        "pakai background 'warna' atau 'gradient', atau 'generate' (bila ingin ilustrasi AI).\n"
        "Untuk tiap slide tentukan background + elemen teks beserta posisi & gaya. Pastikan teks terbaca (kontras dengan bg).\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"slides\": [ {"
        "\"bg_tipe\":\"aset|warna|gradient|generate\", "
        "\"bg_aset\":\"nama file dari daftar (bila bg_tipe=aset)\", "
        "\"bg_warna\":\"#hex (bila warna)\", "
        "\"bg_gradient\":[\"#hex\",\"#hex\"] , "
        "\"bg_generate_prompt\":\"deskripsi gambar (bila generate)\", "
        "\"overlay\": true, "
        "\"aset_tempel\":\"nama file aset yang ditempel sebagai foto (opsional)\", "
        "\"teks\": [ {\"isi\":\"...\", \"peran\":\"headline|sub|body|cta\", \"posisi\":\"atas|tengah|bawah\", "
        "\"align\":\"kiri|tengah|kanan\", \"warna\":\"#hex\", \"ukuran\":\"besar|sedang|kecil\"} ] } ] }\n\n"
        "=== DAFTAR ASET (pakai nama persis) ===\n" + daftar_aset +
        "\n\n=== ARAHAN DETAILING ===\n" + json.dumps(detailing, ensure_ascii=False) + fb
    )
    d = _json(_gen(prompt), {"slides": []})
    return d if isinstance(d, dict) else {"slides": []}


# ── Agent Checker (KOORDINATOR) ───────────────────────────────────────
def _agent_checker(brief, detailing, layout):
    prompt = (
        "Kamu Agent Checker (KOORDINATOR) konten IG. Pastikan brief -> detailing -> layouting SALING KONSISTEN.\n"
        "Cek: apakah semua pesan penting di brief masuk? apakah layouting sesuai arahan detailing? apakah teks tiap slide "
        "lengkap & tidak ada slide kosong? apakah aset yang dipakai masuk akal?\n"
        "Kalau ADA yang salah, tulis instruksi koreksi spesifik untuk agent terkait.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"konsisten\": true/false, \"koreksi_detailing\":\"(kosong bila ok)\", \"koreksi_layouting\":\"(kosong bila ok)\", "
        "\"catatan\":[\"...\"] }\n\n"
        "=== BRIEF ===\n" + brief +
        "\n\n=== DETAILING ===\n" + json.dumps(detailing, ensure_ascii=False) +
        "\n\n=== LAYOUTING ===\n" + json.dumps(layout, ensure_ascii=False)
    )
    return _json(_gen(prompt), {"konsisten": True, "koreksi_detailing": "", "koreksi_layouting": "", "catatan": []})


# ── Agent Checker Visual ──────────────────────────────────────────────
def _agent_checker_visual(layout, ref_images):
    if not ref_images:
        return {"sesuai": True, "koreksi_layouting": "", "feedback": ["(Tidak ada referensi design — checker visual dilewati.)"]}
    prompt = (
        "Kamu Agent Checker Visual konten IG. Ada beberapa gambar REFERENSI DESIGN terlampir (acuan gaya). "
        "Nilai apakah RENCANA LAYOUT di bawah (warna, komposisi, gaya teks) SUDAH SEJALAN dengan gaya referensi.\n"
        "Kalau belum sejalan, beri instruksi koreksi konkret untuk Agent Layouting (mis. samakan palet warna, posisi teks, "
        "gaya font, penggunaan whitespace).\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{ \"sesuai\": true/false, \"koreksi_layouting\":\"(kosong bila sudah sesuai)\", \"feedback\":[\"...\"] }\n\n"
        "=== RENCANA LAYOUT ===\n" + json.dumps(layout, ensure_ascii=False)
    )
    imgs = [(b, m) for (b, m) in ref_images]
    return _json(_gen(prompt, imgs), {"sesuai": True, "koreksi_layouting": "", "feedback": []})


# ── Normalisasi & generate background ─────────────────────────────────
def _aset_url(aset_list, name):
    for a in aset_list:
        if a["name"] == name:
            return a["url"]
    return ""


def _finalize_slides(layout, aset_list):
    slides = []
    for s in (layout.get("slides") or []):
        if not isinstance(s, dict):
            continue
        bg_tipe = (s.get("bg_tipe") or "warna").lower()
        slide = {
            "bg_tipe": bg_tipe,
            "bg_warna": s.get("bg_warna") or "#111827",
            "bg_gradient": s.get("bg_gradient") if isinstance(s.get("bg_gradient"), list) else [],
            "bg_aset_url": _aset_url(aset_list, s.get("bg_aset") or ""),
            "aset_tempel_url": _aset_url(aset_list, s.get("aset_tempel") or ""),
            "overlay": bool(s.get("overlay", bg_tipe in ("aset", "generate"))),
            "bg_generate_b64": "",
            "teks": [t for t in (s.get("teks") or []) if isinstance(t, dict) and (t.get("isi"))],
        }
        # Generative background (opsional, hanya bila model image diset)
        if bg_tipe == "generate":
            b64 = _gen_image((s.get("bg_generate_prompt") or "") + " — vertical 4:5 Instagram background, high quality")
            if b64:
                slide["bg_generate_b64"] = b64
            else:
                slide["bg_tipe"] = "gradient"
                if not slide["bg_gradient"]:
                    slide["bg_gradient"] = ["#6d28d9", "#2563eb"]
        slides.append(slide)
    return slides


# ── PIPELINE UTAMA ────────────────────────────────────────────────────
def buat_konten_ig(brief="", jumlah=0):
    brief = (brief or "").strip()
    try:
        jumlah = int(jumlah or 0)
    except (TypeError, ValueError):
        jumlah = 0
    if jumlah:
        jumlah = max(1, min(5, jumlah))

    # Ambil aset & referensi dari GitHub
    aset_list = _github_list(GH_DIR_ASET)
    ref_list = _github_list(GH_DIR_REF)
    ref_images = []
    for r in ref_list[:6]:
        b, m = _fetch_bytes(r["url"])
        if b:
            ref_images.append((b, m))

    # 1) Detailing + Layouting + Checker (koordinator) — loop maks 2
    kor_d = kor_l = ""
    detailing = layout = {}
    checker = {}
    for _ in range(2):
        detailing = _agent_detailing(brief, jumlah, kor_d)
        layout = _agent_layouting(detailing, aset_list, kor_l)
        checker = _agent_checker(brief, detailing, layout)
        if checker.get("konsisten", True):
            break
        kor_d = checker.get("koreksi_detailing", "") or ""
        kor_l = checker.get("koreksi_layouting", "") or ""
        if not kor_d and not kor_l:
            break

    # 2) Checker Visual — bandingkan dengan referensi; bila perlu, revisi layout sekali
    visual = _agent_checker_visual(layout, ref_images)
    if not visual.get("sesuai", True) and (visual.get("koreksi_layouting") or ""):
        layout = _agent_layouting(detailing, aset_list, visual.get("koreksi_layouting", ""))

    # 3) Finalisasi slide (+ generate bg bila diaktifkan)
    slides = _finalize_slides(layout, aset_list)

    return {
        "detailing":       detailing,
        "layout":          layout,
        "checker":         checker,
        "checker_visual":  visual,
        "slides":          slides,
        "jumlah_aset":     len(aset_list),
        "jumlah_referensi": len(ref_list),
        "generative_aktif": bool(IMG_MODEL),
    }

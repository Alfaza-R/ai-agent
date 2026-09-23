"""
Brief Checker — agent QC untuk hasil Content Planner.

Memeriksa brief:
- Jumlah slide minimal 3 (dihitung di kode).
- Detail Visual tiap slide cukup rinci & background bukan polos/abstrak (dicek di kode).
- Antar-slide nyambung & satu alur (slide 1 -> 2 -> dst tidak loncat topik).
- Deskripsi Visual (instruksi gambar) sesuai dengan Headline/teks tiap slide.
- Seluruh isi relevan dengan topik.

Kalau ada masalah, agent memerintahkan rewrite (maks 3 putaran).
"""
import re
import json

from mesin_agent import panggil_gemini  # pemanggil Gemini dengan retry + model cadangan


def _json_valid(teks):
    try:
        json.loads(re.sub(r"```json|```", "", teks).strip())
        return True
    except Exception:
        return False


def _periksa(brief_html, topik, platform):
    prompt = (
        f"Kamu QC editor untuk brief konten media sosial platform {platform}, topik \"{topik}\".\n\n"
        "Periksa brief HTML di bawah pada 4 aspek:\n"
        "1. KOHERENSI ANTAR-SLIDE: apakah slide mengalir satu alur logis (slide 1 -> 2 -> dst membahas tema yang sama, tidak loncat topik).\n"
        "2. VISUAL vs TEKS: apakah deskripsi 'Visual' (instruksi gambar) tiap slide SESUAI dengan Headline/Isi teks slide itu.\n"
        "3. RELEVANSI TOPIK: apakah seluruh isi relevan dengan topik di atas.\n"
        "4. DETAIL VISUAL & BACKGROUND: apakah Visual tiap slide cukup spesifik untuk langsung dieksekusi desainer "
        "(objek/model produk persis, lokasi nyata, orang & aksinya, properti, sudut kamera, pencahayaan), dan "
        "background berupa scene nyata yang relevan — BUKAN background polos/warna solid/gradasi/elemen abstrak. "
        "Warna dominan seharusnya jadi aksen/nuansa, bukan background polos.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"konsisten\": true/false, \"masalah\": [\"masalah konkret (sebut slide & apa yang salah)\", \"...\"]}\n"
        "Set \"konsisten\": false bila ADA masalah berarti.\n\n"
        "=== BRIEF ===\n" + (brief_html or "")
    )
    try:
        teks = panggil_gemini(prompt, validasi=_json_valid)
        data = json.loads(re.sub(r"```json|```", "", teks).strip())
        return {
            "konsisten": bool(data.get("konsisten", True)),
            "masalah": data.get("masalah", []) if isinstance(data.get("masalah"), list) else [],
        }
    except Exception:
        # Kalau gagal menilai, anggap konsisten supaya tidak mengganggu alur generate
        return {"konsisten": True, "masalah": []}


def _rewrite(brief_html, topik, platform, masalah):
    daftar = "\n".join("- " + str(m) for m in masalah) or "- (perbaiki koherensi umum)"
    prompt = (
        f"Kamu content editor. Perbaiki brief HTML berikut (platform {platform}, topik \"{topik}\") agar:\n"
        "- Antar-slide nyambung & satu alur.\n"
        "- Deskripsi Visual cocok dengan teks tiap slide.\n"
        "- Semua isi relevan dengan topik.\n\n"
        "MASALAH yang HARUS diperbaiki:\n" + daftar + "\n\n"
        "ATURAN VISUAL (wajib di setiap slide, termasuk CTA): Visual berupa 5 bullet berlabel \"Jenis visual\", "
        "\"Objek utama\", \"Latar/suasana\", \"Elemen pendukung\", \"Komposisi & warna\" — spesifik (nama/model produk "
        "persis, lokasi nyata, orang & aksinya, properti, sudut kamera, pencahayaan, area teks). Warna Dominan hanya "
        "jadi AKSEN/NUANSA; background WAJIB scene nyata yang relevan, DILARANG background polos/warna solid/gradasi/"
        "elemen abstrak.\n"
        "PERTAHANKAN format & struktur HTML: <h1> untuk judul narasi, <h2> untuk tiap slide, "
        "<ul><li> untuk poin/Visual, slide terakhir tetap Call To Action. JANGAN ubah/hapus nama brand di judul "
        "(<h1>) maupun field \"Warna Dominan\" kalau sudah ada — pertahankan persis. "
        "Jangan menambah penjelasan/komentar apa pun.\n"
        "Kembalikan HANYA HTML brief yang sudah diperbaiki (tanpa backtick).\n\n"
        "=== BRIEF LAMA ===\n" + (brief_html or "")
    )
    try:
        teks = panggil_gemini(prompt, validasi=lambda t: "<h2" in t.lower())
    except Exception:
        return brief_html  # rewrite gagal -> pertahankan brief lama (loop di pemanggil otomatis berhenti)
    out = re.sub(r"^```html|^```|```$", "", teks, flags=re.MULTILINE).strip()
    return out or brief_html


def _hitung_slide(brief_html):
    """Hitung jumlah slide dari heading <h2> (tiap slide = 1 <h2>). Deterministik di kode
    (bukan tanya AI) -> tidak bergantung AI sadar sendiri kalau slide-nya kurang."""
    return len(re.findall(r"<h2\b", brief_html or "", re.IGNORECASE))


def _teks_polos(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


MIN_KATA_VISUAL = 35

# Frasa yang menandakan visual mengarah ke background polos/abstrak, bukan scene nyata.
_POLA_BG_POLOS = re.compile(
    r"\b(polos|abstrak|abstract|warna solid|solid colou?r|gradasi|gradien|gradient|"
    r"(?:background|latar(?: belakang)?)\s+(?:berwarna|warna)\b)",
    re.IGNORECASE,
)


def _cek_visual(brief_html):
    """Cek DETERMINISTIK (di kode, bukan tanya AI) tiap slide: Visual ada, cukup rinci
    (>= MIN_KATA_VISUAL kata), dan tidak mengarah ke background polos/abstrak.
    Return daftar masalah (kosong kalau semua aman)."""
    potongan = re.split(r"(<h2\b[^>]*>.*?</h2>)", brief_html or "", flags=re.IGNORECASE | re.DOTALL)
    masalah = []
    for i in range(1, len(potongan), 2):
        judul = _teks_polos(potongan[i]) or f"Slide {(i + 1) // 2}"
        isi = potongan[i + 1] if i + 1 < len(potongan) else ""
        m = re.search(r"Visual\s*:?\s*</strong>.*?<ul\b[^>]*>(.*?)</ul>", isi, flags=re.IGNORECASE | re.DOTALL)
        if not m:
            masalah.append(f"{judul}: belum ada deskripsi Visual — tambahkan 5 bullet Visual yang rinci.")
            continue
        visual = _teks_polos(m.group(1))
        jumlah_kata = len(visual.split())
        if jumlah_kata < MIN_KATA_VISUAL:
            masalah.append(
                f"{judul}: deskripsi Visual terlalu umum ({jumlah_kata} kata) — rinci jadi Jenis visual, Objek utama, "
                "Latar/suasana, Elemen pendukung, Komposisi & warna."
            )
        polos = next(
            (p for p in _POLA_BG_POLOS.finditer(visual)
             # abaikan kalau didahului negasi, mis. "bukan background polos", "hindari gradasi"
             if not re.search(r"\b(bukan|tanpa|hindari|jangan|tidak|dilarang)\b(\s+\S+){0,3}\s*$",
                              visual[:p.start()], re.IGNORECASE)),
            None,
        )
        if polos:
            masalah.append(
                f"{judul}: Visual mengarah ke background polos/abstrak (\"{polos.group(0)}\") — ganti dengan scene "
                "nyata yang relevan; warna dominan cukup jadi aksen/nuansa."
            )
    return masalah


def periksa_dan_perbaiki(brief_html, topik, platform, maks=2):
    """Cek jumlah slide minimal 3 & detail visual/background (deterministik, di kode) lalu
    koherensi (via AI); rewrite kalau perlu (maksimal `maks` putaran).

    QC AI (_periksa) dijalankan CUKUP SEKALI per brief. Dulu dipanggil ulang tiap putaran:
    untuk 3 brief jadi 11 panggilan (±46 detik) — penyumbang lambat terbesar, sampai
    permintaan sering terputus batas waktu hosting."""
    hasil = brief_html
    qc_sudah = False
    for _ in range(maks):
        masalah = []
        jumlah_slide = _hitung_slide(hasil)
        if jumlah_slide < 3:
            masalah.append(
                f"Cuma ada {jumlah_slide} slide, WAJIB minimal 3 slide (termasuk CTA). Tambah slide BARU yang "
                "relevan dengan topik (jangan cuma menambah CTA duplikat)."
            )
        masalah += _cek_visual(hasil)

        if not masalah:
            if qc_sudah:
                break
            cek = _periksa(hasil, topik, platform)
            qc_sudah = True
            if cek["konsisten"]:
                break
            masalah = cek["masalah"]

        baru = _rewrite(hasil, topik, platform, masalah)
        if not baru or baru.strip() == (hasil or "").strip():
            break
        hasil = baru
    return hasil


# ── Checker ANTAR-konten ───────────────────────────────────────────────
# Beda dari periksa_dan_perbaiki() di atas (yang cek 1 brief secara internal):
# ini membandingkan SEMUA brief hasil 1 permintaan (platform yang sama, jumlah > 1)
# supaya tidak ada 2+ brief yang SUBSTANSINYA sama walau kalimatnya beda.
def cek_kemiripan_antar_konten(topik, platform, daftar_brief):
    """
    daftar_brief: list of {"sudut":..., "isi": html}.
    Return {"ada_duplikat_makna": bool, "instruksi_revisi": {"<index>": "instruksi spesifik"}}.
    """
    if not isinstance(daftar_brief, list) or len(daftar_brief) < 2:
        return {"ada_duplikat_makna": False, "instruksi_revisi": {}}

    daftar_teks = "\n\n".join(
        f"=== KONTEN #{i} (sudut: {b.get('sudut', 'Umum')}) ===\n{b.get('isi', '')}"
        for i, b in enumerate(daftar_brief)
    )
    prompt = (
        f"Kamu QC editor untuk {len(daftar_brief)} brief konten platform {platform}, topik \"{topik}\", yang "
        "dihasilkan dari SATU permintaan yang sama — tujuannya jadi ide konten yang BENAR-BENAR BERBEDA, bukan "
        "variasi kalimat dari ide yang sama.\n\n"
        "Baca semua konten di bawah, bandingkan satu sama lain. Fokus ke SUBSTANSI (tips/fakta/sudut pandang/pesan "
        "inti yang disampaikan), BUKAN sekadar mirip kalimat. Dua konten dianggap TERLALU MIRIP kalau inti pesannya "
        "sama (mis. sama-sama membahas 'kebersihan alat' walau headline & kalimatnya beda), sehingga kalau dipasang "
        "bersebelahan di feed terasa mengulang.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{\"ada_duplikat_makna\": true/false, "
        "\"instruksi_revisi\": {\"<index_konten_yang_perlu_ditulis_ulang>\": \"instruksi spesifik: sebutkan konten "
        "mana yang inti-nya sama, apa inti konten yang sudah dipakai, dan arahkan ke sudut/informasi BARU yang "
        "belum dibahas konten lain\"}}\n"
        "Kalau ada kelompok >2 yang mirip, sisakan SATU yang paling kuat & minta revisi untuk sisanya saja. Kalau "
        "semua konten sudah cukup berbeda substansinya, kembalikan instruksi_revisi kosong ({}) dan "
        "ada_duplikat_makna: false. Index memakai angka SESUAI '#' di setiap KONTEN di bawah (mulai dari 0).\n\n"
        + daftar_teks
    )
    try:
        teks = panggil_gemini(prompt, validasi=_json_valid)
        data = json.loads(re.sub(r"```json|```", "", teks).strip())
        instruksi = data.get("instruksi_revisi", {})
        if not isinstance(instruksi, dict):
            instruksi = {}
        return {
            "ada_duplikat_makna": bool(data.get("ada_duplikat_makna", False)),
            "instruksi_revisi": instruksi,
        }
    except Exception:
        # Kalau gagal menilai, anggap tidak ada duplikat supaya tidak mengganggu alur generate
        return {"ada_duplikat_makna": False, "instruksi_revisi": {}}

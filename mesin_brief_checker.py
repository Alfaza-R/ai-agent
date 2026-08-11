"""
Brief Checker — agent QC untuk hasil Content Planner.

Memeriksa koherensi/relevansi brief:
- Antar-slide nyambung & satu alur (slide 1 -> 2 -> dst tidak loncat topik).
- Deskripsi Visual (instruksi gambar) sesuai dengan Headline/teks tiap slide.
- Seluruh isi relevan dengan topik.

Kalau tidak konsisten, agent memerintahkan rewrite (maks 2 putaran).
"""
import re
import json

from mesin_agent import client  # reuse client Gemini


def _periksa(brief_html, topik, platform):
    prompt = (
        f"Kamu QC editor untuk brief konten media sosial platform {platform}, topik \"{topik}\".\n\n"
        "Periksa brief HTML di bawah pada 3 aspek:\n"
        "1. KOHERENSI ANTAR-SLIDE: apakah slide mengalir satu alur logis (slide 1 -> 2 -> dst membahas tema yang sama, tidak loncat topik).\n"
        "2. VISUAL vs TEKS: apakah deskripsi 'Visual' (instruksi gambar) tiap slide SESUAI dengan Headline/Isi teks slide itu.\n"
        "3. RELEVANSI TOPIK: apakah seluruh isi relevan dengan topik di atas.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"konsisten\": true/false, \"masalah\": [\"masalah konkret (sebut slide & apa yang salah)\", \"...\"]}\n"
        "Set \"konsisten\": false bila ADA masalah berarti.\n\n"
        "=== BRIEF ===\n" + (brief_html or "")
    )
    try:
        resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        txt = re.sub(r"```json|```", "", resp.text or "").strip()
        data = json.loads(txt)
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
        "PERTAHANKAN format & struktur HTML: <h1> untuk judul narasi, <h2> untuk tiap slide, "
        "<ul><li> untuk poin/Visual, slide terakhir tetap Call To Action. JANGAN ubah/hapus nama brand di judul "
        "(<h1>) maupun field \"Warna Dominan\" kalau sudah ada — pertahankan persis. "
        "Jangan menambah penjelasan/komentar apa pun.\n"
        "Kembalikan HANYA HTML brief yang sudah diperbaiki (tanpa backtick).\n\n"
        "=== BRIEF LAMA ===\n" + (brief_html or "")
    )
    resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
    out = re.sub(r"^```html|^```|```$", "", (resp.text or "").strip(), flags=re.MULTILINE).strip()
    return out or brief_html


def periksa_dan_perbaiki(brief_html, topik, platform, maks=2):
    """Cek koherensi; rewrite kalau perlu (maksimal `maks` putaran)."""
    hasil = brief_html
    for _ in range(maks):
        cek = _periksa(hasil, topik, platform)
        if cek["konsisten"]:
            break
        baru = _rewrite(hasil, topik, platform, cek["masalah"])
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
        resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        txt = re.sub(r"```json|```", "", resp.text or "").strip()
        data = json.loads(txt)
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

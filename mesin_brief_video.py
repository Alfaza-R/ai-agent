"""
Brief Video Short (Reels / TikTok / YouTube Shorts, 9:16, 30-60 detik).

Alur per permintaan:
1. Agent Research (dipakai ulang dari Content Planner) — riset produk dari link referensi.
2. Agent Sutradara — tulis brief per scene: timecode, visual, sumber bahan, teks di layar,
   voice over (kalau dipakai), gerakan/transisi, SFX. Audio (voice over atau cukup musik)
   dipilih AI per konten, dengan alasan.
3. Pengecekan DETERMINISTIK di kode (bukan cuma berharap prompt dipatuhi): total durasi,
   hook <= 3 detik, scene berurutan tanpa celah/tumpang tindih, durasi tiap scene wajar,
   naskah VO tidak kepanjangan untuk durasinya, teks di layar cukup pendek untuk dibaca,
   nomor gambar produk yang dirujuk memang ada. Kalau ada masalah -> rewrite (maks 3 putaran).
4. QC AI (sekali): hook, alur, kecocokan visual-teks, fakta tidak dikarang.

Bagian yang isinya pasti (daftar link gambar produk & checklist export) disusun di kode,
bukan ditulis AI, supaya link tidak salah ketik dan standar export selalu sama.
"""
import html
import json
import re

from mesin_agent import (
    BRAND_INFO,
    SUDUT_KONTEN,
    _agent_research,
    _resolve_sudut_pilihan,
    baca_link,
    panggil_gemini,
)

DURASI_MIN, DURASI_MAKS = 30, 60
HOOK_MAKS = 3              # detik — penonton memutuskan scroll/tidak di 3 detik pertama
SCENE_MIN, SCENE_MAKS = 1, 10
KATA_VO_PER_DETIK = 2.5    # kecepatan bicara wajar bahasa Indonesia
MAKS_KATA_TEKS_LAYAR = 12  # lebih dari ini tidak sempat terbaca di layar HP
MAKS_JUMLAH = 3

AUDIO_VO = "Voice over + teks di layar"
AUDIO_MUSIK = "Teks di layar + musik"

# Jenis hook dibagikan oleh KODE, beda untuk tiap video dalam 1 permintaan. Tes menunjukkan
# instruksi "buat hook berbeda" + cek kemiripan kata tidak cukup: AI terus menulis parafrase
# pertanyaan masalah yang sama ("Data hujan tidak akurat?" / "Data hujan sering meleset?").
JENIS_HOOK = {
    "Pertanyaan":        "pertanyaan yang langsung menyentil masalah penonton",
    "Fakta mengejutkan": "fakta mengejutkan yang BENAR-BENAR ada di hasil riset (bukan pertanyaan). Kalau riset "
                         "tidak memuat angka, pakai fakta tanpa angka — DILARANG mengarang statistik",
    "Visual kejutan":    "visual/demo langsung yang bikin penasaran, teks singkat, tanpa kalimat tanya",
    "Cerita POV":        "potongan situasi nyata sudut pandang orang pertama (mis. 'POV: ...')",
    "Before-after":      "perbandingan sebelum vs sesudah, atau penawaran langsung",
    "Mitos dibantah":    "salah kaprah yang umum dipercaya lalu langsung dibantah",
}
_HOOK_PER_SUDUT = {
    "Edukasi":            ["Fakta mengejutkan", "Pertanyaan", "Mitos dibantah"],
    "Product Knowledge":  ["Visual kejutan", "Fakta mengejutkan"],
    "Storytelling":       ["Cerita POV", "Pertanyaan"],
    "Promosi":            ["Before-after", "Visual kejutan"],
    "Testimoni":          ["Cerita POV", "Fakta mengejutkan"],
    "Behind The Scenes":  ["Visual kejutan", "Cerita POV"],
    "Mitos vs Fakta":     ["Mitos dibantah", "Pertanyaan"],
    "Inspirasi":          ["Cerita POV", "Fakta mengejutkan"],
}


def _pilih_jenis_hook(sudut, sudah_dipakai):
    """Jenis hook paling cocok untuk sudut ini yang belum dipakai video lain."""
    kunci = next((k for k in _HOOK_PER_SUDUT if (sudut or "").startswith(k)), None)
    urutan = _HOOK_PER_SUDUT.get(kunci, []) + list(JENIS_HOOK)
    return next((j for j in urutan if j not in sudah_dipakai), urutan[0])

_KOSONG = {"", "-", "—", "tanpa teks", "(tanpa teks)", "tidak ada", "(tidak ada)"}


# ─── Parsing brief (deterministik) ─────────────────────────────────────────

def _teks_polos(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _jumlah_kata(s):
    return len(re.findall(r"\w+", s or ""))


def _detik(mm, ss):
    return int(mm) * 60 + int(ss)


def _tc(detik):
    return f"{detik // 60:02d}:{detik % 60:02d}"


_POLA_WAKTU = re.compile(r"(\d{1,2}):(\d{2})\s*[–—-]\s*(\d{1,2}):(\d{2})")
_POLA_FIELD = re.compile(
    r"<li\b[^>]*>\s*<strong>\s*([^<]+?)\s*:?\s*</strong>\s*:?\s*(.*?)</li>",
    re.IGNORECASE | re.DOTALL,
)


def _pecah_scene(brief_html):
    """Return list scene: {judul, mulai, selesai, field: {label_lower: teks}}.
    Scene = heading <h2> yang memuat kata 'Scene'."""
    potongan = re.split(r"(<h2\b[^>]*>.*?</h2>)", brief_html or "", flags=re.IGNORECASE | re.DOTALL)
    hasil = []
    for i in range(1, len(potongan), 2):
        judul = _teks_polos(potongan[i])
        if "scene" not in judul.lower():
            continue
        isi = potongan[i + 1] if i + 1 < len(potongan) else ""
        m = _POLA_WAKTU.search(judul)
        field = {}
        for label, nilai in _POLA_FIELD.findall(isi):
            field[label.strip().lower()] = _teks_polos(nilai)
        hasil.append({
            "judul": judul,
            "mulai": _detik(m.group(1), m.group(2)) if m else None,
            "selesai": _detik(m.group(3), m.group(4)) if m else None,
            "field": field,
        })
    return hasil


def _ambil_field(field, *kunci):
    """Cari field berdasarkan awalan label (AI kadang menulis 'Visual utama', 'Voice over (VO)')."""
    for label, nilai in field.items():
        if any(label.startswith(k) for k in kunci):
            return nilai
    return None


def _mode_audio(brief_html):
    """Baca pilihan audio dari bagian Ringkasan. Return AUDIO_VO / AUDIO_MUSIK / None."""
    m = re.search(r"<strong>\s*Audio\s*:?\s*</strong>\s*:?\s*(.*?)</li>", brief_html or "", re.I | re.S)
    if not m:
        return None
    teks = _teks_polos(m.group(1)).lower()
    if "voice over" in teks or "voiceover" in teks:
        return AUDIO_VO
    if "musik" in teks:
        return AUDIO_MUSIK
    return None


def _cek_brief(brief_html, durasi_target, jumlah_gambar):
    """Cek semua aturan yang bisa dihitung. Return daftar masalah (kosong = aman)."""
    masalah = []
    scene = _pecah_scene(brief_html)

    if not scene:
        return ["Tidak ada scene. Tiap scene WAJIB berupa <h2>Scene N — Nama (MM:SS–MM:SS)</h2>."]

    tanpa_waktu = [s["judul"] for s in scene if s["mulai"] is None]
    if tanpa_waktu:
        masalah.append(
            "Heading scene berikut tidak punya timecode format (MM:SS–MM:SS): " + "; ".join(tanpa_waktu)
        )
        return masalah  # hitungan durasi tidak bisa dilanjutkan tanpa timecode

    # Urutan waktu: mulai 00:00, nyambung tanpa celah/tumpang tindih
    if scene[0]["mulai"] != 0:
        masalah.append(f"Scene 1 harus mulai di 00:00 (sekarang {_tc(scene[0]['mulai'])}).")
    for sebelum, s in zip(scene, scene[1:]):
        if s["mulai"] != sebelum["selesai"]:
            masalah.append(
                f"Timecode tidak nyambung: \"{sebelum['judul']}\" selesai {_tc(sebelum['selesai'])} "
                f"tapi \"{s['judul']}\" mulai {_tc(s['mulai'])}. Scene harus berurutan tanpa celah/tumpang tindih."
            )

    # Durasi tiap scene
    for s in scene:
        d = s["selesai"] - s["mulai"]
        if d < SCENE_MIN or d > SCENE_MAKS:
            masalah.append(
                f"\"{s['judul']}\" berdurasi {d} detik — tiap scene harus {SCENE_MIN}-{SCENE_MAKS} detik "
                "(pecah scene yang terlalu panjang)."
            )

    # Hook
    if scene[0]["selesai"] - scene[0]["mulai"] > HOOK_MAKS:
        masalah.append(f"Scene 1 (hook) maksimal {HOOK_MAKS} detik, supaya penonton tidak langsung scroll.")

    # Total durasi
    total = scene[-1]["selesai"]
    if durasi_target:
        if abs(total - durasi_target) > 2:
            masalah.append(f"Total durasi {total} detik, harus {durasi_target} detik (toleransi ±2 detik).")
    elif not (DURASI_MIN <= total <= DURASI_MAKS):
        masalah.append(f"Total durasi {total} detik, harus {DURASI_MIN}-{DURASI_MAKS} detik.")

    min_scene = max(4, total // 10)
    if len(scene) < min_scene:
        masalah.append(f"Cuma {len(scene)} scene untuk video {total} detik — minimal {min_scene} scene supaya tidak monoton.")

    # CTA di scene terakhir
    if "cta" not in scene[-1]["judul"].lower():
        masalah.append("Scene terakhir wajib scene CTA (tulis 'CTA' di heading-nya).")

    # Field wajib per scene
    mode = _mode_audio(brief_html)
    if mode is None:
        masalah.append(
            f"Di Ringkasan, tulis <li><strong>Audio:</strong> {AUDIO_VO} ATAU {AUDIO_MUSIK} — alasan singkat</li>."
        )

    kata_vo_total = 0
    vo_kosong = 0
    for idx, s in enumerate(scene):
        f = s["field"]
        d = s["selesai"] - s["mulai"]
        for label, kunci in (("Visual", ("visual",)), ("Sumber", ("sumber",)),
                             ("Gerakan & transisi", ("gerakan", "transisi"))):
            if not (_ambil_field(f, *kunci) or "").strip():
                masalah.append(f"\"{s['judul']}\": belum ada field \"{label}\".")

        teks_layar = _ambil_field(f, "teks di layar", "teks layar", "teks")
        if teks_layar is None:
            masalah.append(f"\"{s['judul']}\": belum ada field \"Teks di layar\".")
        else:
            wajib_teks = idx == 0 or idx == len(scene) - 1
            if wajib_teks and teks_layar.strip().lower() in _KOSONG:
                masalah.append(f"\"{s['judul']}\": hook & CTA wajib punya teks di layar.")
            n = _jumlah_kata(teks_layar)
            if n > MAKS_KATA_TEKS_LAYAR:
                masalah.append(
                    f"\"{s['judul']}\": teks di layar {n} kata, maksimal {MAKS_KATA_TEKS_LAYAR} kata "
                    "(tidak sempat terbaca). Pindahkan penjelasan panjang ke voice over atau caption."
                )

        sumber = _ambil_field(f, "sumber") or ""
        for nomor in re.findall(r"gambar produk\s*#\s*(\d+)", sumber, re.IGNORECASE):
            if int(nomor) > jumlah_gambar:
                masalah.append(
                    f"\"{s['judul']}\": merujuk Gambar produk #{nomor}, padahal cuma ada {jumlah_gambar} gambar produk."
                )

        if mode == AUDIO_VO:
            vo = _ambil_field(f, "voice over", "vo")
            if vo is None or vo.strip().lower() in _KOSONG:
                vo_kosong += 1
            else:
                n = _jumlah_kata(vo)
                kata_vo_total += n
                batas = int(d * KATA_VO_PER_DETIK) + 2
                if n > batas:
                    masalah.append(
                        f"\"{s['judul']}\": voice over {n} kata untuk {d} detik — maksimal sekitar {batas} kata "
                        "(kecepatan bicara wajar ±2,5 kata/detik). Persingkat atau panjangkan scene-nya."
                    )

    if mode == AUDIO_VO and vo_kosong > 1:
        masalah.append(
            f"Audio dipilih voice over, tapi {vo_kosong} scene belum punya naskah VO. Isi \"Voice over\" "
            "di setiap scene (boleh kosong di maksimal 1 scene)."
        )

    if jumlah_gambar and not re.search(r"gambar produk\s*#\s*\d", brief_html or "", re.IGNORECASE):
        masalah.append(
            f"Ada {jumlah_gambar} gambar produk dari mentor tapi belum dipakai. Rujuk di field Sumber sebagai "
            "\"Gambar produk #1\", \"Gambar produk #2\", dst."
        )

    return masalah


# ─── Agent ─────────────────────────────────────────────────────────────────

def _aturan_format(durasi_target, jumlah_gambar, jenis_hook):
    durasi_txt = (
        f"TEPAT {durasi_target} detik" if durasi_target
        else f"{DURASI_MIN}-{DURASI_MAKS} detik — pilih sendiri yang paling pas untuk isi kontennya"
    )
    gambar_txt = (
        f"Mentor memberi {jumlah_gambar} gambar produk. Rujuk sebagai \"Gambar produk #1\" sampai "
        f"\"Gambar produk #{jumlah_gambar}\" (JANGAN tulis link-nya, link ditempel otomatis)."
        if jumlah_gambar else
        "Mentor belum memberi gambar produk — pakai stock footage, motion graphic, atau rekam sendiri."
    )
    return (
        "FORMAT WAJIB (HTML, tanpa backtick, tanpa penjelasan di luar brief):\n"
        "<h1>Judul konten</h1>\n"
        "<h2>Ringkasan</h2><ul>\n"
        "  <li><strong>Durasi:</strong> NN detik</li>\n"
        "  <li><strong>Format:</strong> Video vertikal 9:16 (1080×1920) — Reels / TikTok / YouTube Shorts</li>\n"
        "  <li><strong>Sudut konten:</strong> ...</li>\n"
        f"  <li><strong>Audio:</strong> {AUDIO_VO} ATAU {AUDIO_MUSIK} — alasan singkat kenapa dipilih</li>\n"
        f"  <li><strong>Jenis hook:</strong> {jenis_hook}</li>\n"
        "  <li><strong>Tujuan:</strong> ...</li>\n"
        "  <li><strong>Target penonton:</strong> ...</li>\n"
        "  <li><strong>Warna brand:</strong> ... (dipakai untuk teks, motion graphic, aksen)</li>\n"
        "</ul>\n"
        "Lalu tiap scene:\n"
        "<h2>Scene N — Nama scene (MM:SS–MM:SS)</h2><ul>\n"
        "  <li><strong>Visual:</strong> apa yang terlihat secara KONKRET — objek/produk, orang & aksinya, lokasi, "
        "jenis shot (close-up/medium/wide), sudut kamera</li>\n"
        "  <li><strong>Sumber:</strong> Gambar produk #N / Stock footage — kata kunci: \"...\" (bahasa Inggris, "
        "siap dicari di Pexels/Pixabay) / Motion graphic — isi animasinya / Rekam sendiri — cara ambil gambarnya</li>\n"
        "  <li><strong>Teks di layar:</strong> \"...\" (maks 12 kata, tulis \"-\" kalau tidak ada)</li>\n"
        f"  <li><strong>Voice over:</strong> \"...\" (HANYA kalau Audio = {AUDIO_VO})</li>\n"
        "  <li><strong>Gerakan & transisi:</strong> gerakan kamera/zoom/pan, animasi teks, transisi ke scene berikutnya</li>\n"
        "  <li><strong>SFX:</strong> efek suara (whoosh, click, dll) — tulis \"-\" kalau tidak ada</li>\n"
        "</ul>\n"
        "<h2>Musik & audio</h2><ul> mood, tempo (BPM), 2-3 kata kunci pencarian musik di CapCut / YouTube Audio "
        "Library, dan kalau pakai VO: gaya suara (nada, kecepatan, boleh pakai AI voice CapCut)</ul>\n"
        "<h2>Caption & hashtag</h2><ul> caption posting (maks 3 kalimat + ajakan) dan 5-8 hashtag relevan</ul>\n\n"
        "ATURAN:\n"
        f"- Total durasi {durasi_txt}. Scene 1 = HOOK, maksimal {HOOK_MAKS} detik, harus bikin penonton berhenti "
        f"scroll. JENIS HOOK WAJIB: {jenis_hook} — {JENIS_HOOK[jenis_hook]}.\n"
        f"- Tiap scene {SCENE_MIN}-{SCENE_MAKS} detik, timecode nyambung tanpa celah (scene 2 mulai tepat saat "
        "scene 1 selesai). Scene terakhir = CTA (tulis 'CTA' di heading-nya).\n"
        f"- AUDIO: pilih {AUDIO_VO} untuk konten yang perlu penjelasan (edukasi, product knowledge, mitos vs "
        f"fakta, storytelling); pilih {AUDIO_MUSIK} untuk konten yang kuat secara visual (promosi, behind the "
        "scenes, inspirasi). Tulis alasannya.\n"
        f"- Voice over maksimal {KATA_VO_PER_DETIK} kata per detik durasi scene. Teks di layar maksimal "
        f"{MAKS_KATA_TEKS_LAYAR} kata — penjelasan panjang taruh di VO atau caption.\n"
        f"- {gambar_txt}\n"
        "- Variasikan sumber visual (gambar produk, stock footage, motion graphic, rekam sendiri) sesuai "
        "kebutuhan tiap scene, supaya video tidak monoton.\n"
        "- Pakai fakta dari HASIL RISET. JANGAN mengarang angka/spesifikasi/klaim. Hindari hal di bagian "
        "JANGAN DIKLAIM.\n"
    )


def _tulis_brief(topik, link, riset, sudut, brand, durasi_target, jumlah_gambar, catatan, hindari, jenis_hook):
    b = BRAND_INFO.get((brand or "").strip().lower())
    brand_txt = (
        f"Akun/brand: {b['label']}. Warna brand: {', '.join(b['warna'])} — pakai sebagai warna teks, motion "
        f"graphic, dan aksen. Tulis nama brand di judul (<h1>).\n" if b else ""
    )
    catatan_txt = f"CATATAN MENTOR (wajib dituruti): {catatan.strip()}\n" if (catatan or "").strip() else ""
    hindari_txt = (
        "Video lain dari permintaan yang sama SUDAH memakai hook & ide berikut — buat yang BERBEDA:\n"
        + "\n".join("- " + h for h in hindari) + "\n" if hindari else ""
    )
    prompt = (
        "Kamu Agent Sutradara: penulis brief video short untuk editor video (anak magang) di tim konten brand "
        "alat industri/laboratorium. Brief harus cukup detail sehingga editor bisa langsung mengerjakan tanpa "
        "bertanya lagi.\n\n"
        f"TOPIK: {topik}\nLINK REFERENSI: {link or '(tidak ada)'}\nSUDUT KONTEN: {sudut}\n"
        + brand_txt + catatan_txt + hindari_txt + "\n"
        + _aturan_format(durasi_target, jumlah_gambar, jenis_hook)
        + "\n=== HASIL RISET PRODUK (bahan utama) ===\n" + (riset or "(tidak ada)")
    )
    try:
        teks = panggil_gemini(prompt, validasi=lambda t: len(t) >= 400 and "<h2" in t.lower())
    except Exception:
        return None
    return _bersihkan(teks)


def _bersihkan(teks):
    return re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", (teks or "").strip()).strip()


def _rewrite(brief_html, masalah, riset, durasi_target, jumlah_gambar, jenis_hook):
    prompt = (
        "Kamu editor brief video short. Perbaiki brief HTML di bawah. MASALAH yang HARUS diperbaiki:\n"
        + "\n".join("- " + str(m) for m in masalah) + "\n\n"
        + _aturan_format(durasi_target, jumlah_gambar, jenis_hook)
        + "\nPertahankan judul, sudut, dan ide kontennya — hanya perbaiki masalah di atas. Kalau menggeser "
        "timecode, sesuaikan SEMUA scene setelahnya supaya tetap nyambung. Kembalikan HANYA HTML brief lengkap.\n\n"
        "=== HASIL RISET (untuk cek fakta) ===\n" + (riset or "(tidak ada)")[:4000]
        + "\n\n=== BRIEF LAMA ===\n" + brief_html
    )
    try:
        return _bersihkan(panggil_gemini(prompt, validasi=lambda t: "<h2" in t.lower()))
    except Exception:
        return brief_html


def _json_valid(teks):
    try:
        json.loads(re.sub(r"```json|```", "", teks).strip())
        return True
    except Exception:
        return False


def _qc(brief_html, topik, riset, jenis_hook):
    """QC AI sekali: hal yang tidak bisa dihitung di kode."""
    prompt = (
        f"Kamu QC brief video short, topik \"{topik}\". Periksa:\n"
        f"1. HOOK: apakah scene 1 benar-benar bikin berhenti scroll, relevan dengan topik, dan BENAR-BENAR "
        f"berjenis \"{jenis_hook}\" ({JENIS_HOOK[jenis_hook]})? Kalau jenisnya lain (mis. diminta fakta tapi "
        "ditulis kalimat tanya), itu masalah.\n"
        "2. ALUR: apakah scene mengalir logis dari hook sampai CTA?\n"
        "3. VISUAL vs TEKS/VO: apakah visual tiap scene cocok dengan teks di layar & voice over-nya?\n"
        "4. FAKTA: adakah angka/spesifikasi/klaim yang TIDAK ada di hasil riset (dikarang)?\n"
        "Kembalikan HANYA JSON: {\"lolos\": true/false, \"masalah\": [\"sebut scene & masalahnya\"]}. "
        "Set lolos=false hanya kalau ada masalah BERARTI.\n\n"
        "=== HASIL RISET ===\n" + (riset or "")[:4000] + "\n\n=== BRIEF ===\n" + brief_html
    )
    try:
        data = json.loads(re.sub(r"```json|```", "", panggil_gemini(prompt, validasi=_json_valid)).strip())
        if data.get("lolos", True):
            return []
        return [str(m) for m in data.get("masalah", []) if str(m).strip()]
    except Exception:
        return []  # QC gagal jangan menggagalkan brief yang sudah lolos cek kode


def _kata_set(s):
    return {w for w in re.findall(r"\w+", (s or "").lower()) if len(w) > 2}


def _mirip(a, b):
    """Kemiripan kata (Jaccard) 0-1 antara dua teks pendek."""
    x, y = _kata_set(a), _kata_set(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def _hook(brief_html):
    """Return (teks di layar hook, teks + VO hook)."""
    scene = _pecah_scene(brief_html)
    if not scene:
        return ("", "")
    f = scene[0]["field"]
    teks = _ambil_field(f, "teks di layar", "teks") or ""
    vo = _ambil_field(f, "voice over", "vo") or ""
    return (teks, f"{teks} {vo}".strip())


def _cek_hook_kembar(brief_html, hook_lain):
    """Prompt 'buat yang berbeda' terbukti tidak cukup (tes: 2 video dengan hook nyaris sama),
    jadi kemiripannya dihitung di kode. Teks di layar dibandingkan tersendiri juga — kalau
    digabung VO, kalimat VO yang panjang mengencerkan skor dan hook kembar lolos."""
    teks, lengkap = _hook(brief_html)
    for teks_lain, lengkap_lain in hook_lain:
        if max(_mirip(teks, teks_lain), _mirip(lengkap, lengkap_lain)) >= 0.4:
            return [
                f"Hook scene 1 terlalu mirip dengan video lain dari permintaan yang sama (\"{teks_lain}\"). "
                "Ganti hook dengan pendekatan BERBEDA — jangan cuma parafrase masalah yang sama. Pilih salah "
                "satu: fakta/angka mengejutkan, visual kejutan tanpa pertanyaan, cerita singkat, atau "
                "penawaran langsung — sesuai sudut konten video ini."
            ]
    return []


_POLA_ANGKA = re.compile(r"\d+(?:[.,]\d+)?")


def _angka(s):
    return {a.replace(",", ".") for a in _POLA_ANGKA.findall(s or "")}


def _cek_angka_dikarang(brief_html, riset):
    """Setiap angka di teks layar & voice over harus ada di hasil riset. Tes menemukan hook
    'Fakta mengejutkan' berisi statistik karangan ('60% data hujan tambang tidak akurat!')
    padahal riset tidak memuat angka itu — dan QC AI tidak menangkapnya.
    Baris riset bertanda '(perlu dicek)' tidak dihitung: Agent Research memakai tanda itu
    untuk klaim yang belum terverifikasi dari sumber."""
    terverifikasi = "\n".join(
        baris for baris in (riset or "").splitlines() if "perlu dicek" not in baris.lower()
    )
    angka_riset = _angka(terverifikasi)
    masalah = []
    for s in _pecah_scene(brief_html):
        f = s["field"]
        teks = " ".join(filter(None, [_ambil_field(f, "teks di layar", "teks"), _ambil_field(f, "voice over", "vo")]))
        asing = sorted(a for a in _angka(teks) if a not in angka_riset)
        if asing:
            masalah.append(
                f"\"{s['judul']}\": angka {', '.join(asing)} tidak ada di hasil riset (kemungkinan dikarang). "
                "Hapus angka itu atau ganti dengan fakta TANPA angka yang memang ada di riset."
            )
    return masalah


def _cek_jenis_hook(brief_html, jenis_hook):
    m = re.search(r"<strong>\s*Jenis hook\s*:?\s*</strong>\s*:?\s*(.*?)</li>", brief_html or "", re.I | re.S)
    if m and jenis_hook.lower() in _teks_polos(m.group(1)).lower():
        return []
    return [
        f"Jenis hook WAJIB \"{jenis_hook}\" ({JENIS_HOOK[jenis_hook]}). Tulis di Ringkasan "
        f"<li><strong>Jenis hook:</strong> {jenis_hook}</li> dan tulis ulang scene 1 sesuai jenis itu."
    ]


def _periksa_dan_perbaiki(brief_html, riset, topik, durasi_target, jumlah_gambar, jenis_hook, hook_lain=(), maks=3):
    """Cek -> rewrite, maksimal `maks` kali rewrite. Hasil rewrite TERAKHIR juga dicek
    (versi lama loop ini tidak, sehingga masalah baru dari rewrite terakhir lolos). Yang
    dikembalikan: versi dengan masalah cek-kode paling sedikit (seri -> versi terbaru)."""
    hasil = brief_html
    terbaik, jumlah_terbaik = brief_html, None
    qc_sudah = False
    for putaran in range(maks + 1):
        masalah = (
            _cek_brief(hasil, durasi_target, jumlah_gambar)
            + _cek_jenis_hook(hasil, jenis_hook)
            + _cek_hook_kembar(hasil, hook_lain)
            + _cek_angka_dikarang(hasil, riset)
        )
        if jumlah_terbaik is None or len(masalah) <= jumlah_terbaik:
            terbaik, jumlah_terbaik = hasil, len(masalah)
        if not masalah:
            if qc_sudah:
                break
            masalah = _qc(hasil, topik, riset, jenis_hook)
            qc_sudah = True
            if not masalah:
                break
        if putaran == maks:
            break
        baru = _rewrite(hasil, masalah, riset, durasi_target, jumlah_gambar, jenis_hook)
        if not baru or baru.strip() == hasil.strip():
            break
        hasil = baru
    return terbaik


# ─── Bagian yang disusun di kode ───────────────────────────────────────────

def _blok_bahan(gambar):
    if not gambar:
        return ""
    e = html.escape
    poin = "".join(
        f'<li><strong>Gambar produk #{i}:</strong> <a href="{e(url)}">{e(url)}</a></li>'
        for i, url in enumerate(gambar, 1)
    )
    return f"<h2>Bahan dari mentor</h2><ul>{poin}</ul>"


_CHECKLIST = (
    "<h2>Checklist sebelum export</h2><ul>"
    "<li>Ukuran 1080×1920 (9:16), 30 fps, export MP4.</li>"
    "<li>Teks & subtitle berada di area aman — jangan terlalu mepet atas/bawah/kanan karena tertutup tombol "
    "dan caption aplikasi.</li>"
    "<li>Kalau pakai voice over, tambahkan subtitle otomatis (CapCut: Teks → Teks otomatis) lalu cek ejaannya.</li>"
    "<li>Durasi akhir sesuai brief (toleransi ±2 detik).</li>"
    "<li>Musik & stock footage bebas hak cipta (library CapCut, YouTube Audio Library, Pexels, Pixabay).</li>"
    "<li>Tonton ulang sampai habis di HP sebelum lapor ke mentor.</li>"
    "</ul>"
)


def _sisipkan_bahan(brief_html, blok):
    """Taruh daftar gambar produk tepat sebelum scene pertama (setelah Ringkasan)."""
    if not blok:
        return brief_html
    m = re.search(r"<h2\b[^>]*>[^<]*scene", brief_html, re.IGNORECASE)
    if not m:
        return blok + brief_html
    return brief_html[:m.start()] + blok + brief_html[m.start():]


def _judul_dan_hook(brief_html):
    h1 = re.search(r"<h1\b[^>]*>(.*?)</h1>", brief_html or "", re.I | re.S)
    return f"{_teks_polos(h1.group(1)) if h1 else '(tanpa judul)'} — hook: {_hook(brief_html)[1]}"


def _pastikan_brand(brief_html, brand):
    """Nama brand wajib ada di judul (<h1>) — kalau AI lupa, ditambahkan di kode."""
    b = BRAND_INFO.get((brand or "").strip().lower())
    if not b:
        return brief_html
    m = re.search(r"(<h1\b[^>]*>)(.*?)(</h1>)", brief_html, re.I | re.S)
    if not m or b["label"].lower() in _teks_polos(m.group(2)).lower():
        return brief_html
    return brief_html[:m.start()] + f"{m.group(1)}{b['label']} — {m.group(2).strip()}{m.group(3)}" + brief_html[m.end():]


# ─── Entry point ───────────────────────────────────────────────────────────

def buat_brief_video(topik, link="", gambar=None, brand="", durasi=0, jumlah=1, sudut=None, catatan=""):
    """
    Return list of {"sudut": str, "durasi": int, "isi": html}. Brief yang gagal total dibuang.
    durasi: 0 = AI pilih 30-60 detik; selain itu dipaksa ke 30/45/60 terdekat.
    """
    gambar = [g.strip() for g in (gambar or []) if str(g).strip()]
    jumlah = max(1, min(int(jumlah or 1), MAKS_JUMLAH))
    durasi = int(durasi or 0)
    if durasi:
        durasi = min((30, 45, 60), key=lambda d: abs(d - durasi))

    daftar_sudut = _resolve_sudut_pilihan(sudut) or SUDUT_KONTEN
    riset = _agent_research(topik, link, baca_link(link), brand)

    hasil, sudah, hook_lain, jenis_dipakai = [], [], [], []
    for i in range(jumlah):
        s = daftar_sudut[i % len(daftar_sudut)]
        jenis_hook = _pilih_jenis_hook(s, jenis_dipakai)
        jenis_dipakai.append(jenis_hook)
        brief = _tulis_brief(topik, link, riset, s, brand, durasi, len(gambar), catatan, sudah, jenis_hook)
        if not brief:
            continue
        brief = _periksa_dan_perbaiki(brief, riset, topik, durasi, len(gambar), jenis_hook, hook_lain)
        brief = _pastikan_brand(brief, brand)
        sudah.append(_judul_dan_hook(brief))
        hook_lain.append(_hook(brief))

        scene = _pecah_scene(brief)
        total = scene[-1]["selesai"] if scene and scene[-1]["selesai"] is not None else durasi
        brief = _sisipkan_bahan(brief, _blok_bahan(gambar)) + _CHECKLIST
        hasil.append({"sudut": s, "durasi": total, "isi": brief})
    return hasil

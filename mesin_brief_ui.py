"""
Brief UI (mockup Figma) — halaman penuh atau section tertentu untuk website perusahaan.

Mentor memberi: website target, halaman/section yang dibuat, tujuan & isinya, link website
referensi, dan/atau screenshot desain lain. Alurnya:

1. Gaya website target dibaca di KODE: warna yang benar-benar paling sering dipakai di CSS
   (warna bawaan Elementor, tombol WhatsApp, & warna bawaan Bootstrap dibuang — tes
   menunjukkan warna "global" Elementor sering masih default yang tidak pernah dipakai) dan
   font dari Google Fonts yang benar-benar dimuat.
2. Struktur website referensi dibaca di kode (judul, menu, heading berurutan, tombol).
3. Agent Analis Referensi (vision) — membaca screenshot + struktur referensi: pola layout,
   gaya visual, apa yang layak diadopsi, apa yang jangan ditiru.
4. Agent UI Writer — brief per section (tujuan, layout desktop & mobile, konten, komponen,
   interaksi) + style guide memakai gaya website TARGET.
5. Cek deterministik: jumlah & kelengkapan section, warna di brief harus satu keluarga
   dengan warna website target (bukan warna brand referensi), font harus font website
   target, nomor referensi/screenshot valid. Kalau ada masalah -> rewrite (maks 3 putaran).
6. QC AI sekali.
"""
import colorsys
import html
import json
import re
import time
from collections import Counter
from urllib.parse import urljoin, urlparse

import requests

from mesin_agent import BRAND_INFO, panggil_gemini

# Domain website perusahaan -> key BRAND_INFO. Domain bukan rahasia (kredensial tetap di WordPress).
SITUS_WEB = {
    "alatuji.co.id": "alatuji",
    "taharica.co.id": "taharica",
    "taharica.com": "taharica",
    "taharicadatamonitoring.com": "taharicadm",
    "automationindo.com": "automationindo",
    "timbanganindonesia.com": "timbangan",
    "rajaloadcell.com": "rajaloadcell",
    "loggerindo.co.id": "loggerindo",
    "loggerindo.com": "loggerindo",
}

MAKS_REFERENSI = 3
MAKS_SCREENSHOT = 5
MIN_SECTION_HALAMAN = 5
TOLERANSI_HUE = 20  # derajat — tint/shade dari warna brand dianggap satu keluarga

_H = {"User-Agent": "Mozilla/5.0"}
# Warna yang BUKAN warna brand walau sering muncul di CSS.
_WARNA_BUKAN_BRAND = {
    "#6ec1e4", "#54595f", "#7a7a7a", "#61ce70",            # kit bawaan Elementor
    "#25d366", "#128c7e", "#075e54",                       # tombol/plugin WhatsApp
    "#d9534f", "#5cb85c", "#f0ad4e", "#5bc0de", "#337ab7",  # kontekstual Bootstrap 3
}
_HUE_NAMA_WARNA = {"merah": 0, "orange": 28, "oranye": 28, "kuning": 50, "cream": 42, "hijau": 130,
                   "cyan": 188, "biru": 215, "ungu": 275, "pink": 330}
_FONT_UMUM = [
    "Poppins", "Jost", "Roboto Slab", "Roboto", "Inter", "Montserrat", "Open Sans", "Lato", "Nunito Sans",
    "Nunito", "Raleway", "Oswald", "Playfair Display", "Merriweather", "Source Sans Pro", "Source Sans 3",
    "Work Sans", "DM Sans", "Manrope", "Plus Jakarta Sans", "Rubik", "Ubuntu", "Noto Sans", "PT Sans", "Mulish",
    "Barlow", "Outfit", "Space Grotesk", "Figtree", "Lexend", "Sora", "Urbanist", "Karla", "Quicksand",
    "Lora", "Heebo", "Archivo", "IBM Plex Sans", "Titillium Web", "Fira Sans", "Exo 2", "Josefin Sans",
]


# ─── Warna ─────────────────────────────────────────────────────────────────

def _hex6(h):
    h = h.lower()
    return "#" + "".join(c * 2 for c in h[1:]) if len(h) == 4 else h[:7]


def _hls(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hue, l, s = colorsys.rgb_to_hls(r, g, b)
    return hue * 360, l, s


def _netral(h):
    _, l, s = _hls(h)
    return s < 0.18 or l > 0.94 or l < 0.08


def _jarak_hue(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


# ─── Baca website ──────────────────────────────────────────────────────────

_cache_gaya = {}


def baca_gaya_web(url):
    """Warna brand yang benar-benar terpakai + font yang benar-benar dimuat. Cache 1 jam."""
    if url in _cache_gaya and time.time() - _cache_gaya[url][0] < 3600:
        return _cache_gaya[url][1]
    hasil = {"warna": [], "font": []}
    try:
        page = requests.get(url, headers=_H, timeout=20).text
        host = urlparse(url).netloc
        links = re.findall(r'<link[^>]+href=["\']([^"\']+\.css[^"\']*)["\']', page)
        css_elementor = [urljoin(url, h) for h in dict.fromkeys(links)
                         if urlparse(urljoin(url, h)).netloc == host and "elementor" in h][:8]
        teks = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", page, re.S))
        teks += "\n" + "\n".join(re.findall(r'style="([^"]*)"', page))
        for c in css_elementor:
            try:
                teks += "\n" + requests.get(c, headers=_H, timeout=15).text
            except Exception:
                pass
        hitung = Counter(_hex6(h) for h in re.findall(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", teks))
        hasil["warna"] = [h for h, _ in hitung.most_common()
                          if h not in _WARNA_BUKAN_BRAND and not _netral(h)][:6]
        hasil["font"] = sorted({f.replace("+", " ").strip() for f in
                                re.findall(r"fonts\.googleapis\.com/css2?\?family=([^&\"':|]+)", page)})
    except Exception:
        pass
    _cache_gaya[url] = (time.time(), hasil)
    return hasil


def baca_struktur_referensi(url, maks=3000):
    """Ringkasan struktur halaman referensi (teks) — pelengkap screenshot."""
    try:
        from bs4 import BeautifulSoup
        page = requests.get(url, headers=_H, timeout=20).text
        sup = BeautifulSoup(page, "html.parser")
        for t in sup(["script", "style", "noscript", "svg"]):
            t.decompose()
        judul = (sup.title.get_text(strip=True) if sup.title else "")[:120]
        nav = sup.find("nav") or sup.find("header")
        menu = [a.get_text(" ", strip=True) for a in (nav.find_all("a") if nav else [])][:15]
        heading = [f"{h.name.upper()}: {h.get_text(' ', strip=True)[:90]}"
                   for h in sup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)][:40]
        tombol = [b.get_text(" ", strip=True)[:40] for b in
                  sup.select("button, a.button, a.btn, .elementor-button, [class*=btn]") if b.get_text(strip=True)][:15]
        teks = (
            f"Judul halaman: {judul}\nMenu: {' | '.join(dict.fromkeys(filter(None, menu)))}\n"
            f"Tombol/CTA: {' | '.join(dict.fromkeys(tombol))}\n"
            f"Jumlah gambar: {len(sup.find_all('img'))}\nUrutan heading:\n" + "\n".join(heading)
        )
        return teks[:maks]
    except Exception as e:
        return f"(gagal dibaca: {e})"


# ─── Parsing & cek deterministik ───────────────────────────────────────────

def _teks_polos(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


_POLA_FIELD = re.compile(r"<li\b[^>]*>\s*<strong>\s*([^<]+?)\s*:?\s*</strong>\s*:?\s*(.*?)</li>", re.I | re.S)


def _pecah_section(brief_html):
    potongan = re.split(r"(<h2\b[^>]*>.*?</h2>)", brief_html or "", flags=re.I | re.S)
    hasil = []
    for i in range(1, len(potongan), 2):
        judul = _teks_polos(potongan[i])
        if not re.match(r"section\b", judul, re.I):
            continue
        isi = potongan[i + 1] if i + 1 < len(potongan) else ""
        field = {k.strip().lower(): _teks_polos(v) for k, v in _POLA_FIELD.findall(isi)}
        hasil.append({"judul": judul, "field": field})
    return hasil


def _ada_field(field, *awalan):
    return any(k.startswith(awalan) and v.strip() for k, v in field.items())


def _kata(s):
    return {w for w in re.findall(r"\w+", (s or "").lower()) if len(w) > 2}


def _mirip(a, b):
    x, y = _kata(a), _kata(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def teks_referensi(struktur, analisis):
    """Teks milik website/screenshot referensi: heading & tombol dari link, plus baris '> ...'
    yang disalin Agent Analis dari screenshot. Dipakai untuk mendeteksi copywriting tersalin."""
    hasil = []
    for _, t in struktur:
        hasil += [m.split(":", 1)[1].strip() for m in re.findall(r"^H[123]:.*$", t, re.M)]
        tombol = re.search(r"^Tombol/CTA:(.*)$", t, re.M)
        if tombol:
            hasil += [x.strip() for x in tombol.group(1).split("|")]
    hasil += [m.strip().strip('"') for m in re.findall(r"^\s*>\s*(.+)$", analisis or "", re.M)]
    return [h for h in dict.fromkeys(hasil) if len(_kata(h)) >= 3]


def _cek_salin_teks(brief_html, teks_ref):
    """Tes: CTA brief 'Siap Tingkatkan Efisiensi Gedung Anda?' ≈ teks screenshot referensi
    'Siap Tingkatkan Efisiensi Pabrik?' — lolos dari prompt & QC AI, jadi dicek di kode."""
    if not teks_ref:
        return []
    masalah = []
    for s in _pecah_section(brief_html):
        konten = next((v for k, v in s["field"].items() if k.startswith("konten")), "")
        for kutipan in re.findall(r"[\"“]([^\"”]{12,})[\"”]", konten):
            if len(_kata(kutipan)) < 3:
                continue
            asal = max(teks_ref, key=lambda r: _mirip(kutipan, r))
            if _mirip(kutipan, asal) >= 0.5:
                masalah.append(
                    f"\"{s['judul']}\": teks \"{kutipan}\" terlalu mirip teks referensi \"{asal}\". "
                    "Tulis copywriting sendiri untuk brand kita — jangan parafrase teks referensi."
                )
    return masalah


def _cek_brief(brief_html, jenis, jumlah_section_diminta, palet, font_web, jumlah_ref, jumlah_ss, teks_ref=()):
    masalah = _cek_salin_teks(brief_html, teks_ref)
    section = _pecah_section(brief_html)

    if not re.search(r"<h2\b[^>]*>\s*style guide", brief_html or "", re.I):
        masalah.append("Belum ada bagian <h2>Style guide</h2> (warna, tipografi, spacing, radius, tombol).")

    minimal = MIN_SECTION_HALAMAN if jenis == "halaman" else max(1, jumlah_section_diminta)
    if len(section) < minimal:
        masalah.append(
            f"Cuma {len(section)} section, minimal {minimal} "
            + ("untuk satu halaman penuh (mis. navbar, hero, isi utama, bukti/keunggulan, CTA, footer)."
               if jenis == "halaman" else "sesuai section yang diminta mentor.")
            + " Tiap section WAJIB <h2>Section N — Nama</h2>."
        )

    for s in section:
        f = s["field"]
        for label, awalan in (("Tujuan", ("tujuan",)), ("Layout desktop", ("layout desktop",)),
                              ("Layout mobile", ("layout mobile",)), ("Konten", ("konten",)),
                              ("Komponen", ("komponen",))):
            if not _ada_field(f, *awalan):
                masalah.append(f"\"{s['judul']}\": belum ada field \"{label}\".")

    # Warna harus satu keluarga dengan warna website target (bukan warna brand referensi).
    if palet:
        hue_palet = [_hls(h)[0] for h in palet]
        asing = []
        for h in dict.fromkeys(_hex6(x) for x in re.findall(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", brief_html or "")):
            if _netral(h) or h in palet:
                continue
            if min(_jarak_hue(_hls(h)[0], p) for p in hue_palet) > TOLERANSI_HUE:
                asing.append(h)
        if asing:
            masalah.append(
                f"Warna {', '.join(asing)} bukan keluarga warna website target ({', '.join(palet)}). "
                "Kemungkinan terbawa dari website referensi — ganti dengan warna brand target atau "
                "tint/shade-nya, atau warna netral (putih/abu/hitam)."
            )

    if font_web:
        disebut = [f for f in _FONT_UMUM if re.search(rf"\b{re.escape(f)}\b", brief_html or "", re.I)]
        # 'Roboto' juga cocok di dalam 'Roboto Slab' — cek pakai nama terpanjang dulu
        asing = [f for f in disebut if f not in font_web
                 and not any(f != g and f in g and g in disebut for g in disebut)]
        if asing:
            masalah.append(
                f"Font {', '.join(asing)} tidak dipakai website target (font website: {', '.join(font_web)}). "
                "Pakai font website target supaya hasil desain bisa langsung diterapkan."
            )

    for nomor in re.findall(r"Referensi\s*#\s*(\d+)", brief_html or "", re.I):
        if int(nomor) > jumlah_ref:
            masalah.append(f"Merujuk Referensi #{nomor}, padahal link referensi cuma {jumlah_ref}.")
            break
    for nomor in re.findall(r"Screenshot\s*#\s*(\d+)", brief_html or "", re.I):
        if int(nomor) > jumlah_ss:
            masalah.append(f"Merujuk Screenshot #{nomor}, padahal screenshot cuma {jumlah_ss}.")
            break
    # Tiap referensi dari mentor wajib dipakai minimal sekali (tes: link Referensi #1 diabaikan,
    # semua section cuma mengacu Screenshot #1).
    dipakai_ref = {int(n) for n in re.findall(r"Referensi\s*#\s*(\d+)", brief_html or "", re.I)}
    dipakai_ss = {int(n) for n in re.findall(r"Screenshot\s*#\s*(\d+)", brief_html or "", re.I)}
    belum = [f"Referensi #{i}" for i in range(1, jumlah_ref + 1) if i not in dipakai_ref]
    belum += [f"Screenshot #{i}" for i in range(1, jumlah_ss + 1) if i not in dipakai_ss]
    if belum:
        masalah.append(
            f"{', '.join(belum)} dari mentor belum dipakai. Di field \"Referensi\" section yang cocok, sebut "
            "referensi itu dan bagian mana yang diacu (mis. pola navbar, kartu produk, tabel spesifikasi)."
        )
    return masalah


# ─── Agent ─────────────────────────────────────────────────────────────────

def _analisis_referensi(struktur, gambar, nama, tujuan):
    if not struktur and not gambar:
        return "(mentor tidak memberi referensi)"
    blok_struktur = "\n\n".join(f"=== Referensi #{i} ({u}) ===\n{t}" for i, (u, t) in enumerate(struktur, 1))
    prompt = (
        "Kamu UI/UX designer senior. Analisis referensi desain berikut sebagai bahan brief untuk "
        f"membuat \"{nama}\" (tujuan: {tujuan}).\n"
        f"Ada {len(gambar)} screenshot terlampir — sebut sebagai Screenshot #1, #2, dst sesuai urutan lampiran. "
        f"Ada {len(struktur)} link referensi — sebut sebagai Referensi #1, #2, dst.\n\n"
        "Untuk TIAP referensi/screenshot tulis ringkas:\n"
        "1. POLA LAYOUT: urutan section & susunan tiap section (kolom, posisi gambar vs teks, grid kartu).\n"
        "2. GAYA VISUAL: hierarki tipografi, spacing/whitespace, radius sudut, bayangan, gaya ikon & foto.\n"
        "3. KOMPONEN MENARIK: navbar, hero, kartu produk, tabel spesifikasi, testimoni, CTA, form, footer.\n"
        "4. LAYAK DIADOPSI: apa yang cocok untuk website alat industri/laboratorium.\n"
        "5. JANGAN DITIRU: logo, nama brand, teks/copywriting, foto milik mereka, dan WARNA BRAND mereka "
        "(warna akan pakai warna website kita sendiri).\n"
        "6. TEKS TERLIHAT: salin PERSIS headline, subjudul, dan teks tombol yang terlihat di tiap screenshot, "
        "satu per baris, tiap baris diawali \"> \".\n\n" + blok_struktur
    )
    try:
        return panggil_gemini(prompt, validasi=lambda t: len(t) >= 200, gambar=gambar)
    except Exception:
        return blok_struktur or "(analisis referensi gagal)"


def _aturan_format(jenis, nama, jumlah_ref, jumlah_ss):
    cakupan = (
        f"SATU HALAMAN PENUH \"{nama}\": minimal {MIN_SECTION_HALAMAN} section berurutan dari atas "
        "(navbar/header sampai footer)."
        if jenis == "halaman" else
        f"SECTION TERTENTU saja: {nama}. Buat HANYA section yang diminta, satu <h2> per section."
    )
    ref = []
    if jumlah_ref:
        ref.append(f"Referensi #1..#{jumlah_ref}")
    if jumlah_ss:
        ref.append(f"Screenshot #1..#{jumlah_ss}")
    ref_txt = " dan ".join(ref) if ref else "(tidak ada referensi — rancang sendiri)"
    return (
        f"CAKUPAN: {cakupan}\n\n"
        "FORMAT WAJIB (HTML, tanpa backtick, tanpa penjelasan di luar brief):\n"
        "<h1>Judul brief</h1>\n"
        "<h2>Ringkasan</h2><ul> <li><strong>Website:</strong> ...</li> <li><strong>Yang dibuat:</strong> ...</li> "
        "<li><strong>Tujuan halaman:</strong> ...</li> <li><strong>Target pengguna:</strong> ...</li> "
        "<li><strong>Frame Figma:</strong> Desktop 1440 px & Mobile 390 px</li> "
        "<li><strong>Grid:</strong> desktop 12 kolom (margin 80, gutter 24); mobile 4 kolom (margin 16, gutter 16)</li></ul>\n"
        "<h2>Style guide</h2><ul> <li><strong>Warna:</strong> primary, secondary, aksen, teks, background — "
        "tulis kode HEX</li> <li><strong>Tipografi:</strong> font + ukuran/tebal H1, H2, H3, body, caption "
        "(desktop & mobile)</li> <li><strong>Spacing:</strong> ...</li> <li><strong>Radius & bayangan:</strong> ...</li> "
        "<li><strong>Tombol:</strong> primary & secondary (warna, radius, padding, state hover)</li> "
        "<li><strong>Ikon & foto:</strong> gaya ikon, gaya foto produk</li></ul>\n"
        "Lalu tiap section:\n"
        "<h2>Section N — Nama section</h2><ul>\n"
        "  <li><strong>Tujuan:</strong> fungsi section ini untuk pengunjung</li>\n"
        "  <li><strong>Layout desktop:</strong> susunan kolom, posisi elemen, lebar/tinggi kira-kira</li>\n"
        "  <li><strong>Layout mobile:</strong> perubahan susunan di 390 px</li>\n"
        "  <li><strong>Konten:</strong> draft headline, subjudul, teks tombol (bahasa Indonesia, siap pakai)</li>\n"
        "  <li><strong>Komponen:</strong> komponen Figma yang dibuat (kartu, tombol, ikon, form, dst)</li>\n"
        "  <li><strong>Gambar/aset:</strong> foto/ilustrasi apa yang dipakai</li>\n"
        f"  <li><strong>Referensi:</strong> {ref_txt} — bagian mana yang diacu & apa yang diadopsi</li>\n"
        "  <li><strong>Interaksi:</strong> hover, animasi masuk, state aktif (tulis \"-\" kalau tidak ada)</li>\n"
        "</ul>\n\n"
        "ATURAN:\n"
        "- Style guide WAJIB memakai warna & font WEBSITE TARGET di bawah, BUKAN warna/font website referensi. "
        "Boleh tint/shade warna brand + warna netral (putih, abu, hitam).\n"
        "- Adopsi POLA layout & gaya referensi, tapi JANGAN menyalin logo, nama brand, teks, atau foto mereka.\n"
        "- Konten ditulis untuk brand kita sendiri, sesuai tujuan halaman.\n"
    )


def _tulis_brief(situs, brand_label, gaya, jenis, nama, tujuan, analisis, jumlah_ref, jumlah_ss, catatan):
    gaya_txt = (
        f"WEBSITE TARGET: {situs} (brand {brand_label or situs})\n"
        f"Warna brand yang dipakai website saat ini (dibaca otomatis): {', '.join(gaya['warna']) or '(tidak terbaca)'}\n"
        f"Font yang dimuat website saat ini: {', '.join(gaya['font']) or '(tidak terbaca)'}\n"
    )
    b = BRAND_INFO.get(SITUS_WEB.get(situs, ""))
    if b:
        gaya_txt += f"Warna brand menurut tim: {', '.join(b['warna'])}\n"
    catatan_txt = f"CATATAN MENTOR (wajib dituruti): {catatan.strip()}\n" if catatan.strip() else ""
    prompt = (
        "Kamu UI Writer: menulis brief mockup Figma untuk desainer magang. Brief harus cukup detail supaya "
        "desainer bisa langsung mengerjakan tanpa bertanya lagi.\n\n"
        f"YANG DIBUAT: {nama}\nTUJUAN & ISI: {tujuan}\n" + gaya_txt + catatan_txt + "\n"
        + _aturan_format(jenis, nama, jumlah_ref, jumlah_ss)
        + "\n=== ANALISIS REFERENSI ===\n" + analisis
    )
    try:
        return _bersihkan(panggil_gemini(prompt, validasi=lambda t: len(t) >= 500 and "<h2" in t.lower()))
    except Exception:
        return None


def _bersihkan(teks):
    return re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", (teks or "").strip()).strip()


def _rewrite(brief_html, masalah, jenis, nama, jumlah_ref, jumlah_ss, gaya):
    prompt = (
        "Kamu editor brief UI. Perbaiki brief HTML di bawah. MASALAH yang HARUS diperbaiki:\n"
        + "\n".join("- " + str(m) for m in masalah) + "\n\n"
        f"Warna website target: {', '.join(gaya['warna']) or '(tidak terbaca)'}. "
        f"Font website target: {', '.join(gaya['font']) or '(tidak terbaca)'}.\n"
        + _aturan_format(jenis, nama, jumlah_ref, jumlah_ss)
        + "\nPertahankan isi yang sudah benar. Kembalikan HANYA HTML brief lengkap.\n\n=== BRIEF LAMA ===\n" + brief_html
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


def _qc(brief_html, nama, tujuan):
    prompt = (
        f"Kamu QC brief UI untuk \"{nama}\" (tujuan: {tujuan}). Periksa:\n"
        "1. Apakah urutan section logis untuk tujuan halaman dan pengunjungnya?\n"
        "2. Apakah layout desktop & mobile tiap section jelas dan bisa dikerjakan di Figma?\n"
        "3. Apakah konten (headline, teks tombol) relevan dan BUKAN salinan teks/nama brand website referensi?\n"
        "Kembalikan HANYA JSON: {\"lolos\": true/false, \"masalah\": [\"sebut section & masalahnya\"]}. "
        "Set lolos=false hanya kalau ada masalah BERARTI.\n\n=== BRIEF ===\n" + brief_html
    )
    try:
        data = json.loads(re.sub(r"```json|```", "", panggil_gemini(prompt, validasi=_json_valid)).strip())
        return [] if data.get("lolos", True) else [str(m) for m in data.get("masalah", []) if str(m).strip()]
    except Exception:
        return []


def _periksa_dan_perbaiki(brief, jenis, nama, tujuan, n_section, gaya, n_ref, n_ss, teks_ref, maks=3):
    """Hasil rewrite terakhir ikut dicek; kembalikan versi dengan masalah cek-kode paling sedikit."""
    hasil, terbaik, jumlah_terbaik, qc_sudah = brief, brief, None, False
    for putaran in range(maks + 1):
        masalah = _cek_brief(hasil, jenis, n_section, gaya["warna"], gaya["font"], n_ref, n_ss, teks_ref)
        if jumlah_terbaik is None or len(masalah) <= jumlah_terbaik:
            terbaik, jumlah_terbaik = hasil, len(masalah)
        if not masalah:
            if qc_sudah:
                break
            masalah = _qc(hasil, nama, tujuan)
            qc_sudah = True
            if not masalah:
                break
        if putaran == maks:
            break
        baru = _rewrite(hasil, masalah, jenis, nama, n_ref, n_ss, gaya)
        if not baru or baru.strip() == hasil.strip():
            break
        hasil = baru
    return terbaik


# ─── Blok yang disusun di kode ─────────────────────────────────────────────

PENANDA_SCREENSHOT = "<p>[[SCREENSHOT]]</p>"  # diganti WordPress dengan screenshot yang sudah diupload

_CHECKLIST = (
    "<h2>Checklist sebelum lapor</h2><ul>"
    "<li>Ada frame Desktop 1440 px dan Mobile 390 px untuk semua section.</li>"
    "<li>Warna & teks didaftarkan sebagai Color Styles dan Text Styles di Figma.</li>"
    "<li>Tombol, kartu, dan elemen berulang dibuat sebagai Component.</li>"
    "<li>Pakai Auto Layout supaya mudah diubah & diterapkan ke Elementor.</li>"
    "<li>Tidak ada logo, teks, atau foto milik website referensi yang ikut terpakai.</li>"
    "<li>Frame diberi nama jelas (mis. \"Desktop — Hero\"), lalu kirim link Figma (akses view) ke mentor.</li>"
    "</ul>"
)


def _blok_referensi(referensi, ada_screenshot, gaya, situs):
    e = html.escape
    poin = "".join(f'<li><strong>Referensi #{i}:</strong> <a href="{e(u)}">{e(u)}</a></li>'
                   for i, u in enumerate(referensi, 1))
    warna = ", ".join(gaya["warna"]) or "(tidak terbaca)"
    font = ", ".join(gaya["font"]) or "(tidak terbaca)"
    return (
        "<h2>Referensi dari mentor</h2>"
        + (f"<ul>{poin}</ul>" if poin else "")
        + (PENANDA_SCREENSHOT if ada_screenshot else "")
        + f"<p><strong>Gaya website {e(situs)} saat ini (dibaca otomatis):</strong> warna {e(warna)} · font {e(font)}</p>"
    )


def _sisipkan_setelah_ringkasan(brief_html, blok):
    """Taruh blok referensi sebelum 'Style guide' (setelah Ringkasan)."""
    m = re.search(r"<h2\b[^>]*>\s*style guide", brief_html, re.I)
    return brief_html[:m.start()] + blok + brief_html[m.start():] if m else blok + brief_html


# ─── Entry point ───────────────────────────────────────────────────────────

def buat_brief_ui(situs, jenis, nama, tujuan, referensi=None, screenshot=None, catatan=""):
    """
    situs: domain di SITUS_WEB. jenis: "halaman" | "section".
    screenshot: list (bytes, mime). Return {"isi", "palet", "font"} atau None kalau gagal total.
    """
    situs = (situs or "").strip().lower()
    jenis = "section" if jenis == "section" else "halaman"
    referensi = [u.strip() for u in (referensi or []) if u and u.strip().startswith("http")][:MAKS_REFERENSI]
    screenshot = list(screenshot or [])[:MAKS_SCREENSHOT]
    n_section = len([s for s in re.split(r",|\+|\bdan\b|\n", nama or "") if s.strip()]) if jenis == "section" else 0

    gaya = baca_gaya_web(f"https://{situs}/") if situs in SITUS_WEB else {"warna": [], "font": []}
    struktur = [(u, baca_struktur_referensi(u)) for u in referensi]
    analisis = _analisis_referensi(struktur, screenshot, nama, tujuan)

    b = BRAND_INFO.get(SITUS_WEB.get(situs, ""))
    brief = _tulis_brief(situs, b["label"] if b else "", gaya, jenis, nama, tujuan, analisis,
                         len(referensi), len(screenshot), catatan or "")
    if not brief:
        return None
    brief = _periksa_dan_perbaiki(brief, jenis, nama, tujuan, n_section, gaya, len(referensi), len(screenshot),
                                  teks_referensi(struktur, analisis))
    brief = _sisipkan_setelah_ringkasan(brief, _blok_referensi(referensi, bool(screenshot), gaya, situs)) + _CHECKLIST
    return {"isi": brief, "palet": gaya["warna"], "font": gaya["font"]}

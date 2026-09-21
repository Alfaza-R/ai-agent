"""
Brief UI (mockup Figma) — halaman penuh atau section tertentu untuk website perusahaan.

Mentor memberi: website target, halaman/section yang dibuat, tujuan & isinya, link website
referensi, dan/atau screenshot desain lain. Alurnya BERURUTAN:

TAHAP 1 — CEK REFERENSI. Semua link & screenshot dianalisis satu per satu (vision + fakta
   CSS dari link: radius, bayangan, ukuran font). Kode memastikan TIDAK ADA referensi yang
   terlewat.
TAHAP 2 — STYLE GABUNGAN. 9 aspek gaya (layout, spacing, radius, bayangan, skala tipografi,
   tombol, kartu, foto & ikon, animasi) diracik dari SEMUA referensi, tiap aspek mencatat
   sumbernya. Kode memastikan setiap referensi menyumbang minimal satu aspek (hasilnya
   campuran, bukan salinan satu referensi). Warna & font TIDAK diambil dari referensi:
   tetap warna & font website target (dibaca di kode dari CSS yang benar-benar dipakai).
   Style guide di brief disusun oleh KODE dari hasil tahap ini.
TAHAP 3 — BRIEF. UI Writer menulis section memakai style gabungan. Cek deterministik:
   jumlah & kelengkapan section, warna satu keluarga dengan warna website target, font
   website target, referensi valid & terpakai, copywriting tidak mirip teks referensi.
   Rewrite maks 3 putaran, lalu QC AI sekali.
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

# Aspek gaya yang digabung dari referensi (warna & font sengaja TIDAK ada di sini).
ASPEK_GAYA = [
    "Layout & grid", "Spacing", "Radius sudut", "Bayangan & kedalaman", "Skala tipografi",
    "Tombol", "Kartu & komponen", "Foto & ikon", "Animasi & interaksi",
]
_FIELD_ANALISIS = ["layout", "spacing", "radius", "bayangan", "tipografi", "tombol", "kartu", "foto_ikon",
                   "animasi", "kesan"]

_H = {"User-Agent": "Mozilla/5.0"}
# Warna yang BUKAN warna brand walau sering muncul di CSS.
_WARNA_BUKAN_BRAND = {
    "#6ec1e4", "#54595f", "#7a7a7a", "#61ce70",            # kit bawaan Elementor
    "#25d366", "#128c7e", "#075e54",                       # tombol/plugin WhatsApp
    "#d9534f", "#5cb85c", "#f0ad4e", "#5bc0de", "#337ab7",  # kontekstual Bootstrap 3
}
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


def _ambil_css(url, page, filter_href=None, maks_file=8):
    """Teks CSS: <style> inline + atribut style="" + file CSS milik domain yang sama."""
    host = urlparse(url).netloc
    links = re.findall(r'<link[^>]+href=["\']([^"\']+\.css[^"\']*)["\']', page)
    files = [urljoin(url, h) for h in dict.fromkeys(links)
             if urlparse(urljoin(url, h)).netloc == host and (filter_href is None or filter_href in h)][:maks_file]
    teks = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", page, re.S))
    teks += "\n" + "\n".join(re.findall(r'style="([^"]*)"', page))
    for c in files:
        try:
            teks += "\n" + requests.get(c, headers=_H, timeout=15).text
        except Exception:
            pass
    return teks


def _google_fonts(page):
    return sorted({f.replace("+", " ").strip() for f in
                   re.findall(r"fonts\.googleapis\.com/css2?\?family=([^&\"':|]+)", page)})


def baca_gaya_web(url):
    """Warna brand yang benar-benar terpakai + font yang benar-benar dimuat. Cache 1 jam.
    (Warna 'global' Elementor sering masih bawaan yang tidak pernah dipakai, jadi yang
    dihitung adalah frekuensi warna di CSS.)"""
    if url in _cache_gaya and time.time() - _cache_gaya[url][0] < 3600:
        return _cache_gaya[url][1]
    hasil = {"warna": [], "font": []}
    try:
        page = requests.get(url, headers=_H, timeout=20).text
        teks = _ambil_css(url, page, filter_href="elementor")
        hitung = Counter(_hex6(h) for h in re.findall(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", teks))
        hasil["warna"] = [h for h, _ in hitung.most_common()
                          if h not in _WARNA_BUKAN_BRAND and not _netral(h)][:6]
        hasil["font"] = _google_fonts(page)
    except Exception:
        pass
    _cache_gaya[url] = (time.time(), hasil)
    return hasil


def _fakta_css(teks_css):
    """Fakta gaya yang bisa dihitung dari CSS referensi (bukan tebakan AI)."""
    radius = Counter(v.strip() for v in re.findall(r"border-radius\s*:\s*([^;}{!]+)", teks_css)
                     if v.strip() not in ("0", "0px", "inherit", "initial"))
    bayangan = [v.strip() for v in re.findall(r"box-shadow\s*:\s*([^;}{!]+)", teks_css) if "none" not in v]
    ukuran = Counter(re.findall(r"font-size\s*:\s*(\d+(?:\.\d+)?px)", teks_css))
    return (
        f"Radius paling sering: {', '.join(v for v, _ in radius.most_common(4)) or '-'}\n"
        f"Bayangan: {len(bayangan)} deklarasi" + (f", contoh: {bayangan[0][:60]}" if bayangan else "") + "\n"
        f"Ukuran font paling sering: {', '.join(v for v, _ in ukuran.most_common(6)) or '-'}"
    )


def baca_struktur_referensi(url, maks=3500):
    """Ringkasan halaman referensi: struktur (heading, menu, tombol) + fakta CSS."""
    try:
        from bs4 import BeautifulSoup
        page = requests.get(url, headers=_H, timeout=20).text
        fakta = _fakta_css(_ambil_css(url, page, maks_file=4))
        fonts = _google_fonts(page)
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
            f"Jumlah gambar: {len(sup.find_all('img'))}\nFont dimuat: {', '.join(fonts) or '-'}\n"
            f"FAKTA CSS:\n{fakta}\nUrutan heading:\n" + "\n".join(heading)
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


def _cek_warna(teks, palet):
    """Warna harus satu keluarga (hue) dengan warna website target, atau netral."""
    if not palet:
        return []
    hue_palet = [_hls(h)[0] for h in palet]
    asing = []
    for h in dict.fromkeys(_hex6(x) for x in re.findall(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", teks or "")):
        if _netral(h) or h in palet:
            continue
        if min(_jarak_hue(_hls(h)[0], p) for p in hue_palet) > TOLERANSI_HUE:
            asing.append(h)
    if not asing:
        return []
    return [
        f"Warna {', '.join(asing)} bukan keluarga warna website target ({', '.join(palet)}). "
        "Kemungkinan terbawa dari website referensi — ganti dengan warna brand target atau "
        "tint/shade-nya, atau warna netral (putih/abu/hitam)."
    ]


def _cek_font(teks, font_web):
    if not font_web:
        return []
    disebut = [f for f in _FONT_UMUM if re.search(rf"\b{re.escape(f)}\b", teks or "", re.I)]
    # 'Roboto' juga cocok di dalam 'Roboto Slab' — yang dihitung nama terpanjangnya.
    asing = [f for f in disebut if f not in font_web
             and not any(f != g and f in g and g in disebut for g in disebut)]
    if not asing:
        return []
    return [
        f"Font {', '.join(asing)} tidak dipakai website target (font website: {', '.join(font_web)}). "
        "Pakai font website target supaya hasil desain bisa langsung diterapkan."
    ]


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


def _cek_brief(brief_html, jenis, jumlah_section_diminta, palet, font_web, id_ref, teks_ref=()):
    masalah = _cek_salin_teks(brief_html, teks_ref)
    section = _pecah_section(brief_html)

    if re.search(r"<h[1-3]\b[^>]*>\s*style guide", brief_html or "", re.I):
        masalah.append("Hapus bagian Style guide dari brief — style guide sudah disusun dari style gabungan.")

    minimal =MIN_SECTION_HALAMAN if jenis == "halaman" else max(1, jumlah_section_diminta)
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

    masalah += _cek_warna(brief_html, palet) + _cek_font(brief_html, font_web)

    disebut = set(_id_disebut(brief_html))
    tidak_ada = sorted(disebut - set(id_ref))
    if tidak_ada:
        masalah.append(f"Merujuk {', '.join(tidak_ada)}, padahal referensi yang ada: {', '.join(id_ref) or '(tidak ada)'}.")
    belum = [i for i in id_ref if i not in disebut]
    if belum:
        masalah.append(
            f"{', '.join(belum)} belum dipakai di section mana pun. Di field \"Referensi\" section yang cocok, "
            "sebut referensi itu dan bagian mana yang diacu."
        )
    return masalah


def _id_disebut(teks):
    return [f"{jenis.capitalize()} #{n}" for jenis, n in
            re.findall(r"\b(Referensi|Screenshot)\s*#\s*(\d+)", teks or "", re.I)]


# ─── Tahap 1: cek referensi ────────────────────────────────────────────────

def _json_dari(teks):
    return json.loads(re.sub(r"```json|```", "", teks or "").strip())


def _analisis_referensi(struktur, gambar, nama, tujuan):
    """Return list analisis per referensi (dict dengan 'id' + _FIELD_ANALISIS + 'teks_terlihat').
    Kode memastikan SEMUA referensi (Screenshot #1..n, Referensi #1..n) ada di hasil."""
    id_ref = [f"Screenshot #{i}" for i in range(1, len(gambar) + 1)] + \
             [f"Referensi #{i}" for i in range(1, len(struktur) + 1)]
    if not id_ref:
        return []

    blok_struktur = "\n\n".join(f"=== Referensi #{i} ({u}) ===\n{t}" for i, (u, t) in enumerate(struktur, 1))
    contoh = {"id": "Screenshot #1", **{f: "..." for f in _FIELD_ANALISIS}, "teks_terlihat": ["..."]}
    prompt = (
        "Kamu UI/UX designer senior. TAHAP 1: CEK SEMUA REFERENSI satu per satu sebelum mendesain "
        f"\"{nama}\" (tujuan: {tujuan}).\n"
        f"Referensi yang WAJIB dianalisis semua: {', '.join(id_ref)}. Screenshot #1, #2, dst = urutan gambar "
        "terlampir. Referensi #N = link website (struktur & FAKTA CSS-nya di bawah).\n\n"
        "Untuk TIAP referensi isi:\n"
        "- layout: urutan section & susunan (kolom, posisi gambar vs teks, grid kartu)\n"
        "- spacing: rapat/lega, jarak antar section & elemen\n"
        "- radius: bentuk sudut tombol, kartu, gambar (pakai FAKTA CSS kalau ada)\n"
        "- bayangan: pemakaian bayangan/border/kedalaman\n"
        "- tipografi: hierarki & skala ukuran judul vs body, ketebalan (JANGAN sebut nama font)\n"
        "- tombol: bentuk, ukuran, gaya primary/secondary\n"
        "- kartu: gaya kartu & komponen berulang\n"
        "- foto_ikon: gaya foto & ikon\n"
        "- animasi: interaksi/hover/animasi yang terlihat atau lazim untuk gaya itu\n"
        "- kesan: kesan keseluruhan dalam 1 kalimat\n"
        "- teks_terlihat: salin PERSIS headline, subjudul, teks tombol yang terlihat\n"
        "JANGAN menulis kode warna HEX atau nama font — warna & font memakai milik website kita sendiri.\n\n"
        "Kembalikan HANYA JSON: {\"referensi\": [" + json.dumps(contoh, ensure_ascii=False) + ", ...]}\n\n"
        + blok_struktur
    )

    def valid(t):
        try:
            data = _json_dari(t).get("referensi", [])
            ada = {str(r.get("id", "")).strip() for r in data if isinstance(r, dict)}
            return all(i in ada for i in id_ref)
        except Exception:
            return False

    try:
        data = _json_dari(panggil_gemini(prompt, validasi=valid, gambar=gambar))["referensi"]
    except Exception:
        # Gagal total: tetap lanjut dengan struktur link apa adanya supaya brief tidak batal.
        return [{"id": f"Referensi #{i}", "kesan": t[:300], "teks_terlihat": []}
                for i, (_, t) in enumerate(struktur, 1)]
    urut = {r["id"]: r for r in data if isinstance(r, dict) and r.get("id") in id_ref}
    return [urut[i] for i in id_ref if i in urut]


def teks_referensi(struktur, analisis):
    """Teks milik referensi (heading & tombol dari link + teks yang terlihat di screenshot).
    Dipakai untuk mendeteksi copywriting yang tersalin."""
    hasil = []
    for _, t in struktur:
        hasil += [m.split(":", 1)[1].strip() for m in re.findall(r"^H[123]:.*$", t, re.M)]
        tombol = re.search(r"^Tombol/CTA:(.*)$", t, re.M)
        if tombol:
            hasil += [x.strip() for x in tombol.group(1).split("|")]
    for r in analisis:
        hasil += [str(x).strip() for x in (r.get("teks_terlihat") or []) if str(x).strip()]
    return [h for h in dict.fromkeys(hasil) if len(_kata(h)) >= 3]


# ─── Tahap 2: style gabungan ───────────────────────────────────────────────

def _cek_style_gabungan(data, id_ref, palet, font_web):
    masalah = []
    if not isinstance(data, dict):
        return ["Bukan JSON objek."]
    atribut = {str(a.get("aspek", "")).strip(): a for a in data.get("atribut", []) if isinstance(a, dict)}
    for aspek in ASPEK_GAYA:
        a = atribut.get(aspek)
        if not a or len(str(a.get("nilai", "")).split()) < 6:
            masalah.append(f"Aspek \"{aspek}\" belum diisi atau terlalu singkat (minimal satu kalimat spesifik).")
            continue
        sumber = [str(s).strip() for s in (a.get("sumber") or [])]
        salah = [s for s in sumber if s not in id_ref and s != "Rekomendasi"]
        if salah:
            masalah.append(f"Aspek \"{aspek}\": sumber {', '.join(salah)} tidak dikenal. Pakai: {', '.join(id_ref)}.")
    if len(id_ref) >= 2:
        dipakai = {str(s).strip() for a in atribut.values() for s in (a.get("sumber") or [])}
        belum = [i for i in id_ref if i not in dipakai]
        if belum:
            masalah.append(
                f"{', '.join(belum)} belum menyumbang aspek apa pun. Style harus GABUNGAN semua referensi — "
                "ambil minimal satu aspek dari tiap referensi."
            )
    teks = json.dumps(data, ensure_ascii=False)
    return masalah + _cek_warna(teks, palet) + _cek_font(teks, font_web)


def _style_gabungan(analisis, id_ref, gaya, nama, tujuan):
    """Racik 9 aspek gaya dari semua referensi. Return dict {"konsep", "atribut": [...]}."""
    ringkas = json.dumps([{k: v for k, v in r.items() if k != "teks_terlihat"} for r in analisis],
                         ensure_ascii=False)
    aturan_sumber = (
        f"Sumber tiap aspek diisi dengan id referensi ({', '.join(id_ref)}); boleh lebih dari satu kalau "
        "aspeknya perpaduan. WAJIB: setiap referensi menyumbang minimal satu aspek — ini gaya GABUNGAN."
        if id_ref else
        "Tidak ada referensi — isi sumber dengan [\"Rekomendasi\"]."
    )
    contoh = {"konsep": "1-2 kalimat arah gaya gabungan",
              "atribut": [{"aspek": ASPEK_GAYA[0], "nilai": "keputusan spesifik + angka (px) bila relevan",
                           "sumber": ["Screenshot #1"]}]}
    dasar = (
        "TAHAP 2: RACIK STYLE GABUNGAN untuk desain "
        f"\"{nama}\" (tujuan: {tujuan}) dari hasil cek referensi di bawah.\n"
        f"Aspek yang WAJIB diisi semua: {', '.join(ASPEK_GAYA)}.\n"
        "Tiap aspek: keputusan yang SPESIFIK & bisa langsung dipakai di Figma (sertakan angka px untuk radius, "
        "spacing, ukuran teks), bukan sekadar 'modern' atau 'bersih'.\n"
        f"{aturan_sumber}\n"
        "WARNA & FONT BUKAN bagian dari aspek ini — jangan tulis kode HEX atau nama font "
        f"(website target memakai warna {', '.join(gaya['warna']) or '-'} dan font {', '.join(gaya['font']) or '-'}).\n"
        "Kembalikan HANYA JSON seperti: " + json.dumps(contoh, ensure_ascii=False) + "\n\n"
        "=== HASIL CEK REFERENSI ===\n" + ringkas
    )
    prompt, data = dasar, None
    for _ in range(3):
        try:
            data = _json_dari(panggil_gemini(prompt, validasi=lambda t: _json_valid(t)))
        except Exception:
            break
        masalah = _cek_style_gabungan(data, id_ref, gaya["warna"], gaya["font"])
        if not masalah:
            return data
        prompt = dasar + "\n\n=== PERBAIKI MASALAH INI dari jawaban sebelumnya ===\n" + \
            "\n".join("- " + m for m in masalah) + "\n\nJawaban sebelumnya:\n" + json.dumps(data, ensure_ascii=False)
    return data if isinstance(data, dict) else {"konsep": "", "atribut": []}


def _json_valid(teks):
    try:
        _json_dari(teks)
        return True
    except Exception:
        return False


# ─── Tahap 3: brief ────────────────────────────────────────────────────────

def _teks_style(style):
    baris = [f"Arah gaya: {style.get('konsep', '')}"]
    for a in style.get("atribut", []):
        baris.append(f"- {a.get('aspek')}: {a.get('nilai')} (sumber: {', '.join(a.get('sumber') or [])})")
    return "\n".join(baris)


def _aturan_format(jenis, nama, id_ref):
    cakupan = (
        f"SATU HALAMAN PENUH \"{nama}\": minimal {MIN_SECTION_HALAMAN} section berurutan dari atas "
        "(navbar/header sampai footer)."
        if jenis == "halaman" else
        f"SECTION TERTENTU saja: {nama}. Buat HANYA section yang diminta, satu <h2> per section."
    )
    ref_txt = ", ".join(id_ref) if id_ref else "(tidak ada referensi — tulis \"-\")"
    return (
        f"CAKUPAN: {cakupan}\n\n"
        "FORMAT WAJIB (HTML, tanpa backtick, tanpa penjelasan di luar brief). JANGAN tulis bagian style guide — "
        "style guide sudah disusun terpisah dari style gabungan.\n"
        "<h1>Judul brief</h1>\n"
        "<h2>Ringkasan</h2><ul> <li><strong>Website:</strong> ...</li> <li><strong>Yang dibuat:</strong> ...</li> "
        "<li><strong>Tujuan halaman:</strong> ...</li> <li><strong>Target pengguna:</strong> ...</li> "
        "<li><strong>Frame Figma:</strong> Desktop 1440 px & Mobile 390 px</li></ul>\n"
        "Lalu tiap section:\n"
        "<h2>Section N — Nama section</h2><ul>\n"
        "  <li><strong>Tujuan:</strong> fungsi section ini untuk pengunjung</li>\n"
        "  <li><strong>Layout desktop:</strong> susunan kolom, posisi elemen, ukuran kira-kira</li>\n"
        "  <li><strong>Layout mobile:</strong> perubahan susunan di 390 px</li>\n"
        "  <li><strong>Konten:</strong> draft headline, subjudul, teks tombol (bahasa Indonesia, siap pakai)</li>\n"
        "  <li><strong>Komponen:</strong> komponen Figma yang dibuat & gaya dari style gabungan yang dipakai</li>\n"
        "  <li><strong>Gambar/aset:</strong> foto/ilustrasi apa yang dipakai</li>\n"
        f"  <li><strong>Referensi:</strong> {ref_txt} — bagian mana yang diacu</li>\n"
        "  <li><strong>Interaksi:</strong> hover, animasi masuk, state aktif (tulis \"-\" kalau tidak ada)</li>\n"
        "</ul>\n\n"
        "ATURAN:\n"
        "- WAJIB konsisten dengan STYLE GABUNGAN (radius, spacing, bayangan, gaya tombol/kartu, dst).\n"
        "- Warna hanya warna website target (atau tint/shade-nya) + netral. Font hanya font website target.\n"
        "- Adopsi POLA dari referensi, tapi JANGAN menyalin logo, nama brand, teks, atau foto mereka.\n"
    )


def _tulis_brief(situs, brand_label, gaya, jenis, nama, tujuan, style, id_ref, catatan):
    gaya_txt = (
        f"WEBSITE TARGET: {situs} (brand {brand_label or situs})\n"
        f"Warna website target: {', '.join(gaya['warna']) or '(tidak terbaca)'}\n"
        f"Font website target: {', '.join(gaya['font']) or '(tidak terbaca)'}\n"
    )
    catatan_txt = f"CATATAN MENTOR (wajib dituruti): {catatan.strip()}\n" if catatan.strip() else ""
    prompt = (
        "Kamu UI Writer (TAHAP 3): menulis brief mockup Figma untuk desainer magang, memakai STYLE GABUNGAN "
        "hasil tahap sebelumnya. Brief harus cukup detail supaya desainer bisa langsung mengerjakan.\n\n"
        f"YANG DIBUAT: {nama}\nTUJUAN & ISI: {tujuan}\n" + gaya_txt + catatan_txt + "\n"
        + _aturan_format(jenis, nama, id_ref)
        + "\n=== STYLE GABUNGAN ===\n" + _teks_style(style)
    )
    try:
        return _bersihkan(panggil_gemini(prompt, validasi=lambda t: len(t) >= 500 and "<h2" in t.lower()))
    except Exception:
        return None


def _bersihkan(teks):
    return re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", (teks or "").strip()).strip()


def _rewrite(brief_html, masalah, jenis, nama, id_ref, gaya, style):
    prompt = (
        "Kamu editor brief UI. Perbaiki brief HTML di bawah. MASALAH yang HARUS diperbaiki:\n"
        + "\n".join("- " + str(m) for m in masalah) + "\n\n"
        f"Warna website target: {', '.join(gaya['warna']) or '(tidak terbaca)'}. "
        f"Font website target: {', '.join(gaya['font']) or '(tidak terbaca)'}.\n"
        + _aturan_format(jenis, nama, id_ref)
        + "\n=== STYLE GABUNGAN ===\n" + _teks_style(style)
        + "\n\nPertahankan isi yang sudah benar. Kembalikan HANYA HTML brief lengkap.\n\n=== BRIEF LAMA ===\n" + brief_html
    )
    try:
        return _bersihkan(panggil_gemini(prompt, validasi=lambda t: "<h2" in t.lower()))
    except Exception:
        return brief_html


def _qc(brief_html, nama, tujuan, style):
    prompt = (
        f"Kamu QC brief UI untuk \"{nama}\" (tujuan: {tujuan}). Periksa:\n"
        "1. Apakah urutan section logis untuk tujuan halaman dan pengunjungnya?\n"
        "2. Apakah layout desktop & mobile tiap section jelas dan bisa dikerjakan di Figma?\n"
        "3. Apakah section KONSISTEN dengan style gabungan di bawah (radius, spacing, gaya tombol/kartu)?\n"
        "4. Apakah konten (headline, teks tombol) relevan dan BUKAN salinan teks/nama brand referensi?\n"
        "Kembalikan HANYA JSON: {\"lolos\": true/false, \"masalah\": [\"sebut section & masalahnya\"]}. "
        "Set lolos=false hanya kalau ada masalah BERARTI.\n\n=== STYLE GABUNGAN ===\n" + _teks_style(style)
        + "\n\n=== BRIEF ===\n" + brief_html
    )
    try:
        data = _json_dari(panggil_gemini(prompt, validasi=_json_valid))
        return [] if data.get("lolos", True) else [str(m) for m in data.get("masalah", []) if str(m).strip()]
    except Exception:
        return []


def _periksa_dan_perbaiki(brief, jenis, nama, tujuan, n_section, gaya, id_ref, teks_ref, style, maks=3):
    """Hasil rewrite terakhir ikut dicek; kembalikan versi dengan masalah cek-kode paling sedikit."""
    hasil, terbaik, jumlah_terbaik, qc_sudah = brief, brief, None, False
    for putaran in range(maks + 1):
        masalah = _cek_brief(hasil, jenis, n_section, gaya["warna"], gaya["font"], id_ref, teks_ref)
        if jumlah_terbaik is None or len(masalah) <= jumlah_terbaik:
            terbaik, jumlah_terbaik = hasil, len(masalah)
        if not masalah:
            if qc_sudah:
                break
            masalah = _qc(hasil, nama, tujuan, style)
            qc_sudah = True
            if not masalah:
                break
        if putaran == maks:
            break
        baru = _rewrite(hasil, masalah, jenis, nama, id_ref, gaya, style)
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
    "<li>Radius, spacing, bayangan, tombol, dan kartu mengikuti Style guide (gabungan referensi).</li>"
    "<li>Tombol, kartu, dan elemen berulang dibuat sebagai Component; pakai Auto Layout.</li>"
    "<li>Tidak ada logo, teks, atau foto milik website referensi yang ikut terpakai.</li>"
    "<li>Frame diberi nama jelas (mis. \"Desktop — Hero\"), lalu kirim link Figma (akses view) ke mentor.</li>"
    "</ul>"
)


def _blok_referensi(referensi, ada_screenshot, analisis):
    """Daftar referensi + hasil cek tiap referensi (tahap 1)."""
    e = html.escape
    poin = "".join(f'<li><strong>Referensi #{i}:</strong> <a href="{e(u)}">{e(u)}</a></li>'
                   for i, u in enumerate(referensi, 1))
    h = "<h2>Referensi dari mentor</h2>" + (f"<ul>{poin}</ul>" if poin else "") + \
        (PENANDA_SCREENSHOT if ada_screenshot else "")
    if analisis:
        h += "<h2>Hasil cek referensi</h2>"
        for r in analisis:
            gaya = "; ".join(str(r.get(k)) for k in ("radius", "bayangan", "tipografi") if r.get(k))
            h += (f"<h3>{e(str(r.get('id', '')))}</h3><ul>"
                  + (f"<li><strong>Kesan:</strong> {e(str(r['kesan']))}</li>" if r.get("kesan") else "")
                  + (f"<li><strong>Layout:</strong> {e(str(r['layout']))}</li>" if r.get("layout") else "")
                  + (f"<li><strong>Gaya:</strong> {e(gaya)}</li>" if gaya else "")
                  + "</ul>")
    return h


def _blok_style_guide(style, gaya, situs):
    """Style guide disusun KODE dari style gabungan + warna/font website target."""
    e = html.escape
    warna = ", ".join(gaya["warna"]) or "(tidak terbaca — tanyakan mentor)"
    font = ", ".join(gaya["font"]) or "(tidak terbaca — tanyakan mentor)"
    h = "<h2>Style guide (gabungan referensi)</h2>"
    if style.get("konsep"):
        h += f"<p><strong>Arah gaya:</strong> {e(str(style['konsep']))}</p>"
    h += (
        "<ul>"
        f"<li><strong>Warna (website {e(situs)}):</strong> {e(warna)} — plus netral putih, abu muda, "
        "abu gelap/hitam untuk teks. Boleh tint/shade dari warna brand.</li>"
        f"<li><strong>Font (website {e(situs)}):</strong> {e(font)}</li>"
    )
    for a in style.get("atribut", []):
        sumber = ", ".join(str(s) for s in (a.get("sumber") or []))
        h += (f"<li><strong>{e(str(a.get('aspek', '')))}:</strong> {e(str(a.get('nilai', '')))}"
              + (f" <em>(dari {e(sumber)})</em>" if sumber else "") + "</li>")
    return h + "</ul>"


def _sisipkan_setelah_ringkasan(brief_html, blok):
    """Taruh blok referensi & style guide tepat sebelum section pertama."""
    m = re.search(r"<h2\b[^>]*>\s*section\b", brief_html, re.I)
    return brief_html[:m.start()] + blok + brief_html[m.start():] if m else brief_html + blok


# ─── Entry point ───────────────────────────────────────────────────────────

def buat_brief_ui(situs, jenis, nama, tujuan, referensi=None, screenshot=None, catatan=""):
    """
    situs: domain di SITUS_WEB. jenis: "halaman" | "section".
    screenshot: list (bytes, mime). Return {"isi", "palet", "font", "style"} atau None kalau gagal total.
    """
    situs = (situs or "").strip().lower()
    jenis = "section" if jenis == "section" else "halaman"
    referensi = [u.strip() for u in (referensi or []) if u and u.strip().startswith("http")][:MAKS_REFERENSI]
    screenshot = list(screenshot or [])[:MAKS_SCREENSHOT]
    n_section = len([s for s in re.split(r",|\+|\bdan\b|\n", nama or "") if s.strip()]) if jenis == "section" else 0
    id_ref = [f"Screenshot #{i}" for i in range(1, len(screenshot) + 1)] + \
             [f"Referensi #{i}" for i in range(1, len(referensi) + 1)]

    gaya = baca_gaya_web(f"https://{situs}/") if situs in SITUS_WEB else {"warna": [], "font": []}

    # TAHAP 1 — cek semua referensi
    struktur = [(u, baca_struktur_referensi(u)) for u in referensi]
    analisis = _analisis_referensi(struktur, screenshot, nama, tujuan)

    # TAHAP 2 — style gabungan dari semua referensi
    style = _style_gabungan(analisis, id_ref, gaya, nama, tujuan)

    # TAHAP 3 — brief memakai style gabungan
    b = BRAND_INFO.get(SITUS_WEB.get(situs, ""))
    brief = _tulis_brief(situs, b["label"] if b else "", gaya, jenis, nama, tujuan, style, id_ref, catatan or "")
    if not brief:
        return None
    brief = _periksa_dan_perbaiki(brief, jenis, nama, tujuan, n_section, gaya, id_ref,
                                  teks_referensi(struktur, analisis), style)
    blok = _blok_referensi(referensi, bool(screenshot), analisis) + _blok_style_guide(style, gaya, situs)
    brief = _sisipkan_setelah_ringkasan(brief, blok) + _CHECKLIST
    return {"isi": brief, "palet": gaya["warna"], "font": gaya["font"], "style": style}

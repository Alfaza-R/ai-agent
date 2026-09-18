"""
Brief SEO — Input Gambar.

Mentor cuma input: daftar keyword (artikel yang sudah tayang tapi belum ada gambar)
+ website mana. Mesin ini bikin RENCANA GAMBAR per keyword:
featured image + gambar dalam artikel, lengkap dengan ide visual, alt text siap tempel,
usulan nama file, dan sumber gambar.

Bagian brief yang tetap (cara login, cara input gambar, cara isi alt text, template
Canva) TIDAK dibuat di sini — itu disusun di sisi WordPress, supaya kredensial login
tidak pernah lewat/menempel di backend AI yang endpoint-nya publik.
"""
import html
import json
import re

from mesin_agent import panggil_gemini  # pemanggil Gemini dengan retry + model cadangan

MIN_GAMBAR = 3      # 1 featured + minimal 2 gambar dalam artikel
MAKS_GAMBAR = 6
MAKS_ALT = 125      # batas aman alt text (biar tidak dipotong pembaca layar/mesin pencari)
MIN_KATA_IDE = 10   # ide visual harus konkret, bukan "gambar produk"


def _slug(teks, maks=60):
    s = re.sub(r"[^a-z0-9]+", "-", (teks or "").lower()).strip("-")
    return s[:maks].strip("-") or "gambar"


def _kata_inti(keyword):
    """Kata-kata penting dari keyword (buat cek alt text benar-benar menyebut topiknya)."""
    return [k for k in re.split(r"\s+", (keyword or "").lower()) if len(k) > 3]


def _potong_alt(alt):
    alt = re.sub(r"\s+", " ", (alt or "")).strip().strip('"')
    if len(alt) <= MAKS_ALT:
        return alt
    potong = alt[:MAKS_ALT]
    return potong[: potong.rfind(" ")].rstrip(",.;:-") if " " in potong else potong


def _json_rencana_valid(teks):
    """Validator untuk panggil_gemini: JSON benar & isinya memang layak dipakai."""
    try:
        data = json.loads(re.sub(r"```json|```", "", teks).strip())
        gambar = data.get("gambar")
        if not isinstance(gambar, list) or not (MIN_GAMBAR <= len(gambar) <= MAKS_GAMBAR):
            return False
        for g in gambar:
            if not isinstance(g, dict):
                return False
            for kunci in ("posisi", "ide", "alt", "file", "sumber"):
                if not str(g.get(kunci, "")).strip():
                    return False
            if len(str(g["ide"]).split()) < MIN_KATA_IDE:
                return False
        return True
    except Exception:
        return False


def _rapikan(gambar, keyword):
    """Beresin hasil AI di kode (bukan cuma berharap prompt dipatuhi):
    featured image di urutan pertama, alt text unik & tidak kepanjangan,
    nama file rapi & tidak kembar."""
    bersih = []
    for g in gambar[:MAKS_GAMBAR]:
        bersih.append({
            "posisi": re.sub(r"\s+", " ", str(g.get("posisi", "")).strip()),
            "ide": re.sub(r"\s+", " ", str(g.get("ide", "")).strip()),
            "alt": _potong_alt(str(g.get("alt", ""))),
            "file": str(g.get("file", "")).strip(),
            "sumber": re.sub(r"\s+", " ", str(g.get("sumber", "")).strip()),
        })

    # Featured image wajib ada & jadi urutan pertama.
    idx = next((i for i, g in enumerate(bersih) if "featured" in g["posisi"].lower()), None)
    if idx is None:
        bersih[0]["posisi"] = "Featured image"
    elif idx != 0:
        bersih.insert(0, bersih.pop(idx))

    # Alt featured image wajib menyebut keyword (ini yang paling dibaca mesin pencari).
    inti = _kata_inti(keyword)
    if inti and not any(k in bersih[0]["alt"].lower() for k in inti):
        bersih[0]["alt"] = _potong_alt(f"{bersih[0]['alt']} {keyword}")

    dipakai_alt, dipakai_file = set(), set()
    for i, g in enumerate(bersih, 1):
        # Alt kembar bikin nilai SEO turun → bedakan pakai posisinya.
        if g["alt"].lower() in dipakai_alt:
            g["alt"] = _potong_alt(f"{g['alt']} ({g['posisi'].lower()})")
        dipakai_alt.add(g["alt"].lower())

        nama = re.sub(r"\.(jpg|jpeg|png|webp)$", "", g["file"], flags=re.IGNORECASE)
        nama = _slug(nama) or _slug(f"{keyword}-{i}")
        if nama in dipakai_file:
            nama = f"{nama}-{i}"
        dipakai_file.add(nama)
        g["file"] = f"{nama}.jpg"
    return bersih


def _rencana_cadangan(keyword):
    """Dipakai kalau AI benar-benar gagal — brief tetap bisa dikerjakan intern,
    tinggal ide visualnya diisi mentor."""
    return [
        {
            "posisi": "Featured image",
            "ide": f"Gambar utama yang mewakili topik \"{keyword}\" — tentukan bersama mentor.",
            "alt": _potong_alt(keyword),
            "file": f"{_slug(keyword)}-featured.jpg",
            "sumber": "Desain sendiri di Canva (pakai template di bagian 4)",
        },
        {
            "posisi": "Dalam artikel — setelah paragraf pembuka",
            "ide": f"Foto/ilustrasi pendukung yang menjelaskan \"{keyword}\" — tentukan bersama mentor.",
            "alt": _potong_alt(f"Ilustrasi {keyword}"),
            "file": f"{_slug(keyword)}-1.jpg",
            "sumber": "Dokumentasi produk / link referensi dari mentor",
        },
        {
            "posisi": "Dalam artikel — di bagian tengah",
            "ide": f"Gambar kedua yang memperjelas pembahasan \"{keyword}\" — tentukan bersama mentor.",
            "alt": _potong_alt(f"{keyword} - gambar pendukung"),
            "file": f"{_slug(keyword)}-2.jpg",
            "sumber": "Dokumentasi produk / link referensi dari mentor",
        },
    ]


def _rencana_satu_keyword(keyword, situs="", referensi=None, catatan=""):
    referensi = [r for r in (referensi or []) if str(r).strip()]
    blok_ref = ""
    if referensi:
        blok_ref = (
            "\nLINK REFERENSI GAMBAR dari mentor (gambar diambil/diadaptasi dari sini — "
            "sebutkan link yang relevan di kolom sumber):\n"
            + "\n".join("- " + str(r).strip() for r in referensi)
            + "\n"
        )
    blok_catatan = f"\nCATATAN MENTOR (wajib dituruti): {catatan.strip()}\n" if catatan.strip() else ""
    blok_situs = f" milik website {situs}" if situs else ""

    prompt = (
        f"Kamu Agent Brief Gambar untuk tim SEO{blok_situs}. Sebuah artikel dengan target keyword "
        f"\"{keyword}\" SUDAH selesai ditulis dan sudah tayang, tapi BELUM ada gambarnya sama sekali. "
        "Tugasmu membuat rencana gambar yang harus diinput anak magang.\n\n"
        f"Tentukan {MIN_GAMBAR}-5 gambar: 1 featured image + sisanya gambar di dalam artikel.\n"
        "Untuk tiap gambar tulis:\n"
        "- posisi: \"Featured image\" ATAU \"Dalam artikel — setelah paragraf pembuka\" / "
        "\"Dalam artikel — di bagian <perkiraan subjudul>\".\n"
        "- ide: deskripsi KONKRET apa yang harus terlihat (alat/produk apa, orang & aktivitasnya, "
        "latar tempat, sudut pengambilan gambar). Minimal 1-2 kalimat, cukup jelas untuk langsung "
        "dicari atau difoto. Dilarang abstrak seperti \"gambar produk\" atau \"ilustrasi menarik\".\n"
        "- alt: alt text siap tempel, bahasa Indonesia, deskriptif, maksimal 125 karakter. Sebut "
        "keyword atau variasinya secara WAJAR — jangan semua alt kalimatnya sama.\n"
        "- file: usulan nama file, huruf kecil, pakai tanda hubung, tanpa spasi, akhiri .jpg\n"
        "- sumber: dari mana gambar diambil (mis. foto dokumentasi produk, situs resmi principal, "
        "screenshot software, desain sendiri di Canva).\n\n"
        "ATURAN: jangan mengarang spesifikasi, angka, atau klaim produk. Kalau butuh angka pasti, "
        "tulis \"(cek ke mentor)\". Jangan menyebut nama merek/model alat tertentu kecuali merek itu "
        "memang muncul di link referensi atau catatan mentor — sebut jenis alatnya saja.\n"
        + blok_ref + blok_catatan +
        "\nKembalikan HANYA JSON valid (tanpa backtick):\n"
        "{\"gambar\":[{\"posisi\":\"...\",\"ide\":\"...\",\"alt\":\"...\",\"file\":\"...\",\"sumber\":\"...\"}]}"
    )

    try:
        teks = panggil_gemini(prompt, validasi=_json_rencana_valid)
        data = json.loads(re.sub(r"```json|```", "", teks).strip())
        return _rapikan(data["gambar"], keyword), True
    except Exception:
        return _rencana_cadangan(keyword), False


def _html_satu_keyword(nomor, keyword, rencana, sukses):
    e = html.escape
    poin = []
    for g in rencana:
        poin.append(
            f"<li><strong>{e(g['posisi'])}</strong>"
            "<ul>"
            f"<li>Ide gambar: {e(g['ide'])}</li>"
            f"<li>Alt text: <em>{e(g['alt'])}</em></li>"
            f"<li>Nama file: {e(g['file'])}</li>"
            f"<li>Sumber: {e(g['sumber'])}</li>"
            "</ul></li>"
        )
    catatan = (
        "" if sukses else
        "<p><em>Catatan: ide gambar untuk keyword ini belum berhasil dibuat otomatis — "
        "mentor perlu mengisinya manual.</em></p>"
    )
    return (
        # <h3> supaya nyambung di bawah heading bagian "Daftar artikel & rencana gambar" (<h2>) di brief.
        f"<h3>{nomor}. {e(keyword)}</h3>"
        f"<p>Jumlah gambar yang harus diinput: <strong>{len(rencana)}</strong> "
        f"(1 featured image + {len(rencana) - 1} gambar dalam artikel).</p>"
        f"{catatan}<ul>" + "".join(poin) + "</ul>"
    )


def buat_brief_seo(daftar, situs="", catatan=""):
    """
    daftar: list of {"keyword": str, "referensi": [link, ...]}  (referensi opsional)
    Return {"rencana_html": str, "jumlah_keyword": int, "jumlah_gagal": int}
    """
    bagian, jumlah, gagal = [], 0, 0
    for item in daftar or []:
        if isinstance(item, str):
            item = {"keyword": item}
        keyword = str(item.get("keyword", "")).strip()
        if not keyword:
            continue
        jumlah += 1
        rencana, sukses = _rencana_satu_keyword(
            keyword, situs, item.get("referensi"), catatan
        )
        if not sukses:
            gagal += 1
        bagian.append(_html_satu_keyword(jumlah, keyword, rencana, sukses))

    return {
        "rencana_html": "\n".join(bagian),
        "jumlah_keyword": jumlah,
        "jumlah_gagal": gagal,
    }

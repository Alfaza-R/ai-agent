import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai

load_dotenv()


def _make_client():
    """Buat Gemini client. Dipanggil LAZY (bukan saat import) supaya masalah key
    tidak menjatuhkan seluruh app saat startup — app tetap hidup, error muncul jelas
    per-request."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY tidak ditemukan/kosong di environment server. "
            "Cek Secret 'GEMINI_API_KEY' di Settings Space (pastikan terisi, tanpa spasi)."
        )
    return genai.Client(api_key=key)


class _LazyClient:
    """Proxy: bikin client asli saat pertama kali dipakai (client.models.dst), bukan saat import."""
    _real = None

    def __getattr__(self, name):
        if _LazyClient._real is None:
            _LazyClient._real = _make_client()
        return getattr(_LazyClient._real, name)


client = _LazyClient()

CONTOH_FORMAT = """<h1>Konten Carousel Instagram — Realita Kehidupan Laboran</h1>
<p><strong>Jenis Konten:</strong> Entertaining / Relatable</p>
<p><strong>Format:</strong> Carousel</p>
<p><strong>Warna Dominan:</strong> Merah</p>
<p><strong>Sumber/Referensi:</strong> Timbangan Laboratorium / https://timbanganindonesia.com/product/orion-series/</p>

<h2>SLIDE 1 — Thumbnail</h2>
<p><strong>Visual:</strong></p>
<ul>
  <li>Ilustrasi karakter laboran yang bingung di depan timbangan.</li>
</ul>
<p><strong>Headline:</strong> Momen "Dugaan" di Laboratorium</p>
<p><strong>Sub Headline:</strong> Saat Kamu Sudah Yakin, Tapi Angka Terus Berubah</p>

<h2>SLIDE 2 — Penyebabnya Apa?</h2>
<p><strong>Visual:</strong></p>
<ul>
  <li>Foto timbangan dengan area kerja sedikit berantakan.</li>
</ul>
<p><strong>Headline:</strong> Penyebab Drama Timbangan</p>
<p><strong>Isi:</strong></p>
<ul>
  <li>Pintu Kaca Belum Tertutup Rapat: aliran udara memengaruhi hasil.</li>
</ul>

<h2>SLIDE 3 — Call To Action</h2>
<ul>
  <li>Template CTA yang biasa digunakan.</li>
</ul>"""


# Akun/brand (sosmed) yang bisa dipilih sebelum generate brief — tiap brand punya
# palet warna dominan sendiri untuk template desain, dan namanya dimunculkan di judul brief.
# "warna" berupa LIST warna diskrit (bukan kalimat) supaya bisa dibagi rata (round-robin)
# antar-konten saat jumlah>1 — lihat buat_brief().
BRAND_INFO = {
    "alatuji":        {"label": "Alat Uji",                 "warna": ["Orange", "Hitam", "Biru"]},
    "taharica":       {"label": "Taharica",                  "warna": ["Biru"]},
    "taharicadm":     {"label": "Taharica Data Monitoring",  "warna": ["Cyan", "Biru"]},
    "automationindo": {"label": "Automation Indo",           "warna": ["Merah", "Hitam", "Putih"]},
    "loggerindo":     {"label": "Logger Indo",               "warna": ["Biru"]},
    "timbangan":      {"label": "Timbangan Indonesia",       "warna": ["Merah", "Cream"]},
    "rajaloadcell":   {"label": "Raja Loadcell",             "warna": ["Biru", "Merah"]},
}


# Daftar "sudut konten" untuk variasi brief saat 1 platform diminta banyak brief.
# Key SINGKAT dipakai sebagai value checkbox di frontend (user bisa pilih manual);
# kalau user tidak pilih apa-apa, SUDUT_KONTEN (semua value, urut) dipakai bergiliran
# seperti perilaku lama (sistem yang pilih/variasikan sendiri).
SUDUT_KONTEN_MAP = {
    "Edukasi":            "Edukasi / Tips Praktis",
    "Product Knowledge":  "Product Knowledge (kenalkan fitur & keunggulan produk)",
    "Storytelling":       "Storytelling / Relatable (cerita keseharian yang nyambung dengan produk)",
    "Promosi":            "Promosi / Penawaran (dorong audiens untuk action / beli)",
    "Testimoni":          "Testimoni / Social Proof (bukti & kepercayaan dari pengguna)",
    "Behind The Scenes":  "Behind The Scenes / Proses (di balik layar produk atau layanan)",
    "Mitos vs Fakta":     "Mitos vs Fakta / FAQ (luruskan salah kaprah, jawab pertanyaan umum)",
    "Inspirasi":          "Inspirasi / Motivasi (angkat semangat yang relevan dengan audiens)",
}
SUDUT_KONTEN = list(SUDUT_KONTEN_MAP.values())


def _resolve_sudut_pilihan(daftar_sudut):
    """Ubah daftar KEY singkat (dari checkbox frontend) jadi daftar label lengkap
    SUDUT_KONTEN, dedupe & buang key yang tidak dikenal. Kosong kalau user tidak pilih
    apa-apa (berarti sistem yang pilih/variasikan sendiri, perilaku lama)."""
    keys = [str(k).strip() for k in (daftar_sudut or []) if isinstance(k, str) and str(k).strip()]
    seen, hasil = set(), []
    for k in keys:
        full = SUDUT_KONTEN_MAP.get(k)
        if full and full not in seen:
            seen.add(full)
            hasil.append(full)
    return hasil


def _agent_jumlah(topik, sudut_pilihan, platform):
    """Agent Jumlah: tentukan berapa banyak konten (brief) yang wajar untuk 1 permintaan,
    dipanggil HANYA kalau user tidak menentukan jumlah sendiri (jumlah=0/auto). Bias: 2-3
    konten umum, sesekali 4-5 kalau topiknya kaya, condong ke 1 kalau sudut yang diminta
    cuma Product Knowledge & topiknya sempit -- tapi BUKAN aturan kaku, AI menyesuaikan
    konteks (Product Knowledge juga bisa >1 kalau produknya punya beberapa fitur/poin)."""
    sudut_txt = ", ".join(sudut_pilihan) if sudut_pilihan else "(belum ditentukan user, kamu juga tahu sistem lain akan memvariasikan sudutnya sendiri)"
    prompt = (
        "Kamu Content Strategist. Tentukan JUMLAH konten (brief) paling wajar untuk 1 permintaan berikut.\n"
        f"Platform: {platform}\nTopik: \"{topik}\"\nSudut konten yang diminta user: {sudut_txt}\n\n"
        "PANDUAN (bukan aturan kaku, sesuaikan konteks — pertimbangkan seberapa kaya/luas topiknya):\n"
        "- Umumnya 2-3 konten cukup untuk topik dengan variasi sudut yang wajar.\n"
        "- Sesekali 4-5 kalau topiknya kaya (banyak sub-topik/fitur/sudut pandang berbeda yang layak dipisah, "
        "atau user minta beberapa sudut konten sekaligus).\n"
        "- Condong ke 1 konten KALAU sudut yang diminta HANYA 'Product Knowledge' DAN topiknya sempit/spesifik "
        "(tidak ada variasi berarti) — TAPI kalau produk/topiknya sendiri punya beberapa fitur/poin berbeda yang "
        "layak dipisah, boleh lebih dari 1 walau sudutnya Product Knowledge.\n"
        "- Jangan paksa banyak konten kalau topiknya sempit (lebih baik sedikit & berbobot daripada banyak tapi "
        "mengada-ada/mengulang).\n\n"
        "Kembalikan HANYA satu angka bulat 1-8. TANPA penjelasan, TANPA tanda baca lain, TANPA kata apa pun selain "
        "angkanya."
    )
    try:
        resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        n = int(re.search(r"\d+", resp.text or "").group())
        return max(1, min(n, 8))
    except Exception:
        return 2  # fallback wajar kalau AI gagal / balasan tidak bisa diparse


def _generate_aman(prompt):
    """Panggil Gemini dengan 1x retry kalau error transient (rate limit/timeout/gangguan
    jaringan). Request generate makin banyak panggilan Gemini berurutan (jumlah brief >1,
    Agent Jumlah, checker antar-konten, dst) -> makin besar peluang 1 panggilan kena error
    sesaat. Kalau tetap gagal, kembalikan HTML placeholder yang jelas (BUKAN raise), supaya
    1 kegagalan tidak bikin SELURUH request /buat-brief 500 (brief lain tetap jalan)."""
    for percobaan in range(2):
        try:
            resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
            return resp.text or ""
        except Exception as e:
            if percobaan == 0:
                continue
            return (
                "<h1>⚠️ Gagal membuat konten</h1>"
                f"<p><strong>Error:</strong> Terjadi gangguan saat memanggil AI ({type(e).__name__}). "
                "Coba generate ulang untuk konten ini.</p>"
            )


def baca_link(url):
    if not url:
        return "(tidak ada link referensi)"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        halaman = requests.get(url, headers=headers, timeout=20)
        sup = BeautifulSoup(halaman.text, "html.parser")
        return sup.get_text(separator=" ", strip=True)[:2000]
    except Exception as e:
        return f"(Gagal baca link: {e})"


def buat_brief_satu_platform(topik, link, isi_link, platform, sudut=None, brand=None, instruksi_diferensiasi=None, warna_paksa=None):
    instruksi_sudut = (
        f"- SUDUT KONTEN brief ini: {sudut}. Fokuskan seluruh isi brief ke sudut ini.\n"
        if sudut else ""
    )
    b = BRAND_INFO.get((brand or "").strip().lower())
    if b and warna_paksa:
        # Warna SUDAH ditentukan oleh kode (dibagi rata antar-konten) -> jangan diserahkan ke AI lagi,
        # supaya tidak ada 2+ konten dalam 1 batch kebetulan pilih warna yang sama.
        instruksi_brand = (
            f"- Brief ini untuk akun/brand \"{b['label']}\". Warna Dominan brief ini SUDAH DITENTUKAN SISTEM: "
            f"\"{warna_paksa}\" (SATU warna ini saja). WAJIB: (1) isi field \"Warna Dominan\" PERSIS dengan kata "
            f"\"{warna_paksa}\" SAJA — JANGAN tambah warna lain, JANGAN pakai kata \"dan\", walau menurutmu warna lain "
            f"juga cocok/related dengan topiknya; (2) deskripsi Visual & mood tiap slide juga konsisten pakai nuansa "
            f"warna \"{warna_paksa}\" saja, bukan kombinasi warna lain.\n"
            f"- Sisipkan nama brand \"{b['label']}\" di judul narasi (<h1>) secara natural, mis. \"<Judul konten> — {b['label']}\".\n"
        )
    elif b:
        palet = ", ".join(b["warna"])
        instruksi_brand = (
            f"- Brief ini untuk akun/brand \"{b['label']}\". WAJIB isi \"Warna Dominan\" dengan warna dari palet brand ini: "
            f"{palet}. Kalau ada beberapa pilihan warna, pilih 1 yang paling cocok dengan nuansa kontennya — "
            f"JANGAN pakai warna di luar palet ini.\n"
            f"- Sisipkan nama brand \"{b['label']}\" di judul narasi (<h1>) secara natural, mis. \"<Judul konten> — {b['label']}\".\n"
        )
    else:
        instruksi_brand = ""
    instruksi_beda = (
        f"- WAJIB DIBEDAKAN dari konten lain dalam batch permintaan ini: {instruksi_diferensiasi}\n"
        if instruksi_diferensiasi else ""
    )
    perintah = f"""Kamu adalah content planner profesional untuk brand alat industri/laboratorium.
Buatkan brief konten untuk platform {platform}, untuk dikerjakan tim desain.

PENTING:
- Ikuti PERSIS format dan gaya dari contoh di bawah.
- OUTPUT HARUS HTML. Aturan struktur:
  * Judul narasi (paling atas) pakai <h1>.
  * Judul tiap slide (mis. "SLIDE 1 — Thumbnail") pakai <h2>.
  * Daftar/poin (Visual, Isi, dll) pakai bullet list <ul><li>...</li></ul>.
  * Label singkat (Jenis Konten, Headline, Sub Headline, dsb) pakai <p><strong>Label:</strong> nilai</p>.
- HANYA keluarkan HTML mentah. JANGAN bungkus dengan ```html atau ``` , JANGAN pakai markdown.
- Sesuaikan NUANSA dengan platform {platform}: kalau Instagram lebih santai/relatable, kalau LinkedIn lebih profesional dan informatif.
{instruksi_sudut}{instruksi_brand}{instruksi_beda}- Jangan menambah bagian "Tips Tambahan", "Caption", atau "Hashtag".
- JUMLAH SLIDE (WAJIB): minimal 3 slide (termasuk CTA) — JANGAN PERNAH cuma 1 atau 2 slide, itu terlalu tipis untuk carousel. Target rata-rata 4-5 slide. Maksimal 6 slide (termasuk CTA). Slide terakhir selalu CTA (isi CTA seperti biasa).
- Pada bagian "Sumber/Referensi", tulis link ini: {link}

=== CONTOH FORMAT YANG HARUS DIIKUTI ===
{CONTOH_FORMAT}
=== AKHIR CONTOH ===

=== INFORMASI PRODUK (hasil baca link, pakai untuk konteks isi) ===
{isi_link}
=== AKHIR INFORMASI PRODUK ===

Sekarang buat brief BARU dengan format sama persis untuk:
Topik: {topik}
Platform: {platform}
Pastikan isi nyambung dengan produk dari informasi di atas."""

    hasil = _generate_aman(perintah)

    # Brief Checker: cek koherensi/relevansi, rewrite otomatis kalau perlu (maks 2x)
    try:
        from mesin_brief_checker import periksa_dan_perbaiki
        hasil = periksa_dan_perbaiki(hasil, topik, platform)
    except Exception:
        pass  # kalau checker error, pakai brief asli supaya generate tetap jalan

    if warna_paksa:
        # JAMINAN deterministik: apapun yang ditulis AI di field "Warna Dominan" (model tidak
        # selalu 100% patuh ke instruksi teks, kadang tetap gabung >1 warna), TIMPA di sini
        # supaya hasil akhir PASTI sesuai jatah warna round-robin dari buat_brief().
        hasil = _paksa_warna_dominan(hasil, warna_paksa)

    return hasil


def _paksa_warna_dominan(html, warna):
    """Timpa isi field 'Warna Dominan' di HTML brief dengan `warna` PERSIS, apapun yang
    ditulis AI. Deterministik di kode -> tidak bergantung kepatuhan model ke instruksi.
    Rekonstruksi penuh label+nilai (bukan partial-replace) supaya tahan variasi format kecil
    (kolon di dalam/luar <strong>, spasi ganda, dll)."""
    if not warna or not html:
        return html
    pola = re.compile(r'<strong>\s*Warna\s*Dominan\s*:?\s*</strong>\s*:?\s*[^<]*', re.IGNORECASE)
    if pola.search(html):
        return pola.sub(f'<strong>Warna Dominan:</strong> {warna}', html, count=1)
    return html


def buat_brief(topik, link, daftar_platform, jumlah=0, brand=None, sudut=None):
    # jumlah: 0/kosong = Agent Jumlah yang tentukan sendiri per platform (lihat _agent_jumlah).
    # Kalau user isi angka > 0, itu dipakai apa adanya (dibatasi 1-8) — pilihan user menang.
    try:
        jumlah_req = int(jumlah)
    except (TypeError, ValueError):
        jumlah_req = 0
    jumlah_req = max(0, min(jumlah_req, 8))

    # sudut: key singkat dari checkbox frontend (mis. ["Product Knowledge", "Edukasi"]).
    # Kosong = user tidak pilih -> sistem yang variasikan sendiri (perilaku lama, SUDUT_KONTEN
    # dipakai bergiliran). Kalau user pilih, HANYA sudut itu yang dipakai (bergiliran juga
    # kalau jumlah > banyaknya sudut yang dipilih).
    sudut_pilihan = _resolve_sudut_pilihan(sudut)

    isi_link = baca_link(link)
    b = BRAND_INFO.get((brand or "").strip().lower())
    palet_warna = b["warna"] if b else []

    hasil = {}
    for platform in daftar_platform:
        jumlah_platform = jumlah_req if jumlah_req > 0 else _agent_jumlah(topik, sudut_pilihan, platform)
        jumlah_platform = max(1, min(jumlah_platform, 8))

        sudut_pool = sudut_pilihan if sudut_pilihan else SUDUT_KONTEN

        daftar_brief = []
        for i in range(jumlah_platform):
            if sudut_pilihan:
                # User pilih sudut sendiri -> HORMATI pilihannya, bergiliran, walau cuma 1 brief.
                sudut_i = sudut_pool[i % len(sudut_pool)]
            else:
                # Kalau cuma 1 brief & sistem yang tentukan sudut, biarkan tanpa sudut khusus (perilaku lama).
                sudut_i = sudut_pool[i % len(sudut_pool)] if jumlah_platform > 1 else None
            # Kalau brief > 1 & brand punya beberapa warna -> warna dibagi RATA bergiliran
            # per index (bukan diserahkan ke AI), supaya tidak ada 2 konten kebetulan warna sama.
            warna_i = palet_warna[i % len(palet_warna)] if (jumlah_platform > 1 and palet_warna) else None
            isi = buat_brief_satu_platform(topik, link, isi_link, platform, sudut_i, brand, warna_paksa=warna_i)
            daftar_brief.append({"sudut": sudut_i or "Umum", "isi": isi, "warna": warna_i})

        # Checker ANTAR-konten: cuma relevan kalau lebih dari 1 brief di platform ini.
        if len(daftar_brief) > 1:
            daftar_brief = _diferensiasi_antar_konten(topik, link, isi_link, platform, brand, daftar_brief)

        hasil[platform] = daftar_brief
    return hasil


def _diferensiasi_antar_konten(topik, link, isi_link, platform, brand, daftar_brief, maks=2):
    """AI Checker ANTAR-konten: bandingkan semua brief dalam 1 platform (hasil 1
    permintaan) agar tidak ada 2+ yang SUBSTANSINYA sama walau kalimatnya beda.
    Kalau ada yang mirip, brief itu ditulis ulang Writer dengan arahan diferensiasi
    spesifik (maks `maks` putaran, sama seperti pola checker lain di proyek ini)."""
    try:
        from mesin_brief_checker import cek_kemiripan_antar_konten
    except Exception:
        return daftar_brief  # checker error -> pakai hasil apa adanya, jangan gagalkan generate

    for _ in range(maks):
        try:
            cek = cek_kemiripan_antar_konten(topik, platform, daftar_brief)
        except Exception:
            break
        instruksi = cek.get("instruksi_revisi") or {}
        if not instruksi:
            break

        berubah = False
        for idx_str, catatan in instruksi.items():
            try:
                idx = int(idx_str)
            except (TypeError, ValueError):
                continue
            if not (0 <= idx < len(daftar_brief)) or not catatan:
                continue
            sudut = daftar_brief[idx].get("sudut")
            sudut = None if sudut in (None, "", "Umum") else sudut
            warna_i = daftar_brief[idx].get("warna")
            baru = buat_brief_satu_platform(
                topik, link, isi_link, platform, sudut, brand,
                instruksi_diferensiasi=catatan, warna_paksa=warna_i
            )
            if baru and baru.strip() != (daftar_brief[idx].get("isi") or "").strip():
                daftar_brief[idx]["isi"] = baru
                berubah = True

        if not berubah:
            break

    return daftar_brief
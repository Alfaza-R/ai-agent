import os
import re
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

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

MODEL_UTAMA = "gemini-3.1-flash-lite"
MODEL_CADANGAN = "gemini-3.5-flash-lite"  # dipakai kalau model utama sibuk/error berulang


def panggil_gemini(prompt, validasi=None):
    """Panggil Gemini yang tahan gangguan sesaat (rate limit 429, server sibuk 503, timeout,
    balasan kosong). Coba model utama 3x lalu model cadangan 2x, dengan jeda makin panjang
    (3, 6, 12, 20 detik). `validasi(teks) -> bool` opsional: balasan yang tidak lolos dianggap
    gagal & dicoba ulang. Raise RuntimeError kalau semua percobaan gagal."""
    urutan = [MODEL_UTAMA, MODEL_UTAMA, MODEL_UTAMA, MODEL_CADANGAN, MODEL_CADANGAN]
    jeda = [3, 6, 12, 20]
    err_terakhir = None
    for i, model in enumerate(urutan):
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            teks = (resp.text or "").strip()
            if teks and (validasi is None or validasi(teks)):
                return teks
            err_terakhir = RuntimeError(f"balasan {model} kosong/tidak valid")
        except Exception as e:
            err_terakhir = e
            if getattr(e, "code", None) in (401, 403):
                break  # masalah API key/izin -- diulang pun percuma
        if i < len(jeda):
            time.sleep(jeda[i])
    raise RuntimeError(f"Gemini gagal setelah beberapa percobaan: {err_terakhir}")

CONTOH_FORMAT = """<h1>Konten Carousel Instagram — Realita Kehidupan Laboran</h1>
<p><strong>Jenis Konten:</strong> Entertaining / Relatable</p>
<p><strong>Format:</strong> Carousel</p>
<p><strong>Warna Dominan:</strong> Merah</p>
<p><strong>Sumber/Referensi:</strong> Timbangan Laboratorium / https://timbanganindonesia.com/product/orion-series/</p>

<h2>SLIDE 1 — Thumbnail</h2>
<p><strong>Visual:</strong></p>
<ul>
  <li>Jenis visual: foto realistis (bukan ilustrasi flat).</li>
  <li>Objek utama: timbangan analitik digital Orion Series dengan kaca pelindung (draft shield) terbuka setengah, layar menampilkan angka 0.0012 g yang terus berubah.</li>
  <li>Latar/suasana: ruang laboratorium kimia, meja kerja granit putih, rak berisi botol reagen dan beaker kaca sedikit blur di belakang, lampu neon putih dari atas.</li>
  <li>Elemen pendukung: laboran berjas lab putih dan sarung tangan nitril memegang spatula berisi serbuk, dahi berkerut menatap layar timbangan.</li>
  <li>Komposisi & warna: diambil dari samping kanan (sudut 45°), fokus tajam di layar timbangan; merah muncul sebagai aksen di tutup botol reagen, label rak, dan frame teks; ruang kosong di sisi kiri untuk headline.</li>
</ul>
<p><strong>Headline:</strong> Momen "Dugaan" di Laboratorium</p>
<p><strong>Sub Headline:</strong> Saat Kamu Sudah Yakin, Tapi Angka Terus Berubah</p>

<h2>SLIDE 2 — Penyebabnya Apa?</h2>
<p><strong>Visual:</strong></p>
<ul>
  <li>Jenis visual: foto close-up realistis dengan 1 panah penanda (callout) grafis.</li>
  <li>Objek utama: pintu kaca samping timbangan analitik yang masih terbuka sekitar 3 cm, butiran serbuk di wadah timbang tampak sedikit bergeser.</li>
  <li>Latar/suasana: area kerja lab dengan kipas angin dinding dan pintu ruangan terbuka terlihat blur di belakang, menandakan ada aliran udara.</li>
  <li>Elemen pendukung: panah callout menunjuk celah pintu kaca dengan teks kecil "aliran udara masuk".</li>
  <li>Komposisi & warna: close-up dari depan agak atas; merah dipakai di panah callout dan garis bawah teks, latar tetap foto ruangan lab yang terlihat jelas.</li>
</ul>
<p><strong>Headline:</strong> Penyebab Drama Timbangan</p>
<p><strong>Isi:</strong></p>
<ul>
  <li>Pintu Kaca Belum Tertutup Rapat: aliran udara memengaruhi hasil.</li>
</ul>

<h2>SLIDE 3 — Call To Action</h2>
<p><strong>Visual:</strong></p>
<ul>
  <li>Jenis visual: foto realistis.</li>
  <li>Objek utama: timbangan Orion Series tertutup rapat dengan layar stabil menunjukkan 25.0000 g.</li>
  <li>Latar/suasana: meja lab yang rapi dan bersih, laboran tersenyum sambil mencatat hasil di buku log.</li>
  <li>Elemen pendukung: tombol CTA berbentuk kotak membulat dan logo brand di pojok kanan bawah.</li>
  <li>Komposisi & warna: eye-level, cahaya terang; merah di tombol CTA, pena, dan aksen label, bagian atas foto disisakan untuk teks ajakan.</li>
</ul>
<p><strong>Headline:</strong> Hasil Timbang Stabil Tanpa Drama</p>
<p><strong>Isi:</strong></p>
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
        teks = panggil_gemini(prompt, validasi=lambda t: re.search(r"\d+", t) is not None)
        n = int(re.search(r"\d+", teks).group())
        return max(1, min(n, 8))
    except Exception:
        return 2  # fallback wajar kalau AI gagal / balasan tidak bisa diparse


def _generate_aman(prompt):
    """Panggil Writer lewat panggil_gemini (retry bertahap + model cadangan). Balasan wajib
    berupa brief HTML ber-slide (<h2>) dan tidak terlalu pendek. Return None kalau tetap gagal
    -- JANGAN kembalikan HTML "gagal" karena itu akan ikut tersimpan jadi task; pemanggil yang
    memutuskan (coba lagi nanti / lewati)."""
    try:
        return panggil_gemini(prompt, validasi=lambda t: len(t) >= 300 and "<h2" in t.lower())
    except Exception:
        return None


def baca_link(url, maks=10000):
    """Ambil teks isi halaman referensi. Menu navigasi, header, footer, script, dan form dibuang
    dulu -- sebelumnya teks mentah 2000 karakter pertama habis untuk menu website dan terpotong
    sebelum bagian fitur/spesifikasi produk."""
    if not url:
        return "(tidak ada link referensi)"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        halaman = requests.get(url, headers=headers, timeout=20)
        sup = BeautifulSoup(halaman.text, "html.parser")
        for tag in sup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form", "iframe"]):
            tag.decompose()
        utama = sup.find("main") or sup.find("article") or sup.body or sup
        return utama.get_text(separator=" ", strip=True)[:maks]
    except Exception as e:
        return f"(Gagal baca link: {e})"


def _agent_research(topik, link, isi_link, brand=None):
    """Agent Research: riset produk dari halaman link referensi + topik, lalu susun catatan
    terstruktur (produk, spesifikasi, fitur, aplikasi, masalah, fakta, petunjuk visual, hal yang
    tidak boleh diklaim) sebagai BAHAN untuk Agent Writer. Dijalankan SEKALI per permintaan.
    Coba sekali dengan Google Search grounding (tanpa retry -- kuota grounding bisa habis);
    kalau gagal, riset dari isi halaman saja lewat panggil_gemini. Kalau riset tetap gagal,
    kembalikan isi halaman mentah supaya Writer tetap bisa jalan (perilaku lama)."""
    b = BRAND_INFO.get((brand or "").strip().lower())
    akun = f" untuk akun {b['label']}" if b else ""
    prompt = (
        f"Kamu Agent Research untuk tim content planner brand alat industri/laboratorium{akun}. Tugasmu meriset "
        "produk & topik di bawah sebagai BAHAN untuk penulis brief konten media sosial.\n\n"
        f"TOPIK KONTEN: {topik}\n"
        f"LINK REFERENSI: {link or '(tidak ada)'}\n\n"
        "Susun hasil riset dalam Bahasa Indonesia, poin-poin ringkas, isi FAKTA saja, dengan bagian:\n"
        "1. PRODUK: nama & model persis, merek, kategori.\n"
        "2. SPESIFIKASI KUNCI: angka/spesifikasi penting (rentang ukur, akurasi, kapasitas, konektivitas, daya, "
        "material, sertifikasi/IP rating) — HANYA yang tertulis di sumber.\n"
        "3. FITUR & KEUNGGULAN: fitur utama dan manfaat nyatanya bagi pengguna.\n"
        "4. APLIKASI & PENGGUNA: industri, lokasi, siapa yang memakai, contoh situasi pemakaian nyata.\n"
        "5. MASALAH YANG DISELESAIKAN: masalah audiens yang relevan dengan TOPIK dan bagaimana produk membantu.\n"
        "6. FAKTA UNTUK KONTEN: fakta/angka/tips yang paling relevan dengan TOPIK, siap jadi bahan headline & isi slide.\n"
        "7. PETUNJUK VISUAL: tampilan fisik produk (bentuk, warna casing, komponen yang terlihat, ukuran), "
        "lingkungan pemasangan/pemakaian yang realistis, aktivitas orang saat memakainya.\n"
        "8. JANGAN DIKLAIM: hal penting yang TIDAK ada di sumber atau belum pasti, supaya penulis tidak mengarang.\n\n"
        "ATURAN: JANGAN mengarang angka/spesifikasi. Kalau halaman gagal dibaca atau tidak memuat info produk, riset "
        "berdasarkan topik saja dan tandai poin yang belum terverifikasi dengan \"(perlu dicek)\". Kalau kamu memakai "
        "info dari luar halaman referensi, tandai \"(sumber luar)\" dan jangan ambil info produk merek lain.\n\n"
        "=== ISI HALAMAN REFERENSI ===\n" + (isi_link or "(kosong)") + "\n=== AKHIR ISI HALAMAN ==="
    )
    valid = lambda t: len(t) >= 300

    try:
        cfg = genai_types.GenerateContentConfig(tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())])
        resp = client.models.generate_content(model=MODEL_UTAMA, contents=prompt, config=cfg)
        teks = (resp.text or "").strip()
        if valid(teks):
            return teks
    except Exception:
        pass  # grounding tidak tersedia/kuota habis -> lanjut riset tanpa grounding

    try:
        return panggil_gemini(prompt, validasi=valid)
    except Exception:
        return isi_link


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
            f"juga cocok/related dengan topiknya; (2) di bagian Visual, \"{warna_paksa}\" jadi warna AKSEN/NUANSA yang "
            f"konsisten (lihat ATURAN WARNA & BACKGROUND), bukan warna background polos.\n"
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
{instruksi_sudut}{instruksi_brand}{instruksi_beda}- ATURAN VISUAL (WAJIB di SETIAP slide, termasuk CTA): tulis Visual sebagai 5 bullet berlabel persis seperti contoh — "Jenis visual", "Objek utama", "Latar/suasana", "Elemen pendukung", "Komposisi & warna". Harus SPESIFIK sampai desainer bisa langsung eksekusi tanpa menebak: sebut nama/model produk persis (dari informasi produk), kondisi/aksi yang sedang terjadi, lokasi nyata, orang (siapa, pakai apa, sedang apa) bila ada, properti di sekitar, sudut kamera, pencahayaan, dan area kosong untuk teks. DILARANG deskripsi umum seperti "foto produk", "infografis sederhana", "ikon terkait", "elemen desain", tanpa rincian.
- ATURAN WARNA & BACKGROUND (WAJIB): Warna Dominan dipakai sebagai NUANSA/AKSEN — color grading foto, pencahayaan, properti, pakaian, panah/ikon/frame teks, tombol CTA — BUKAN sebagai background polos. Background tiap slide WAJIB berupa scene/lingkungan nyata yang relevan dengan topik (lokasi, ruangan, alat, aktivitas). Kalau pakai infografis/ikon, taruh di atas foto scene yang relevan. DILARANG: background polos/warna solid, background berwarna saja, gradasi warna saja, pola/elemen abstrak tanpa konteks.
- Jangan menambah bagian "Tips Tambahan", "Caption", atau "Hashtag".
- JUMLAH SLIDE (WAJIB): minimal 3 slide (termasuk CTA) — JANGAN PERNAH cuma 1 atau 2 slide, itu terlalu tipis untuk carousel. Target rata-rata 4-5 slide. Maksimal 6 slide (termasuk CTA). Slide terakhir selalu CTA (isi CTA seperti biasa).
- Pada bagian "Sumber/Referensi", tulis link ini: {link}

=== CONTOH FORMAT YANG HARUS DIIKUTI ===
{CONTOH_FORMAT}
=== AKHIR CONTOH ===

=== HASIL RISET PRODUK (dari Agent Research — BAHAN UTAMA brief) ===
{isi_link}
=== AKHIR HASIL RISET ===

Sekarang buat brief BARU dengan format sama persis untuk:
Topik: {topik}
Platform: {platform}
Pastikan isi nyambung dengan produk dari hasil riset di atas: pakai nama/model, spesifikasi, fitur, dan fakta dari riset untuk headline & isi slide; pakai bagian PETUNJUK VISUAL untuk deskripsi Visual; JANGAN mengklaim hal yang ada di bagian JANGAN DIKLAIM atau yang tidak ada di riset."""

    hasil = _generate_aman(perintah)
    if hasil is None:
        return None  # Writer gagal total -- buat_brief() yang akan coba ulang / melewati

    # Brief Checker: cek jumlah slide, detail visual & background, koherensi; rewrite kalau perlu
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

    # Agent Research: riset produk dari link + topik SEKALI per permintaan; hasilnya dipakai
    # sebagai bahan oleh Agent Writer untuk semua platform & semua brief.
    isi_link = _agent_research(topik, link, baca_link(link), brand)
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

        # Brief yang gagal (server AI sibuk walau sudah retry + model cadangan): beri jeda supaya
        # server reda, lalu coba SEKALI lagi. Yang masih gagal DILEWATI -- tidak pernah dikirim
        # sebagai brief berisi pesan error.
        gagal = [item for item in daftar_brief if not item["isi"]]
        if gagal:
            time.sleep(15)
            for item in gagal:
                sudut_ulang = None if item["sudut"] == "Umum" else item["sudut"]
                item["isi"] = buat_brief_satu_platform(
                    topik, link, isi_link, platform, sudut_ulang, brand, warna_paksa=item["warna"]
                )
        daftar_brief = [item for item in daftar_brief if item["isi"]]

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
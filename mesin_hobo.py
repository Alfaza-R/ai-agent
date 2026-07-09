"""
Mesin AI multi-agent untuk tim SALES & SERVICE produk HOBO (Onset) data logger.

Mirip pipeline BMS, tapi fokus ke penjualan/service data logger HOBO. Agent Product
mengecek website HOBO (onsetcomp.com pabrikan + loggerindo.com distributor) via
Google Search grounding.

Pipeline:
  Reader Teks -> Reader Visual -> Product (cek web HOBO) -> Technical -> Service
    -> Checker (KOORDINATOR: cek Product/Technical/Service vs Reader, kirim koreksi, loop maks 2)
    -> Flow (Mermaid) -> Result (output awam + technical)
"""
import re
import os
import base64
import binascii

from mesin_agent import client  # reuse client Gemini yang sudah ada

try:
    from google.genai import types
except Exception:
    types = None

MODEL = "gemini-3.1-flash-lite"

# Website acuan Agent Product (bisa diubah via Secret)
HOBO_SITES = os.getenv("HOBO_SITES", "onsetcomp.com, loggerindo.com").strip()


def _gen(prompt, file_bytes=None, mime=None):
    contents = [prompt]
    if file_bytes and types is not None:
        contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime or "image/png"))
    resp = client.models.generate_content(model=MODEL, contents=contents)
    return (resp.text or "").strip()


def _gen_search(prompt):
    """Generate dengan Google Search grounding; fallback ke tanpa-search."""
    if types is not None:
        try:
            cfg = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            resp = client.models.generate_content(model=MODEL, contents=[prompt], config=cfg)
            return (resp.text or "").strip()
        except Exception:
            pass
    return _gen(prompt)


def _json(txt, fallback):
    import json
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
        "Kamu Agent Reader (teks) untuk tim sales & service HOBO data logger. Baca chat customer, lalu ekstrak SEMUA "
        "info penting secara terstruktur (poin '-'): kebutuhan/permintaan, parameter yang mau diukur (suhu, kelembapan, "
        "tekanan, curah hujan, level air, arus listrik, CO2, cahaya, dll), lokasi/lingkungan pemasangan (indoor/outdoor/"
        "air/tanah), jumlah titik/channel, durasi & interval logging, kebutuhan software/koneksi (USB, Bluetooth, "
        "HOBOware, HOBOlink, cloud/wireless), apakah ini penjualan/service/troubleshooting/kalibrasi, budget/timeline "
        "bila ada, serta hal yang ambigu/kurang jelas. JANGAN menyimpulkan solusi, hanya rangkum yang tertulis.\n\n"
        "=== CHAT CUSTOMER ===\n" + chat
    )
    return _gen(prompt)


# ── Agent 2: Reader visual (gambar / datasheet / PDF) ─────────────────
def _agent_reader_visual(file_bytes, mime):
    if not file_bytes:
        return "(Tidak ada gambar/datasheet/PDF dari customer.)"
    prompt = (
        "Kamu Agent Reader (visual) untuk tim HOBO data logger. Baca gambar/PDF/datasheet terlampir. Ekstrak info "
        "terstruktur (poin '-'): jenis dokumen (foto lokasi, datasheet, skema pemasangan, dll), model/seri logger atau "
        "sensor yang terlihat, parameter & spesifikasi, jumlah unit/channel, label/anotasi penting, kondisi lingkungan "
        "yang tampak. Kalau ada bagian tidak terbaca, katakan jujur. JANGAN mengarang."
    )
    return _gen(prompt, file_bytes, mime)


# ── Agent Product (fokus HOBO, cek website onsetcomp + loggerindo) ────
def _agent_product(info, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Product untuk produk HOBO (Onset) data logger. Berdasarkan kebutuhan (dari Reader) di bawah, "
        "rekomendasikan produk HOBO yang tepat untuk tiap kebutuhan.\n"
        "UTAMAKAN mencari & memverifikasi dari website resmi/distributor HOBO: " + HOBO_SITES + ". "
        "Sebutkan seri/model HOBO yang cocok bila kamu yakin (mis. HOBO MX-series, U-series, UX-series, Pendant, "
        "RX3000 station, sensor Smart Sensor, dll) beserta parameter yang didukung.\n"
        "Untuk tiap rekomendasi, sertakan: model + fungsi + kenapa cocok. Bila perlu aksesori (kabel, solar shield, "
        "coupler, software HOBOware/HOBOlink), sebutkan juga.\n"
        "Kalau HOBO tidak punya produk untuk suatu kebutuhan, katakan jujur & sebut alternatif kategori.\n"
        "Produk HARUS sesuai kebutuhan Reader. Jangan mengarang model yang tidak kamu yakini; kalau ragu sebut "
        "kategori/seri-nya dan tandai 'perlu verifikasi'.\n\n"
        "=== KEBUTUHAN (DARI READER) ===\n" + info + fb
    )
    return _gen_search(prompt)


# ── Agent Technical (setup, wiring, konfigurasi, BOM) ─────────────────
def _agent_technical(info, produk, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Technical HOBO data logger. Dari kebutuhan + produk terpilih di bawah, susun:\n"
        "1. SETUP & ARSITEKTUR PENGUKURAN: cara kerja & topologi (logger <-> sensor <-> software/cloud), jalur koneksi "
        "(USB/Bluetooth/wireless/HOBOlink), penempatan sensor, interval & durasi logging yang disarankan.\n"
        "2. BILL OF MATERIALS: daftar komponen (logger, sensor, aksesori, kabel, mounting, software) + estimasi jumlah "
        "unit. Bila jumlah titik tidak pasti, beri estimasi + tulis asumsinya.\n"
        "3. CATATAN TEKNIS: kompatibilitas sensor, kebutuhan daya/baterai, proteksi lingkungan (IP rating, solar shield), "
        "hal penting saat instalasi.\n"
        "Bahasa Indonesia teknis yang jelas. Jangan mengarang angka pasti; tandai estimasi.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK TERPILIH ===\n" + produk + fb
    )
    return _gen(prompt)


# ── Agent Service (troubleshooting, kalibrasi, garansi, software) ─────
def _agent_service(info, produk, koreksi=""):
    fb = ("\n\n=== KOREKSI DARI CHECKER (WAJIB dipatuhi) ===\n" + koreksi) if koreksi else ""
    prompt = (
        "Kamu Agent Service untuk produk HOBO data logger (after-sales). Dari kebutuhan + produk di bawah, berikan "
        "info service yang relevan:\n"
        "- TROUBLESHOOTING: bila customer melaporkan masalah (tidak terbaca, offset, baterai, koneksi HOBOware/"
        "HOBOlink), beri langkah diagnosa & solusi.\n"
        "- KALIBRASI: apakah perlu kalibrasi, interval, dan cara/prosedur umumnya.\n"
        "- SOFTWARE: setup HOBOware/HOBOlink, ekspor data, konfigurasi logging.\n"
        "- GARANSI & PERAWATAN: umum untuk produk HOBO + tips perawatan sensor/logger.\n"
        "Kalau chat tidak menyangkut service, cukup beri tips singkat setup & perawatan agar produk awet. "
        "Jangan mengarang kebijakan garansi spesifik; sebut sebagai 'umum, konfirmasi ke distributor'.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK ===\n" + produk + fb
    )
    return _gen(prompt)


# ── Agent Checker (KOORDINATOR) ───────────────────────────────────────
def _agent_checker_all(teks_info, visual_info, produk, teknis, service):
    prompt = (
        "Kamu Agent Checker (KOORDINATOR) untuk tim HOBO. Pastikan SEMUA hasil agent SALING KONSISTEN dan sesuai apa "
        "yang dibaca Reader (teks & gambar). Reader adalah acuan kebenaran kebutuhan customer.\n\n"
        "Periksa:\n"
        "- Apakah PRODUK HOBO yang direkomendasikan benar-benar sesuai kebutuhan & parameter yang disebut Reader?\n"
        "- Apakah TECHNICAL (setup/BOM) sesuai kebutuhan & produk yang dipilih?\n"
        "- Apakah SERVICE relevan dengan konteks (mis. kalau customer minta beli, jangan malah fokus komplain)?\n"
        "- Apakah ada kontradiksi antar agent atau info yang miss/ambigu?\n\n"
        "Kalau ADA yang tidak sesuai, tulis INSTRUKSI KOREKSI spesifik untuk agent terkait.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick):\n"
        "{\"konsisten\": true/false, \"koreksi_product\":\"(kosong bila benar)\", \"koreksi_technical\":\"(kosong bila benar)\", "
        "\"koreksi_service\":\"(kosong bila benar)\", \"inkonsistensi\":[\"...\"], \"pertanyaan_klarifikasi\":[\"...\"], "
        "\"info_terverifikasi\":\"ringkasan kebutuhan final yang sudah selaras\"}\n\n"
        "=== READER TEKS ===\n" + teks_info +
        "\n\n=== READER VISUAL ===\n" + visual_info +
        "\n\n=== HASIL PRODUCT ===\n" + produk +
        "\n\n=== HASIL TECHNICAL ===\n" + teknis +
        "\n\n=== HASIL SERVICE ===\n" + service
    )
    return _json(_gen(prompt), {
        "konsisten": True, "koreksi_product": "", "koreksi_technical": "", "koreksi_service": "",
        "inkonsistensi": [], "pertanyaan_klarifikasi": [],
        "info_terverifikasi": teks_info + "\n" + visual_info,
    })


# ── Agent Flow (flowchart Mermaid) ────────────────────────────────────
def _agent_flow(teknis):
    prompt = (
        "Kamu Agent Flow. Dari deskripsi setup/teknis di bawah, buat DIAGRAM ALUR (flowchart) sistem pengukuran HOBO "
        "dalam sintaks MermaidJS.\n"
        "Aturan:\n"
        "- Baris pertama WAJIB: flowchart TD  (boleh LR bila lebih pas).\n"
        "- Node = komponen (sensor, logger, software HOBOware/HOBOlink, cloud, PC, dll). Pakai ID pendek + label dalam "
        "kurung siku, mis. L1[HOBO MX2301]. HINDARI tanda kutip, koma, titik dua, kurung bulat, karakter khusus di label.\n"
        "- Edge = aliran data/koneksi; beri label protokol bila ada, mis. S1 -->|Smart Sensor| L1.\n"
        "- Maksimal ~15 node, ringkas & jelas.\n"
        "- Kembalikan HANYA kode Mermaid (tanpa backtick, tanpa penjelasan).\n\n"
        "=== SETUP/TEKNIS ===\n" + teknis
    )
    out = _gen(prompt)
    return re.sub(r"```mermaid|```", "", out or "").strip()


# ── Agent Compare (cari produk alternatif merek lain) ─────────────────
def _agent_compare(info, produk):
    prompt = (
        "Kamu Agent Compare untuk tim sales HOBO. Berdasarkan kebutuhan + produk HOBO yang direkomendasikan di bawah, "
        "cari produk ALTERNATIF dari MEREK LAIN yang fungsinya mirip / sama persis untuk tiap kebutuhan (supaya sales "
        "punya opsi selain HOBO).\n"
        "PRIORITAS ASAL PRODUK (WAJIB, berurutan): (1) utamakan produk BARAT dulu — Eropa & Amerika; (2) kalau tidak "
        "ada padanan Barat yang cocok, baru cari produk CHINA; (3) kalau tetap tidak ada, baru produk LOKAL "
        "(Indonesia). Untuk tiap alternatif, SEBUTKAN asal/negara mereknya.\n"
        "Cari & verifikasi di web. Contoh merek pembanding (sesuaikan dengan parameter & prioritas asal di atas): "
        "Campbell Scientific (AS), Lascar Electronics (Inggris), Testo (Jerman), Vaisala (Finlandia), Tinytag/Gemini "
        "(Inggris), Dwyer/Omega (AS); China: Elitech, RC-series, dll; lokal bila ada.\n"
        "Untuk tiap produk HOBO, beri 1-2 padanan merek lain + model + kenapa setara. Buat juga TABEL Markdown: "
        "Kebutuhan | Produk HOBO | Alternatif (merek+model) | Perbedaan utama (fitur/akurasi/konektivitas).\n"
        "Realistis; jangan mengarang model. Kalau ragu, sebut kategori + tandai 'perlu verifikasi'.\n\n"
        "=== KEBUTUHAN ===\n" + info + "\n\n=== PRODUK HOBO TERPILIH ===\n" + produk
    )
    return _gen_search(prompt)


# ── Agent Budget (estimasi harga modal & penawaran) ───────────────────
def _agent_budget(info, produk, compare):
    prompt = (
        "Kamu Agent Budget untuk Taharica (supplier/distributor alat ukur). Dari daftar produk HOBO + alternatif "
        "(hasil Agent Compare) di bawah, buat ESTIMASI BIAYA.\n"
        "PENTING: kamu TIDAK tahu harga beli/margin internal Taharica yang sebenarnya. Buat estimasi KASAR berbasis "
        "harga pasar/list dari web, lalu terapkan ASUMSI yang kamu sebutkan eksplisit. Selalu beri RENTANG harga, "
        "sebut mata uang (USD/IDR), dan tandai '(estimasi, wajib diverifikasi)'. Jangan mengarang angka pasti.\n"
        "Asumsi default (sebutkan & boleh disesuaikan): harga modal ≈ harga list dikurangi diskon distributor ~25-40%; "
        "harga penawaran ke customer ≈ harga modal + margin ~20-40% (plus catatan bea/kurs/qty bisa mengubah).\n\n"
        "Hasilkan DUA bagian, mencakup produk HOBO DAN alternatif (buat tabel bila memungkinkan):\n"
        "- modal: kisaran HARGA MODAL (biaya beli untuk Taharica sebagai supplier) per item + total kasar.\n"
        "- penawaran: kisaran HARGA PENAWARAN ke customer (harga jual) per item + total kasar.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): {\"modal\":\"...markdown...\", \"penawaran\":\"...markdown...\"}\n\n"
        "=== KEBUTUHAN ===\n" + info +
        "\n\n=== PRODUK HOBO ===\n" + produk +
        "\n\n=== ALTERNATIF (COMPARE) ===\n" + compare
    )
    return _json(_gen_search(prompt), {"modal": "", "penawaran": ""})


# ── Agent Result (3 output: sales HOBO, sales produk lain, teknis) ────
def _agent_result(info, inkon, tanya, produk, teknis, service, compare, budget):
    modal = (budget or {}).get("modal", "") or "-"
    penawaran = (budget or {}).get("penawaran", "") or "-"
    prompt = (
        "Kamu Agent Result untuk tim sales & service HOBO. Berdasarkan SELURUH data di bawah, buat TIGA output Bahasa "
        "Indonesia:\n"
        "1. output_awam_hobo: rekomendasi balasan untuk SALES memakai produk HOBO (bahasa sederhana, siap dipakai "
        "membalas customer; sebut produk HOBO + poin service + kisaran harga penawaran bila relevan).\n"
        "2. output_awam_lain: rekomendasi balasan versi PRODUK ALTERNATIF (merek lain dari Agent Compare) sebagai opsi "
        "kedua untuk customer (sebut merek+model alternatif + kelebihan/kekurangan singkat + kisaran harga penawaran).\n"
        "3. output_technical: rangkuman teknis mendetail untuk tim teknik/service (produk HOBO + alternatif, setup/BOM, "
        "service/kalibrasi/software, perbandingan teknis, dan ringkasan estimasi biaya modal vs penawaran).\n"
        "Sertakan pertanyaan klarifikasi bila ada. Tandai angka harga sebagai estimasi. JANGAN mengarang di luar data.\n\n"
        "Kembalikan HANYA JSON valid (tanpa backtick): "
        "{\"output_awam_hobo\":\"...\", \"output_awam_lain\":\"...\", \"output_technical\":\"...\"}\n\n"
        "=== INFO TERVERIFIKASI ===\n" + info +
        "\n\n=== INKONSISTENSI ===\n" + ("; ".join(map(str, inkon)) or "-") +
        "\n\n=== PERTANYAAN KLARIFIKASI ===\n" + ("; ".join(map(str, tanya)) or "-") +
        "\n\n=== PRODUK HOBO ===\n" + produk +
        "\n\n=== ALTERNATIF (COMPARE) ===\n" + compare +
        "\n\n=== TEKNIS ===\n" + teknis +
        "\n\n=== SERVICE ===\n" + service +
        "\n\n=== ESTIMASI MODAL ===\n" + modal +
        "\n\n=== ESTIMASI PENAWARAN ===\n" + penawaran
    )
    return _json(_gen(prompt), {"output_awam_hobo": "", "output_awam_lain": "", "output_technical": ""})


def analisa_hobo(chat, image_base64="", image_mime="image/png", riwayat=""):
    chat = (chat or "").strip()
    riwayat = (riwayat or "").strip()
    file_bytes = None
    mime = None

    # Percakapan berlanjut: gabungkan riwayat + pesan terbaru sebagai konteks Reader.
    if riwayat:
        chat_ctx = ("=== RIWAYAT PERCAKAPAN SEBELUMNYA ===\n" + riwayat +
                    "\n\n=== PESAN CUSTOMER TERBARU (fokus utama balasan) ===\n" + chat)
    else:
        chat_ctx = chat

    # Siapkan file (gambar / PDF) — opsional
    if image_base64 and types is not None:
        try:
            file_bytes = base64.b64decode(image_base64)
        except (binascii.Error, ValueError):
            file_bytes = None
        if file_bytes:
            mime = image_mime or "image/png"

    # 1) Reader (acuan kebenaran) — termasuk riwayat bila ada
    teks_info   = _agent_reader_teks(chat_ctx)
    visual_info = _agent_reader_visual(file_bytes, mime)
    sumber      = "TEKS:\n" + teks_info + "\n\nVISUAL:\n" + visual_info

    # 2) Product + Technical + Service, lalu Checker koordinator (loop maks 2)
    koreksi_p = koreksi_t = koreksi_s = ""
    produk = teknis = service = ""
    checker = {}
    for _ in range(2):
        produk  = _agent_product(sumber, koreksi_p)
        teknis  = _agent_technical(sumber, produk, koreksi_t)
        service = _agent_service(sumber, produk, koreksi_s)
        checker = _agent_checker_all(teks_info, visual_info, produk, teknis, service)
        if checker.get("konsisten", True):
            break
        koreksi_p = checker.get("koreksi_product", "") or ""
        koreksi_t = checker.get("koreksi_technical", "") or ""
        koreksi_s = checker.get("koreksi_service", "") or ""
        if not (koreksi_p or koreksi_t or koreksi_s):
            break

    info  = checker.get("info_terverifikasi", "") or sumber
    inkon = checker.get("inkonsistensi", []) or []
    tanya = checker.get("pertanyaan_klarifikasi", []) or []

    # 3) Compare (cari alternatif merek lain) + Budget (estimasi harga)
    compare = _agent_compare(info, produk)
    budget  = _agent_budget(info, produk, compare)

    # 4) Flow + Result (3 output)
    flow  = _agent_flow(teknis)
    hasil = _agent_result(info, inkon, tanya, produk, teknis, service, compare, budget)

    return {
        "reader_teks":            teks_info,
        "reader_visual":          visual_info,
        "info_terverifikasi":     info,
        "inkonsistensi":          inkon,
        "pertanyaan_klarifikasi": tanya,
        "produk":                 produk,
        "teknis":                 teknis,
        "service":                service,
        "compare":                compare,
        "budget_modal":           (budget.get("modal") or "").strip(),
        "budget_penawaran":       (budget.get("penawaran") or "").strip(),
        "flow_mermaid":           flow,
        "output_awam_hobo":       (hasil.get("output_awam_hobo") or "").strip(),
        "output_awam_lain":       (hasil.get("output_awam_lain") or "").strip(),
        "output_technical":       (hasil.get("output_technical") or "").strip(),
    }

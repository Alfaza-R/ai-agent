# Agent: Fakopp — Sales & Service Assistant (pipeline multi-agent, chat mode)

Bantu tim sales & service alat **Fakopp** (uji pohon & kayu berbasis akustik) memahami permintaan customer → 2 output (awam & teknis) + skematik. Pola sama seperti HOBO; Agent Product mengecek website Fakopp.

## File
- Backend: `mesin_fakopp.py` — fungsi `analisa_fakopp(chat, image_base64, image_mime, riwayat)`.
- Endpoint: `POST /fakopp-sales` di `main.py`.
- Frontend: `agent-fakopp/fakopp.html` (chat mode 2 kolom, tema hijau, download PNG skematik).

## Input (JSON)
```json
{ "chat":"...pesan customer terbaru...", "image_base64":"...", "image_mime":"image/png | application/pdf",
  "riwayat":"transkrip percakapan sebelumnya (opsional)" }
```

## Pipeline
1. **🅰️ Reader Teks** — tujuan uji (deteksi busuk/rongga, stabilitas pohon, grading kayu/MOE, riset), objek (pohon/log/kayu), jumlah, konteks.
2. **🅱️ Reader Visual** — foto pohon/lokasi/kondisi batang, datasheet, hasil uji.
3. **📦 Product** — rekomendasi produk Fakopp; **utamakan cek** `fakopp.com`. Contoh: ArborSonic 3D Tomograph (busuk/rongga), DynaRoot (stabilitas/risiko tumbang), Microsecond Timer (MOE/deteksi kerusakan).
4. **🔧 Technical** — metode & setup pengukuran + BOM + catatan interpretasi.
5. **🛠️ Service** — kalibrasi, software (ArborSonic/DynaRoot), training, troubleshooting, garansi.
6. **✅ Checker — KOORDINATOR** — cek Product/Technical/Service vs Reader (mis. tujuan stabilitas harus DynaRoot, bukan tomograph); kirim koreksi (loop maks 2x).
7. **🗺️ Flow** — MermaidJS alur pengukuran.
8. **🎯 Result** — output awam (sales) + teknis (tim teknik/service).

## Output (JSON)
```json
{ "reader_teks","reader_visual","info_terverifikasi","inkonsistensi":[],
  "pertanyaan_klarifikasi":[],"produk","teknis","service","flow_mermaid",
  "output_awam","output_technical" }
```

## Konfigurasi
- `FAKOPP_SITES` (Secret, default `fakopp.com`) — website acuan Agent Product. Tambah distributor lokal bila ada.

## Model
Gemini `gemini-3.1-flash-lite` (vision + text + Google Search grounding untuk Product).

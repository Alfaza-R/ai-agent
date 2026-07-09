# Agent: HOBO Data Logger — Sales & Service Assistant (pipeline multi-agent)

Bantu tim sales & service memahami permintaan customer soal produk **HOBO (Onset) data logger** → keluar 2 output (awam & teknis) + diagram alur. Mirip agent BMS, tapi fokus data logger + ada Agent Service, dan Agent Product mengecek website HOBO.

## File
- Backend: `mesin_hobo.py` — fungsi `analisa_hobo(chat, image_base64, image_mime)`.
- Endpoint: `POST /hobo-sales` di `main.py`.
- Frontend: `agent-hobo/hobo.html` (render Mermaid + Markdown).

## Input (JSON)
```json
{ "chat":"...pesan customer terbaru...", "image_base64":"...", "image_mime":"image/png | application/pdf",
  "riwayat":"transkrip percakapan sebelumnya (opsional, chat lanjutan)" }
```
File (foto lokasi/datasheet/PDF) opsional — dibaca Gemini vision.

**Chat mode (multi-turn):** frontend `hobo.html` = antarmuka chat 2 kolom (chat kiri, detail agent kanan, scroll independen, background mesh gradient, skematik bisa di-download PNG). Tiap kirim menyertakan `riwayat` agar balasan nyambung. `output_awam` = bubble balasan; `output_technical` + kartu per-agent (termasuk Service) + skematik di panel kanan.

## Pipeline (urutan)
1. **🅰️ Reader Teks** (`_agent_reader_teks`) — ekstrak kebutuhan dari chat (parameter, lokasi, jumlah titik, interval, software, sales/service).
2. **🅱️ Reader Visual** (`_agent_reader_visual`) — baca foto/datasheet/PDF.
   → keduanya = **acuan kebenaran**.
3. **📦 Product** (`_agent_product`) — rekomendasi produk HOBO; **utamakan cek website** `onsetcomp.com` & `loggerindo.com` (Google Search grounding). Sebut seri/model (MX, U/UX-series, Pendant, RX3000, Smart Sensor, dll).
4. **🔧 Technical** (`_agent_technical`) — setup/arsitektur pengukuran + Bill of Materials + catatan teknis.
5. **🛠️ Service** (`_agent_service`) — troubleshooting, kalibrasi, software HOBOware/HOBOlink, garansi/perawatan.
6. **✅ Checker — KOORDINATOR** (`_agent_checker_all`) — cek Product/Technical/Service vs Reader; bila tak selaras → kirim koreksi → agent ulang (loop maks 2x).
7. **🗺️ Flow** (`_agent_flow`) — MermaidJS flowchart alur pengukuran.
8. **🎯 Result** (`_agent_result`) — 2 output (awam untuk sales, teknis untuk tim teknik/service).

## Output (JSON)
```json
{ "reader_teks","reader_visual","info_terverifikasi","inkonsistensi":[],
  "pertanyaan_klarifikasi":[],"produk","teknis","service","flow_mermaid",
  "output_awam","output_technical" }
```

## Konfigurasi
- `HOBO_SITES` (Secret, default `onsetcomp.com, loggerindo.com`) — website acuan Agent Product.

## Model
Gemini `gemini-3.1-flash-lite` (vision + text + Google Search grounding untuk Product).

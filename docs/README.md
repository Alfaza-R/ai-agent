# AI Agents — Peta Proyek

Kumpulan AI agent (backend FastAPI di Hugging Face Spaces + integrasi WordPress/Google Sheet).

## Backend (Hugging Face Space: `arapaza/ai-agent`)
- URL: `https://arapaza-ai-agent.hf.space`
- Deploy: push ke remote `hf` (`git push hf main`) → Space rebuild otomatis.
- Secret di Space: `GEMINI_API_KEY`, `CLOUDCONVERT_API_KEY`.
- File utama: `main.py` (semua endpoint + CORS).

## Daftar Agent & Endpoint
| Agent | File backend | Endpoint | Dipakai di |
|---|---|---|---|
| Content Planner (brief) | `mesin_agent.py` | `POST /buat-brief` | Plugin WP intern-dashboard |
| Brief Checker | `mesin_brief_checker.py` | (nempel di /buat-brief) | otomatis saat generate brief |
| SEO Checker (Yoast) | `mesin_seo.py` | `POST /cek-seo` | Apps Script generator artikel |
| BMS Sales Assistant | `mesin_bms.py` | `POST /bms-sales` | `bms.html` (halaman WP) |
| Article + SEO Generator | Apps Script (`appscript-baru.txt`) | — (di Google Sheet) | Google Spreadsheet |

## Frontend (tempel di Elementor / WordPress)
- `dashboard.html` — hub semua AI agent (dark). Halaman: `eknowledge.taharica.com/taharica-ai-agent/`
- `bms.html` — halaman tool BMS (Mermaid + Markdown render).
- Plugin `intern-dashboard` — integrasi Content Planner (tombol "Brief AI").

## Detail per agent
Lihat file di folder ini:
- [agent-content-planner.md](agent-content-planner.md)
- [agent-brief-checker.md](agent-brief-checker.md)
- [agent-seo-checker.md](agent-seo-checker.md)
- [agent-seo-generator.md](agent-seo-generator.md)
- [agent-bms.md](agent-bms.md)
- [dashboard.md](dashboard.md)

## Cara update singkat
- **Backend berubah** → `git add -A && git commit -m "..." && git push origin main && git push hf main` → tunggu Space Running.
- **Frontend (dashboard/bms html)** → re-paste isi file ke widget HTML Elementor → Update → Ctrl+F5.
- **Apps Script** → salin `appscript-baru.txt` ke editor Apps Script → Save.

## Catatan keamanan (belum dikerjakan)
Kredensial yang pernah ter-expose sebaiknya dirotate: `GEMINI_API_KEY`, 9 App Password WordPress, `CLOUDCONVERT_API_KEY`. File berisi rahasia (`appscript-baru.txt`, `appscriptsheetlama.txt`, `App Password web baru.txt`) sudah di-`.gitignore`.

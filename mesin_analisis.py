"""
Analisis Kinerja Intern.

Sebelumnya prompt & API key Gemini ditaruh langsung di admin-dashboard.html, jadi
key-nya ikut terkirim ke browser setiap orang yang membuka dashboard. Sekarang
dashboard cukup mengirim ANGKA hasil hitungannya ke sini; key tetap di server.

Skor, tier, dan rincian poin tetap dihitung di dashboard (deterministik) — mesin ini
hanya menulis narasinya.
"""
from mesin_agent import panggil_gemini


def _valid(teks):
    return len(teks.strip()) >= 80


def analisa_kinerja(data):
    """
    data: dict berisi nama, divisi, skor, maks, tier, done, progress, pending,
          blocked, total, rincian, daftar_task (list str).
    Return {"paragraf": [str, ...]}.
    """
    nama    = str(data.get("nama", "")).strip() or "Intern"
    divisi  = str(data.get("divisi", "")).strip() or "-"
    skor    = int(data.get("skor", 0) or 0)
    maks    = int(data.get("maks", 0) or 0)
    tier    = str(data.get("tier", "")).strip() or "-"
    done    = int(data.get("done", 0) or 0)
    progres = int(data.get("progress", 0) or 0)
    pending = int(data.get("pending", 0) or 0)
    blocked = int(data.get("blocked", 0) or 0)
    total   = int(data.get("total", 0) or 0)
    rincian = str(data.get("rincian", "")).strip() or "belum ada task"

    persen = round(skor / maks * 100) if maks else 0
    daftar = [str(t).strip() for t in (data.get("daftar_task") or []) if str(t).strip()][:20]
    daftar_teks = "\n".join(daftar) or "Belum ada task"

    prompt = (
        "Kamu adalah manajer HR. Tulis analisis kinerja intern dalam Bahasa Indonesia.\n\n"
        # Harus sama dengan TASK_POINTS di plugin (includes/class-api-tasks.php).
        "SISTEM POIN: Web done=5pts progress=3pts | Design done=5pts progress=2pts | "
        "SEO done=5pts progress=2pts | Video Editing done=5pts progress=2pts | "
        "Interview done=4pts progress=2pts | Recruitment done=4pts progress=2pts | "
        "Development Karyawan done=3pts progress=1pts | Absensi Harian done=1pts progress=0pts | "
        "Admin done=3pts progress=1pts | QC done=4pts progress=2pts | pending/blocked=0pts\n"
        "TIER: S>=85% A>=70% B>=50% C>=30% D<30% dari total poin maksimal\n\n"
        f"INTERN: {nama} ({divisi})\n"
        f"SKOR: {skor}/{maks} poin = {persen}% = Tier {tier}\n"
        f"STATUS TASK: {done} selesai | {progres} on_progress | {pending} pending | "
        f"{blocked} blocked | total {total}\n"
        f"RINCIAN: {rincian}\n\n"
        "DAFTAR TASK:\n" + daftar_teks + "\n\n"
        "Tulis EMPAT paragraf pendek. WAJIB ikuti aturan ini:\n"
        "- Tulis dalam bentuk paragraf biasa, TANPA bullet point, TANPA tanda bintang, "
        "TANPA heading, TANPA markdown apapun.\n"
        "- Setiap paragraf maksimal 2-3 kalimat.\n"
        "- Setiap kalimat HARUS berakhir dengan tanda titik.\n"
        "- Total MAKSIMAL 120 kata.\n\n"
        f"Paragraf 1: Jelaskan mengapa dapat Tier {tier} dengan menyebut angka skor dan "
        "persentase secara eksplisit.\n"
        "Paragraf 2: Sebutkan kekuatan konkret berdasarkan data task.\n"
        "Paragraf 3: Sebutkan masalah konkret — berapa task pending/blocked dan berapa poin yang hilang.\n"
        "Paragraf 4: Satu rekomendasi aksi spesifik yang bisa dilakukan minggu ini."
    )

    teks = panggil_gemini(prompt, validasi=_valid)
    paragraf = [p.strip().replace("**", "") for p in teks.strip().split("\n") if p.strip()]
    return {"paragraf": paragraf}

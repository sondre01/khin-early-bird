import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Jobs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT,
        work_type TEXT DEFAULT 'Unknown',
        job_type TEXT DEFAULT 'Regular',
        role_category TEXT DEFAULT 'software_engineering',
        salary TEXT,
        description TEXT,
        apply_url TEXT,
        posted_date TEXT,
        extracted_at TEXT,
        status TEXT DEFAULT 'new'
    )
    """)
    
    # Evaluations Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS evaluations (
        job_id TEXT PRIMARY KEY,
        match_score INTEGER DEFAULT 0,
        match_level TEXT DEFAULT 'Low Match',
        is_applicable BOOLEAN DEFAULT 1,
        match_reasons TEXT,
        matched_skills TEXT,
        missing_skills TEXT,
        evaluated_at TEXT,
        ai_model TEXT,
        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
    )
    """)
    
    # Scrape Runs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scrape_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        total_scraped INTEGER DEFAULT 0,
        total_new INTEGER DEFAULT 0,
        total_high_match INTEGER DEFAULT 0,
        status TEXT DEFAULT 'running',
        log TEXT
    )
    """)
    
    # Settings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    conn.commit()
    conn.close()

def save_job(job: Dict[str, Any]) -> bool:
    """Inserts a job if not exists. Returns True if newly inserted, False if already existed."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    try:
        cursor.execute("""
        INSERT INTO jobs (
            id, source, title, company, location, work_type, job_type,
            role_category, salary, description, apply_url, posted_date, extracted_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            company=excluded.company,
            location=excluded.location,
            work_type=excluded.work_type,
            job_type=excluded.job_type,
            role_category=excluded.role_category,
            salary=excluded.salary,
            description=excluded.description,
            apply_url=excluded.apply_url
        """, (
            job["id"],
            job.get("source", "Unknown"),
            job.get("title", "Unknown Title"),
            job.get("company", "Unknown Company"),
            job.get("location", "Philippines"),
            job.get("work_type", "Unknown"),
            job.get("job_type", "Regular"),
            job.get("role_category", "software_engineering"),
            job.get("salary", "Not disclosed"),
            job.get("description", ""),
            job.get("apply_url", "#"),
            job.get("posted_date", ""),
            job.get("extracted_at", now),
            job.get("status", "new")
        ))
        is_new = cursor.rowcount == 1
        conn.commit()
        return is_new
    finally:
        conn.close()

def save_evaluation(evaluation: Dict[str, Any]):
    """Saves AI match evaluation for a job"""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    try:
        cursor.execute("""
        INSERT INTO evaluations (
            job_id, match_score, match_level, is_applicable,
            match_reasons, matched_skills, missing_skills, evaluated_at, ai_model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            match_score=excluded.match_score,
            match_level=excluded.match_level,
            is_applicable=excluded.is_applicable,
            match_reasons=excluded.match_reasons,
            matched_skills=excluded.matched_skills,
            missing_skills=excluded.missing_skills,
            evaluated_at=excluded.evaluated_at,
            ai_model=excluded.ai_model
        """, (
            evaluation["job_id"],
            evaluation.get("match_score", 0),
            evaluation.get("match_level", "Low Match"),
            1 if evaluation.get("is_applicable", True) else 0,
            json.dumps(evaluation.get("match_reasons", [])),
            json.dumps(evaluation.get("matched_skills", [])),
            json.dumps(evaluation.get("missing_skills", [])),
            now,
            evaluation.get("ai_model", "gemini-2.5-flash")
        ))
        conn.commit()
    finally:
        conn.close()

def get_jobs(
    job_type: Optional[str] = None,
    role_category: Optional[str] = None,
    source: Optional[str] = None,
    min_score: Optional[int] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT 
        j.*,
        e.match_score,
        e.match_level,
        e.is_applicable,
        e.match_reasons,
        e.matched_skills,
        e.missing_skills,
        e.ai_model
    FROM jobs j
    LEFT JOIN evaluations e ON j.id = e.job_id
    WHERE 1=1
    """
    params = []
    
    if job_type and job_type.lower() != 'all':
        query += " AND LOWER(j.job_type) = LOWER(?)"
        params.append(job_type)
        
    if role_category and role_category.lower() != 'all':
        query += " AND LOWER(j.role_category) = LOWER(?)"
        params.append(role_category)
        
    if source and source.lower() != 'all':
        query += " AND LOWER(j.source) = LOWER(?)"
        params.append(source)
        
    if min_score is not None:
        query += " AND COALESCE(e.match_score, 0) >= ?"
        params.append(min_score)
        
    if status and status.lower() != 'all':
        query += " AND j.status = ?"
        params.append(status)
        
    if search:
        search_pattern = f"%{search}%"
        query += " AND (j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)"
        params.extend([search_pattern, search_pattern, search_pattern])
        
    query += " ORDER BY COALESCE(e.match_score, 0) DESC, j.extracted_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    results = []
    for row in rows:
        d = dict(row)
        for key in ["match_reasons", "matched_skills", "missing_skills"]:
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except Exception:
                    d[key] = [d[key]]
            else:
                d[key] = []
        results.append(d)
        
    conn.close()
    return results

def get_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        j.*,
        e.match_score,
        e.match_level,
        e.is_applicable,
        e.match_reasons,
        e.matched_skills,
        e.missing_skills,
        e.ai_model
    FROM jobs j
    LEFT JOIN evaluations e ON j.id = e.job_id
    WHERE j.id = ?
    """, (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for key in ["match_reasons", "matched_skills", "missing_skills"]:
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = [d[key]]
        else:
            d[key] = []
    return d

def update_job_status(job_id: str, status: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()

def get_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE LOWER(job_type) = 'internship'")
    internships = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE LOWER(job_type) = 'regular'")
    regular_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM evaluations WHERE match_score >= 80")
    high_match_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'applied'")
    applied_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'saved'")
    saved_jobs = cursor.fetchone()[0]
    
    # Group by role category
    cursor.execute("""
    SELECT role_category, COUNT(*) as count 
    FROM jobs 
    GROUP BY role_category
    ORDER BY count DESC
    """)
    role_distribution = {row["role_category"]: row["count"] for row in cursor.fetchall()}
    
    # Group by source
    cursor.execute("""
    SELECT source, COUNT(*) as count 
    FROM jobs 
    GROUP BY source
    ORDER BY count DESC
    """)
    source_distribution = {row["source"]: row["count"] for row in cursor.fetchall()}
    
    # Latest run
    cursor.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 1")
    latest_run_row = cursor.fetchone()
    latest_run = dict(latest_run_row) if latest_run_row else None
    
    conn.close()
    
    return {
        "total_jobs": total_jobs,
        "internships": internships,
        "regular_jobs": regular_jobs,
        "high_match_jobs": high_match_jobs,
        "applied_jobs": applied_jobs,
        "saved_jobs": saved_jobs,
        "role_distribution": role_distribution,
        "source_distribution": source_distribution,
        "latest_run": latest_run
    }

def start_scrape_run() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO scrape_runs (started_at, status, log)
    VALUES (?, 'running', 'Started scraping run')
    """, (datetime.now().isoformat(),))
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id

def finish_scrape_run(run_id: int, total_scraped: int, total_new: int, total_high_match: int, status: str = "completed", log: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE scrape_runs
    SET finished_at = ?, total_scraped = ?, total_new = ?, total_high_match = ?, status = ?, log = ?
    WHERE id = ?
    """, (datetime.now().isoformat(), total_scraped, total_new, total_high_match, status, log, run_id))
    conn.commit()
    conn.close()

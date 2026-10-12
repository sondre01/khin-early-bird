import os
import sqlite3
import json
import shutil
import re
import secrets
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
from app.config import DB_PATH, PROJECT_ROOT, TARGET_CATEGORIES
from app.utils.location import is_ncr_location
from app.utils.experience import is_fresh_grad_acceptable
from app.supabase_client import (
    is_supabase_configured,
    supabase_save_job,
    supabase_save_evaluation,
    supabase_get_jobs,
    supabase_get_job_by_id,
    supabase_update_job_status,
    supabase_get_stats,
    supabase_start_scrape_run,
    supabase_finish_scrape_run,
    supabase_purge_ineligible_jobs,
    sync_sqlite_to_supabase
)

def get_connection() -> sqlite3.Connection:
    if os.getenv("VERCEL") and not DB_PATH.exists():
        possible_seeds = [
            PROJECT_ROOT / "data" / "early_bird.db",
            Path.cwd() / "data" / "early_bird.db",
            Path("/var/task/data/early_bird.db"),
        ]
        for seed_db in possible_seeds:
            if seed_db.exists():
                try:
                    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(seed_db, DB_PATH)
                    break
                except Exception:
                    pass

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

def parse_posted_age_days(posted_str: Optional[str], extracted_at: Optional[str] = None) -> float:
    """Computes posting age in days from human-relative strings or absolute timestamps."""
    if not posted_str:
        if extracted_at:
            try:
                dt = datetime.fromisoformat(extracted_at)
                return max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)
            except Exception:
                pass
        return 999.0
    s = str(posted_str).lower().strip()
    if any(w in s for w in ('just', 'moment', 'second', 'min')):
        return 0.05
    if 'hour' in s:
        m = re.search(r'(\d+)', s)
        h = int(m.group(1)) if m else 1
        return h / 24.0
    if 'today' in s:
        return 0.2
    if 'yesterday' in s:
        return 1.0
    if 'day' in s:
        m = re.search(r'(\d+)', s)
        return float(m.group(1)) if m else 1.0
    if 'week' in s:
        m = re.search(r'(\d+)', s)
        return float(m.group(1)) * 7.0 if m else 7.0
    if 'month' in s:
        m = re.search(r'(\d+)', s)
        return float(m.group(1)) * 30.0 if m else 30.0
    if 'year' in s:
        m = re.search(r'(\d+)', s)
        return float(m.group(1)) * 365.0 if m else 365.0
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y', '%b %d, %Y'):
        try:
            dt = datetime.strptime(s[:10], fmt)
            return max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)
        except Exception:
            pass
    return 999.0
    
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
        gemini_score INTEGER DEFAULT 0,
        ml_score INTEGER DEFAULT 0,
        preference_score INTEGER DEFAULT 0,
        validators_passed INTEGER DEFAULT 0,
        validator_details TEXT DEFAULT '{}',
        FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
    )
    """)

    # Migration for existing evaluations tables
    for col_def in [
        ("gemini_score", "INTEGER DEFAULT 0"),
        ("ml_score", "INTEGER DEFAULT 0"),
        ("preference_score", "INTEGER DEFAULT 0"),
        ("validators_passed", "INTEGER DEFAULT 0"),
        ("validator_details", "TEXT DEFAULT '{}'")
    ]:
        try:
            cursor.execute(f"ALTER TABLE evaluations ADD COLUMN {col_def[0]} {col_def[1]}")
        except Exception:
            pass

    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN notified_at TEXT")
    except Exception:
        pass
    
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

    # Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        is_verified INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user',
        created_at TEXT NOT NULL,
        last_login TEXT
    )
    """)

    # Email Verifications Table (6-digit OTP codes)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_verifications (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        is_used INTEGER DEFAULT 0
    )
    """)

    # User Preferences Table (Categories, Keywords, Locations, Platforms, Gemini Prompts)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id TEXT PRIMARY KEY,
        target_categories TEXT DEFAULT '[]',
        keywords TEXT DEFAULT '[]',
        target_location TEXT DEFAULT 'Metro Manila, Philippines',
        filter_ncr_only INTEGER DEFAULT 1,
        job_types TEXT DEFAULT '["Regular", "Internship"]',
        platforms TEXT DEFAULT '["indeed", "linkedin", "jobstreet"]',
        daily_alert_enabled INTEGER DEFAULT 1,
        alert_time TEXT DEFAULT '08:00',
        gemini_prompt TEXT DEFAULT '',
        gemini_recommendations TEXT DEFAULT '{}',
        updated_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)

    # User Sessions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)
    
    conn.commit()
    seed_default_user(conn)
    conn.close()
    
    try:
        purge_ineligible_jobs()
    except Exception:
        pass

def save_job(job: Dict[str, Any]) -> bool:
    """Inserts a job if not exists. Returns True if newly inserted, False if already existed."""
    if is_supabase_configured():
        return supabase_save_job(job)

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
    """Saves AI & Multi-Validator match evaluation for a job"""
    if is_supabase_configured():
        return supabase_save_evaluation(evaluation)

    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    try:
        cursor.execute("""
        INSERT INTO evaluations (
            job_id, match_score, match_level, is_applicable,
            match_reasons, matched_skills, missing_skills, evaluated_at, ai_model,
            gemini_score, ml_score, preference_score, validators_passed, validator_details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            match_score=excluded.match_score,
            match_level=excluded.match_level,
            is_applicable=excluded.is_applicable,
            match_reasons=excluded.match_reasons,
            matched_skills=excluded.matched_skills,
            missing_skills=excluded.missing_skills,
            evaluated_at=excluded.evaluated_at,
            ai_model=excluded.ai_model,
            gemini_score=excluded.gemini_score,
            ml_score=excluded.ml_score,
            preference_score=excluded.preference_score,
            validators_passed=excluded.validators_passed,
            validator_details=excluded.validator_details
        """, (
            evaluation["job_id"],
            evaluation.get("match_score", 0),
            evaluation.get("match_level", "Low Match"),
            1 if evaluation.get("is_applicable", True) else 0,
            json.dumps(evaluation.get("match_reasons", [])),
            json.dumps(evaluation.get("matched_skills", [])),
            json.dumps(evaluation.get("missing_skills", [])),
            now,
            evaluation.get("ai_model", "tri-validator-ensemble-v1"),
            evaluation.get("gemini_score", 0),
            evaluation.get("ml_score", 0),
            evaluation.get("preference_score", 0),
            evaluation.get("validators_passed", 0),
            json.dumps(evaluation.get("validator_details", {}))
        ))
        conn.commit()
    finally:
        conn.close()

def get_jobs(
    job_type: Optional[str] = None,
    role_category: Optional[str] = None,
    source: Optional[str] = None,
    min_score: Optional[int] = None,
    min_validators: Optional[int] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    hide_applied: bool = False,
    posted_within: Optional[str] = None,
    sort_by: Optional[str] = "recent",
    location_filter: Optional[str] = "ncr",
    unnotified_only: bool = False,
    limit: int = 500,
    offset: int = 0
) -> List[Dict[str, Any]]:
    if is_supabase_configured():
        return supabase_get_jobs(
            job_type=job_type,
            role_category=role_category,
            source=source,
            min_score=min_score,
            min_validators=min_validators,
            search=search,
            status=status,
            hide_applied=hide_applied,
            posted_within=posted_within,
            sort_by=sort_by,
            location_filter=location_filter,
            unnotified_only=unnotified_only,
            limit=limit,
            offset=offset
        )

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
        e.ai_model,
        COALESCE(e.gemini_score, 0) as gemini_score,
        COALESCE(e.ml_score, 0) as ml_score,
        COALESCE(e.preference_score, 0) as preference_score,
        COALESCE(e.validators_passed, 0) as validators_passed,
        e.validator_details
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

    if min_validators is not None and min_validators > 0:
        query += " AND COALESCE(e.validators_passed, 0) >= ?"
        params.append(min_validators)
        
    if status and status.lower() not in ('all', 'active'):
        query += " AND j.status = ?"
        params.append(status)
    elif status == 'dismissed':
        query += " AND j.status = 'dismissed'"
    else:
        # Default: Hide dismissed/cancelled jobs
        query += " AND (j.status IS NULL OR j.status != 'dismissed')"
        
    # Default: Filter out ineligible / hard-rejected jobs (e.g. senior roles or excessive experience)
    query += " AND (e.is_applicable IS NULL OR e.is_applicable = 1)"
        
    if hide_applied:
        query += " AND (j.status IS NULL OR j.status != 'applied')"

    if unnotified_only:
        query += " AND (j.notified_at IS NULL)"
        
    if search:
        search_pattern = f"%{search}%"
        query += " AND (j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)"
        params.extend([search_pattern, search_pattern, search_pattern])
        
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
        if d.get("validator_details"):
            try:
                d["validator_details"] = json.loads(d["validator_details"])
            except Exception:
                d["validator_details"] = {}
        else:
            d["validator_details"] = {}
        d["posted_age_days"] = parse_posted_age_days(d.get("posted_date"), d.get("extracted_at"))

        # Fresh graduate & 0-experience classification tags
        is_fg_ok, fg_reason, is_exp_fg = is_fresh_grad_acceptable(
            d.get("title", ""), d.get("description", ""), d.get("job_type", "Regular")
        )
        d["is_fresh_grad_acceptable"] = is_fg_ok
        d["fresh_grad_reason"] = fg_reason
        d["is_explicit_fresh_grad"] = is_exp_fg

        results.append(d)
        
    conn.close()

    # Recency filter: Automatically exclude jobs posted >= 1 month ago (>= 30 days) by default
    if not posted_within or posted_within.lower() == 'all':
        results = [r for r in results if r["posted_age_days"] < 30.0]
    else:
        pw = posted_within.lower().strip()
        max_days_map = {
            '24h': 1.0,
            '1d': 1.0,
            '3d': 3.0,
            '7d': 7.0,
            '1w': 7.0,
            '14d': 14.0,
            '2w': 14.0,
            '30d': 30.0,
            '1m': 30.0
        }
        max_days = max_days_map.get(pw, 30.0)
        results = [r for r in results if r["posted_age_days"] <= max_days]

    # Location filtering
    if location_filter and location_filter.lower() != "all":
        lf = location_filter.lower()
        if lf == "ncr":
            results = [r for r in results if is_ncr_location(r.get("location"), r.get("work_type"))]
        elif lf == "remote":
            results = [r for r in results if (r.get("work_type") or "").lower() == "remote" or "remote" in (r.get("location") or "").lower()]
        elif lf == "ncr_onsite":
            results = [r for r in results if (r.get("work_type") or "").lower() != "remote" and is_ncr_location(r.get("location"), r.get("work_type"))]

    # Dynamic sorting
    if sort_by == "recent":
        # Freshest posted jobs first (e.g. hours ago, Today, 1 day ago), then highest match score
        results.sort(key=lambda x: (x["posted_age_days"], -(x.get("match_score") or 0)))
    elif sort_by == "score":
        results.sort(key=lambda x: -(x.get("match_score") or 0))
    elif sort_by == "company":
        results.sort(key=lambda x: (x.get("company") or "").lower())
    else:
        results.sort(key=lambda x: (x["posted_age_days"], -(x.get("match_score") or 0)))

    # Apply offset and limit
    if offset > 0:
        results = results[offset:]
    if limit is not None and limit > 0:
        results = results[:limit]

    return results

def get_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    if is_supabase_configured():
        return supabase_get_job_by_id(job_id)

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
        e.ai_model,
        COALESCE(e.gemini_score, 0) as gemini_score,
        COALESCE(e.ml_score, 0) as ml_score,
        COALESCE(e.preference_score, 0) as preference_score,
        COALESCE(e.validators_passed, 0) as validators_passed,
        e.validator_details
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
    if d.get("validator_details"):
        try:
            d["validator_details"] = json.loads(d["validator_details"])
        except Exception:
            d["validator_details"] = {}
    else:
        d["validator_details"] = {}
    return d

def update_job_status(job_id: str, status: str):
    if is_supabase_configured():
        return supabase_update_job_status(job_id, status)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()

def mark_jobs_as_notified(job_ids: List[str]) -> bool:
    """Marks a list of job IDs as notified with the current timestamp so they won't be re-emailed."""
    if not job_ids:
        return False
    if is_supabase_configured():
        from app.supabase_client import supabase_mark_jobs_as_notified
        return supabase_mark_jobs_as_notified(job_ids)

    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    try:
        placeholders = ",".join("?" for _ in job_ids)
        cursor.execute(f"UPDATE jobs SET notified_at = ? WHERE id IN ({placeholders})", [now] + job_ids)
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error marking jobs as notified in SQLite: {e}")
        return False
    finally:
        conn.close()

def get_stats() -> Dict[str, Any]:
    if is_supabase_configured():
        return supabase_get_stats()

    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE (status IS NULL OR status != 'dismissed')")
    total_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE LOWER(job_type) = 'internship' AND (status IS NULL OR status != 'dismissed')")
    internships = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE LOWER(job_type) = 'regular' AND (status IS NULL OR status != 'dismissed')")
    regular_jobs = cursor.fetchone()[0]
    
    cursor.execute("""
    SELECT COUNT(*) FROM evaluations e
    JOIN jobs j ON e.job_id = j.id
    WHERE e.match_score >= 80 AND (j.status IS NULL OR j.status != 'dismissed')
    """)
    high_match_jobs = cursor.fetchone()[0]

    cursor.execute("""
    SELECT COUNT(*) FROM evaluations e
    JOIN jobs j ON e.job_id = j.id
    WHERE e.validators_passed = 3 AND (j.status IS NULL OR j.status != 'dismissed')
    """)
    triple_verified_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'applied'")
    applied_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'saved'")
    saved_jobs = cursor.fetchone()[0]
    
    # Group by role category
    cursor.execute("""
    SELECT role_category, COUNT(*) as count 
    FROM jobs 
    WHERE (status IS NULL OR status != 'dismissed')
    GROUP BY role_category
    ORDER BY count DESC
    """)
    role_distribution = {row["role_category"]: row["count"] for row in cursor.fetchall()}
    
    # Group by source
    cursor.execute("""
    SELECT source, COUNT(*) as count 
    FROM jobs 
    WHERE (status IS NULL OR status != 'dismissed')
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
        "triple_verified_jobs": triple_verified_jobs,
        "applied_jobs": applied_jobs,
        "saved_jobs": saved_jobs,
        "role_distribution": role_distribution,
        "source_distribution": source_distribution,
        "latest_run": latest_run
    }

def start_scrape_run() -> int:
    if is_supabase_configured():
        return supabase_start_scrape_run()

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
    if is_supabase_configured():
        return supabase_finish_scrape_run(run_id, total_scraped, total_new, total_high_match, status, log)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE scrape_runs
    SET finished_at = ?, total_scraped = ?, total_new = ?, total_high_match = ?, status = ?, log = ?
    WHERE id = ?
    """, (datetime.now().isoformat(), total_scraped, total_new, total_high_match, status, log, run_id))
    conn.commit()
    conn.close()

def purge_ineligible_jobs() -> Dict[str, Any]:
    """
    Finds and dismisses/purges all existing jobs in the database that are Senior,
    require 2+ years of experience, or are not suitable for a fresh graduate with 0 experience.
    """
    if is_supabase_configured():
        return supabase_purge_ineligible_jobs()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, company, job_type, description FROM jobs WHERE status IS NULL OR status != 'dismissed'")
    rows = cursor.fetchall()
    
    purged = []
    for row in rows:
        job_id = row["id"]
        title = row["title"]
        company = row["company"]
        job_type = row["job_type"]
        description = row["description"]
        
        is_ok, reason, _ = is_fresh_grad_acceptable(title, description, job_type)
        if not is_ok:
            cursor.execute("UPDATE jobs SET status = 'dismissed' WHERE id = ?", (job_id,))
            cursor.execute("UPDATE evaluations SET is_applicable = 0 WHERE job_id = ?", (job_id,))
            purged.append({
                "id": job_id,
                "title": title,
                "company": company,
                "reason": reason
            })
            
    conn.commit()
    conn.close()
    return {
        "total_scanned": len(rows),
        "purged_count": len(purged),
        "purged_jobs": purged
    }


# =====================================================================
# USER AUTHENTICATION & PREFERENCES DATABASE OPS
# =====================================================================

def seed_default_user(conn: Optional[sqlite3.Connection] = None):
    """
    Seeds Khin Andrei Gamboa's default verified account and initial preferences.
    Gmail: gamboa.khinandrei@gmail.com
    Password: P@55w0rdKag!()
    Username: khinag
    """
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    cursor = conn.cursor()
    try:
        from app.auth import hash_password
        default_email = "gamboa.khinandrei@gmail.com"
        default_name = "Khin Andrei Gamboa"
        default_user = "khinag"
        default_pass = "P@55w0rdKag!()"
        default_hash = hash_password(default_pass)
        now = datetime.now().isoformat()

        cursor.execute("SELECT id FROM users WHERE email = ? OR username = ?", (default_email, default_user))
        row = cursor.fetchone()
        if not row:
            user_id = "user_khin_default"
            cursor.execute("""
            INSERT INTO users (id, email, username, full_name, password_hash, is_verified, role, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 'admin', ?)
            """, (user_id, default_email, default_user, default_name, default_hash, now))
        else:
            user_id = row["id"]
            # Always ensure verified and default credentials match
            cursor.execute("""
            UPDATE users SET password_hash = ?, is_verified = 1, username = ?, full_name = ?
            WHERE id = ?
            """, (default_hash, default_user, default_name, user_id))

        # Check default preferences
        cursor.execute("SELECT user_id FROM user_preferences WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            default_cats = json.dumps(list(TARGET_CATEGORIES.keys()))
            default_keywords = json.dumps([
                "Junior Software Engineer", "Associate Software Engineer", "Fresh Graduate Software Engineer",
                "Junior Python Developer", "Junior Web Developer", "Junior IT Support",
                "Junior Data Analyst", "Junior Data Engineer", "Junior QA Tester"
            ])
            cursor.execute("""
            INSERT INTO user_preferences (
                user_id, target_categories, keywords, target_location, filter_ncr_only,
                job_types, platforms, daily_alert_enabled, alert_time, gemini_prompt,
                gemini_recommendations, updated_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?, 1, '08:00', ?, ?, ?)
            """, (
                user_id, default_cats, default_keywords, "Metro Manila, Philippines",
                json.dumps(["Regular", "Internship"]),
                json.dumps(["indeed", "linkedin", "jobstreet"]),
                "Entry level software engineer and data analyst jobs for fresh graduate in NCR",
                json.dumps({
                    "recommendation_summary": "Default master profile configured for Khin Andrei Gamboa across Indeed, LinkedIn, and Jobstreet.",
                    "platforms": ["indeed", "linkedin", "jobstreet"]
                }),
                now
            ))
        conn.commit()
    except Exception as e:
        logger.error(f"Error seeding default user: {e}")
    finally:
        if should_close:
            conn.close()


def db_create_user(full_name: str, email: str, password: str, is_verified: bool = False, role: str = "user") -> Dict[str, Any]:
    """Creates a new user record with auto-fixated username and default preferences."""
    from app.auth import hash_password, generate_fixated_username
    username = generate_fixated_username(full_name)
    user_id = f"user_{secrets.token_hex(8)}"
    pw_hash = hash_password(password)
    now = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Check existing email
        cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email.lower().strip(),))
        if cursor.fetchone():
            raise ValueError(f"Email {email} is already registered.")

        # Ensure unique username
        base_username = username
        counter = 1
        while True:
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if not cursor.fetchone():
                break
            username = f"{base_username}{counter}"
            counter += 1

        cursor.execute("""
        INSERT INTO users (id, email, username, full_name, password_hash, is_verified, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, email.lower().strip(), username, full_name.strip(), pw_hash, 1 if is_verified else 0, role, now))

        # Default preferences
        default_cats = json.dumps(["software_engineering", "web_development"])
        default_keywords = json.dumps(["Junior Software Engineer", "Associate Software Engineer", "Junior Web Developer"])
        cursor.execute("""
        INSERT INTO user_preferences (
            user_id, target_categories, keywords, target_location, filter_ncr_only,
            job_types, platforms, daily_alert_enabled, alert_time, updated_at
        ) VALUES (?, ?, ?, 'Metro Manila, Philippines', 1, ?, ?, 1, '08:00', ?)
        """, (
            user_id, default_cats, default_keywords,
            json.dumps(["Regular", "Internship"]),
            json.dumps(["indeed", "linkedin", "jobstreet"]),
            now
        ))

        conn.commit()
        return {
            "id": user_id,
            "email": email.lower().strip(),
            "username": username,
            "full_name": full_name.strip(),
            "is_verified": bool(is_verified),
            "role": role,
            "created_at": now
        }
    finally:
        conn.close()


def db_get_user_by_email_or_username(identifier: str) -> Optional[Dict[str, Any]]:
    """Fetches user record by email or fixated username."""
    conn = get_connection()
    cursor = conn.cursor()
    ident = identifier.lower().strip()
    try:
        cursor.execute("""
        SELECT id, email, username, full_name, password_hash, is_verified, role, created_at, last_login
        FROM users
        WHERE LOWER(email) = ? OR LOWER(username) = ?
        """, (ident, ident))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def db_get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetches user record by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT id, email, username, full_name, password_hash, is_verified, role, created_at, last_login
        FROM users WHERE id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def db_verify_user(email: str) -> bool:
    """Marks a user as email verified."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET is_verified = 1 WHERE LOWER(email) = ?", (email.lower().strip(),))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def db_create_verification_code(email: str, code: str, minutes_valid: int = 10) -> str:
    """Stores a 6-digit OTP verification code."""
    conn = get_connection()
    cursor = conn.cursor()
    code_id = f"otp_{secrets.token_hex(8)}"
    now = datetime.now()
    expires_at = (now + timedelta(minutes=minutes_valid)).isoformat()
    try:
        cursor.execute("UPDATE email_verifications SET is_used = 1 WHERE LOWER(email) = ?", (email.lower().strip(),))
        cursor.execute("""
        INSERT INTO email_verifications (id, email, code, created_at, expires_at, is_used)
        VALUES (?, ?, ?, ?, ?, 0)
        """, (code_id, email.lower().strip(), code.strip(), now.isoformat(), expires_at))
        conn.commit()
        return code_id
    finally:
        conn.close()


def db_verify_code(email: str, code: str) -> bool:
    """Verifies a 6-digit OTP code and marks account verified upon match."""
    conn = get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    try:
        cursor.execute("""
        SELECT id FROM email_verifications
        WHERE LOWER(email) = ? AND code = ? AND is_used = 0 AND expires_at >= ?
        ORDER BY created_at DESC LIMIT 1
        """, (email.lower().strip(), code.strip(), now_iso))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE email_verifications SET is_used = 1 WHERE id = ?", (row["id"],))
            cursor.execute("UPDATE users SET is_verified = 1 WHERE LOWER(email) = ?", (email.lower().strip(),))
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def db_create_session(user_id: str, days_valid: int = 30) -> str:
    """Generates and persists an authenticated user session token."""
    conn = get_connection()
    cursor = conn.cursor()
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires_at = (now + timedelta(days=days_valid)).isoformat()
    try:
        cursor.execute("""
        INSERT INTO user_sessions (token, user_id, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        """, (token, user_id, now.isoformat(), expires_at))
        cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (now.isoformat(), user_id))
        conn.commit()
        return token
    finally:
        conn.close()


def db_get_or_create_owner_session(user_id: str, days_valid: int = 30) -> str:
    """Retrieves an existing valid session token for owner, or creates a new one only if none exists."""
    if not user_id:
        return ""
    conn = get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    try:
        cursor.execute("""
        SELECT token FROM user_sessions
        WHERE user_id = ? AND expires_at >= ?
        ORDER BY created_at DESC LIMIT 1
        """, (user_id, now_iso))
        row = cursor.fetchone()
        if row and row["token"]:
            return row["token"]
    finally:
        conn.close()
    return db_create_session(user_id, days_valid=days_valid)


def db_get_user_by_session(token: str) -> Optional[Dict[str, Any]]:
    """Retrieves user profile associated with an active session token."""
    if not token:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    try:
        cursor.execute("""
        SELECT u.id, u.email, u.username, u.full_name, u.is_verified, u.role, u.created_at, u.last_login
        FROM user_sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at >= ?
        """, (token, now_iso))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def db_delete_session(token: str) -> bool:
    """Invalidates an active user session token."""
    if not token:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        conn.commit()
        return True
    finally:
        conn.close()


def db_get_user_preferences(user_id: str) -> Dict[str, Any]:
    """Retrieves customizable scraping and alert preferences for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return {
                "user_id": user_id,
                "target_categories": ["software_engineering", "web_development"],
                "keywords": ["Junior Software Engineer", "Associate Software Engineer"],
                "target_location": "Metro Manila, Philippines",
                "filter_ncr_only": True,
                "job_types": ["Regular", "Internship"],
                "platforms": ["indeed", "linkedin", "jobstreet"],
                "daily_alert_enabled": True,
                "alert_time": "08:00",
                "gemini_prompt": "",
                "gemini_recommendations": {}
            }
        data = dict(row)
        for field, default in [
            ("target_categories", ["software_engineering"]),
            ("keywords", []),
            ("job_types", ["Regular", "Internship"]),
            ("platforms", ["indeed", "linkedin", "jobstreet"]),
            ("gemini_recommendations", {})
        ]:
            try:
                data[field] = json.loads(data.get(field) or ("{}" if isinstance(default, dict) else "[]"))
            except Exception:
                data[field] = default
        data["filter_ncr_only"] = bool(data.get("filter_ncr_only", 1))
        data["daily_alert_enabled"] = bool(data.get("daily_alert_enabled", 1))
        return data
    finally:
        conn.close()


def db_save_user_preferences(user_id: str, prefs: Dict[str, Any]) -> Dict[str, Any]:
    """Saves customized scraping and notification preferences for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    try:
        target_cats = json.dumps(prefs.get("target_categories", []))
        keywords = json.dumps(prefs.get("keywords", []))
        job_types = json.dumps(prefs.get("job_types", ["Regular", "Internship"]))
        platforms = json.dumps(prefs.get("platforms", ["indeed", "linkedin", "jobstreet"]))
        gemini_recs = json.dumps(prefs.get("gemini_recommendations", {}))
        target_location = prefs.get("target_location", "Metro Manila, Philippines")
        filter_ncr_only = 1 if prefs.get("filter_ncr_only", True) else 0
        daily_alert_enabled = 1 if prefs.get("daily_alert_enabled", True) else 0
        alert_time = prefs.get("alert_time", "08:00")
        gemini_prompt = prefs.get("gemini_prompt", "")

        cursor.execute("""
        INSERT INTO user_preferences (
            user_id, target_categories, keywords, target_location, filter_ncr_only,
            job_types, platforms, daily_alert_enabled, alert_time, gemini_prompt,
            gemini_recommendations, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            target_categories=excluded.target_categories,
            keywords=excluded.keywords,
            target_location=excluded.target_location,
            filter_ncr_only=excluded.filter_ncr_only,
            job_types=excluded.job_types,
            platforms=excluded.platforms,
            daily_alert_enabled=excluded.daily_alert_enabled,
            alert_time=excluded.alert_time,
            gemini_prompt=excluded.gemini_prompt,
            gemini_recommendations=excluded.gemini_recommendations,
            updated_at=excluded.updated_at
        """, (
            user_id, target_cats, keywords, target_location, filter_ncr_only,
            job_types, platforms, daily_alert_enabled, alert_time, gemini_prompt,
            gemini_recs, now
        ))
        conn.commit()
        return db_get_user_preferences(user_id)
    finally:
        conn.close()



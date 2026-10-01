import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.config import (
    PROJECT_ROOT, DB_PATH
)
from app.utils.location import is_ncr_location
from app.utils.experience import is_fresh_grad_acceptable

logger = logging.getLogger(__name__)

_supabase_client = None

def get_supabase_client():
    """Returns singleton Supabase client or None if credentials are not configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")).strip()

    if url and key:
        try:
            from supabase import create_client
            _supabase_client = create_client(url, key)
            logger.info("Successfully connected to Supabase cloud database.")
            return _supabase_client
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            return None
    return None

def is_supabase_configured() -> bool:
    """Returns True if valid Supabase credentials exist."""
    return get_supabase_client() is not None

def supabase_save_job(job: Dict[str, Any]) -> bool:
    client = get_supabase_client()
    if not client:
        return False
    now = datetime.now().isoformat()
    payload = {
        "id": job["id"],
        "source": job.get("source", "Unknown"),
        "title": job.get("title", "Unknown Title"),
        "company": job.get("company", "Unknown Company"),
        "location": job.get("location", "Philippines"),
        "work_type": job.get("work_type", "Unknown"),
        "job_type": job.get("job_type", "Regular"),
        "role_category": job.get("role_category", "software_engineering"),
        "salary": job.get("salary", "Not disclosed"),
        "description": job.get("description", ""),
        "apply_url": job.get("apply_url", "#"),
        "posted_date": job.get("posted_date", ""),
        "extracted_at": job.get("extracted_at", now),
        "status": job.get("status", "new")
    }
    try:
        client.table("jobs").upsert(payload).execute()
        return True
    except Exception as e:
        logger.error(f"Supabase save_job error: {e}")
        return False

def supabase_save_evaluation(evaluation: Dict[str, Any]):
    client = get_supabase_client()
    if not client:
        return
    now = datetime.now().isoformat()
    payload = {
        "job_id": evaluation["job_id"],
        "match_score": evaluation.get("match_score", 0),
        "match_level": evaluation.get("match_level", "Low Match"),
        "is_applicable": bool(evaluation.get("is_applicable", True)),
        "match_reasons": json.dumps(evaluation.get("match_reasons", [])),
        "matched_skills": json.dumps(evaluation.get("matched_skills", [])),
        "missing_skills": json.dumps(evaluation.get("missing_skills", [])),
        "evaluated_at": now,
        "ai_model": evaluation.get("ai_model", "tri-validator-ensemble-v1"),
        "gemini_score": evaluation.get("gemini_score", 0),
        "ml_score": evaluation.get("ml_score", 0),
        "preference_score": evaluation.get("preference_score", 0),
        "validators_passed": evaluation.get("validators_passed", 0),
        "validator_details": json.dumps(evaluation.get("validator_details", {}))
    }
    try:
        client.table("evaluations").upsert(payload).execute()
    except Exception as e:
        logger.error(f"Supabase save_evaluation error: {e}")

def supabase_get_jobs(
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
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = client.table("jobs").select("*, evaluations(*)")

        if job_type and job_type.lower() != 'all':
            query = query.ilike("job_type", job_type)
        if role_category and role_category.lower() != 'all':
            query = query.ilike("role_category", role_category)
        if source and source.lower() != 'all':
            query = query.ilike("source", source)

        if status and status.lower() not in ('all', 'active'):
            query = query.eq("status", status)
        elif status == 'dismissed':
            query = query.eq("status", "dismissed")
        else:
            query = query.neq("status", "dismissed")

        if hide_applied:
            query = query.neq("status", "applied")

        if unnotified_only:
            query = query.is_("notified_at", "null")

        if search:
            query = query.or_(f"title.ilike.%{search}%,company.ilike.%{search}%,description.ilike.%{search}%")

        res = query.execute()
        raw_rows = res.data or []

        from app.database import parse_posted_age_days

        results = []
        for r in raw_rows:
            d = dict(r)
            evals = d.pop("evaluations", None)
            ev = evals[0] if (isinstance(evals, list) and len(evals) > 0) else (evals if isinstance(evals, dict) else {})

            d["match_score"] = ev.get("match_score", 0)
            d["match_level"] = ev.get("match_level", "Low Match")
            d["is_applicable"] = ev.get("is_applicable", True)
            d["ai_model"] = ev.get("ai_model", "tri-validator-ensemble-v1")
            d["gemini_score"] = ev.get("gemini_score", 0)
            d["ml_score"] = ev.get("ml_score", 0)
            d["preference_score"] = ev.get("preference_score", 0)
            d["validators_passed"] = ev.get("validators_passed", 0)

            for k in ["match_reasons", "matched_skills", "missing_skills"]:
                val = ev.get(k)
                if isinstance(val, str):
                    try:
                        d[k] = json.loads(val)
                    except Exception:
                        d[k] = [val] if val else []
                elif isinstance(val, list):
                    d[k] = val
                else:
                    d[k] = []

            val_det = ev.get("validator_details")
            if isinstance(val_det, str):
                try:
                    d["validator_details"] = json.loads(val_det)
                except Exception:
                    d["validator_details"] = {}
            elif isinstance(val_det, dict):
                d["validator_details"] = val_det
            else:
                d["validator_details"] = {}

            # Experience & Fresh Graduate tags
            is_fg_ok, fg_reason, is_exp_fg = is_fresh_grad_acceptable(
                d.get("title", ""), d.get("description", ""), d.get("job_type", "Regular")
            )
            d["is_fresh_grad_acceptable"] = is_fg_ok
            d["fresh_grad_reason"] = fg_reason
            d["is_explicit_fresh_grad"] = is_exp_fg

            d["posted_age_days"] = parse_posted_age_days(d.get("posted_date"), d.get("extracted_at"))

            # Filter out inapplicable/hard-rejected jobs by default
            if d["is_applicable"] is False:
                continue

            if min_score is not None and (d["match_score"] or 0) < min_score:
                continue
            if min_validators is not None and (d["validators_passed"] or 0) < min_validators:
                continue

            results.append(d)

        # Recency filter
        if not posted_within or posted_within.lower() == 'all':
            results = [r for r in results if r["posted_age_days"] < 30.0]
        else:
            pw = posted_within.lower().strip()
            max_days_map = {'24h': 1.0, '1d': 1.0, '3d': 3.0, '7d': 7.0, '1w': 7.0, '14d': 14.0, '2w': 14.0, '30d': 30.0}
            max_days = max_days_map.get(pw, 30.0)
            results = [r for r in results if r["posted_age_days"] <= max_days]

        # Location filter
        if location_filter and location_filter.lower() != "all":
            lf = location_filter.lower()
            if lf == "ncr":
                results = [r for r in results if is_ncr_location(r.get("location"), r.get("work_type"))]
            elif lf == "remote":
                results = [r for r in results if (r.get("work_type") or "").lower() == "remote" or "remote" in (r.get("location") or "").lower()]

        # Sorting
        if sort_by == "recent":
            results.sort(key=lambda x: (x["posted_age_days"], -(x.get("match_score") or 0)))
        elif sort_by == "score":
            results.sort(key=lambda x: -(x.get("match_score") or 0))
        elif sort_by == "company":
            results.sort(key=lambda x: (x.get("company") or "").lower())
        else:
            results.sort(key=lambda x: (x["posted_age_days"], -(x.get("match_score") or 0)))

        if offset > 0:
            results = results[offset:]
        if limit is not None and limit > 0:
            results = results[:limit]

        return results
    except Exception as e:
        logger.error(f"Supabase get_jobs error: {e}")
        return []

def supabase_get_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return None
    try:
        res = client.table("jobs").select("*, evaluations(*)").eq("id", job_id).limit(1).execute()
        if not res.data:
            return None
        r = res.data[0]
        evals = r.pop("evaluations", None)
        ev = evals[0] if (isinstance(evals, list) and len(evals) > 0) else (evals if isinstance(evals, dict) else {})
        r["match_score"] = ev.get("match_score", 0)
        r["match_level"] = ev.get("match_level", "Low Match")
        r["is_applicable"] = ev.get("is_applicable", True)
        r["ai_model"] = ev.get("ai_model", "tri-validator-ensemble-v1")
        r["gemini_score"] = ev.get("gemini_score", 0)
        r["ml_score"] = ev.get("ml_score", 0)
        r["preference_score"] = ev.get("preference_score", 0)
        r["validators_passed"] = ev.get("validators_passed", 0)

        for k in ["match_reasons", "matched_skills", "missing_skills"]:
            val = ev.get(k)
            if isinstance(val, str):
                try:
                    r[k] = json.loads(val)
                except Exception:
                    r[k] = [val] if val else []
            elif isinstance(val, list):
                r[k] = val
            else:
                r[k] = []

        val_det = ev.get("validator_details")
        if isinstance(val_det, str):
            try:
                r["validator_details"] = json.loads(val_det)
            except Exception:
                r["validator_details"] = {}
        elif isinstance(val_det, dict):
            r["validator_details"] = val_det
        else:
            r["validator_details"] = {}

        return r
    except Exception as e:
        logger.error(f"Supabase get_job_by_id error: {e}")
        return None

def supabase_update_job_status(job_id: str, status: str):
    client = get_supabase_client()
    if not client:
        return
    try:
        client.table("jobs").update({"status": status}).eq("id", job_id).execute()
    except Exception as e:
        logger.error(f"Supabase update_job_status error: {e}")

def supabase_mark_jobs_as_notified(job_ids: List[str]) -> bool:
    """Marks a list of job IDs as notified in Supabase with current timestamp."""
    client = get_supabase_client()
    if not client or not job_ids:
        return False
    try:
        now = datetime.now().isoformat()
        try:
            # Batch update via in_
            client.table("jobs").update({"notified_at": now}).in_("id", job_ids).execute()
        except Exception:
            # Fallback to individual updates if in_ batch filter encounters limits
            for jid in job_ids:
                client.table("jobs").update({"notified_at": now}).eq("id", jid).execute()
        return True
    except Exception as e:
        logger.error(f"Supabase mark_jobs_as_notified error: {e}")
        return False

def supabase_get_stats() -> Dict[str, Any]:
    client = get_supabase_client()
    if not client:
        return {}
    try:
        res = client.table("jobs").select("id, job_type, role_category, source, status, evaluations(match_score, validators_passed)").neq("status", "dismissed").execute()
        rows = res.data or []

        total_jobs = len(rows)
        internships = sum(1 for r in rows if (r.get("job_type") or "").lower() == 'internship')
        regular_jobs = sum(1 for r in rows if (r.get("job_type") or "").lower() == 'regular')

        high_match_jobs = 0
        triple_verified_jobs = 0
        applied_jobs = sum(1 for r in rows if r.get("status") == 'applied')
        saved_jobs = sum(1 for r in rows if r.get("status") == 'saved')

        role_dist = {}
        source_dist = {}

        for r in rows:
            rc = r.get("role_category") or "other"
            role_dist[rc] = role_dist.get(rc, 0) + 1
            src = r.get("source") or "Unknown"
            source_dist[src] = source_dist.get(src, 0) + 1

            evals = r.get("evaluations")
            ev = evals[0] if (isinstance(evals, list) and len(evals) > 0) else (evals if isinstance(evals, dict) else {})
            if (ev.get("match_score") or 0) >= 80:
                high_match_jobs += 1
            if (ev.get("validators_passed") or 0) == 3:
                triple_verified_jobs += 1

        # Latest scrape run
        runs_res = client.table("scrape_runs").select("*").order("id", desc=True).limit(1).execute()
        latest_run = runs_res.data[0] if runs_res.data else None

        return {
            "total_jobs": total_jobs,
            "internships": internships,
            "regular_jobs": regular_jobs,
            "high_match_jobs": high_match_jobs,
            "triple_verified_jobs": triple_verified_jobs,
            "applied_jobs": applied_jobs,
            "saved_jobs": saved_jobs,
            "role_distribution": role_dist,
            "source_distribution": source_dist,
            "latest_run": latest_run
        }
    except Exception as e:
        logger.error(f"Supabase get_stats error: {e}")
        return {}

def supabase_start_scrape_run() -> int:
    client = get_supabase_client()
    if not client:
        return 0
    try:
        res = client.table("scrape_runs").insert({
            "started_at": datetime.now().isoformat(),
            "status": "running",
            "log": "Started scraping run"
        }).execute()
        return res.data[0]["id"] if res.data else 0
    except Exception as e:
        logger.error(f"Supabase start_scrape_run error: {e}")
        return 0

def supabase_finish_scrape_run(run_id: int, total_scraped: int, total_new: int, total_high_match: int, status: str = "completed", log: str = ""):
    client = get_supabase_client()
    if not client:
        return
    try:
        client.table("scrape_runs").update({
            "finished_at": datetime.now().isoformat(),
            "total_scraped": total_scraped,
            "total_new": total_new,
            "total_high_match": total_high_match,
            "status": status,
            "log": log
        }).eq("id", run_id).execute()
    except Exception as e:
        logger.error(f"Supabase finish_scrape_run error: {e}")

def supabase_purge_ineligible_jobs() -> Dict[str, Any]:
    client = get_supabase_client()
    if not client:
        return {"total_scanned": 0, "purged_count": 0, "purged_jobs": []}
    try:
        res = client.table("jobs").select("id, title, company, job_type, description").neq("status", "dismissed").execute()
        rows = res.data or []
        purged = []
        for r in rows:
            is_ok, reason, _ = is_fresh_grad_acceptable(r.get("title", ""), r.get("description", ""), r.get("job_type", "Regular"))
            if not is_ok:
                client.table("jobs").update({"status": "dismissed"}).eq("id", r["id"]).execute()
                client.table("evaluations").update({"is_applicable": False}).eq("job_id", r["id"]).execute()
                purged.append({"id": r["id"], "title": r["title"], "company": r["company"], "reason": reason})
        return {
            "total_scanned": len(rows),
            "purged_count": len(purged),
            "purged_jobs": purged
        }
    except Exception as e:
        logger.error(f"Supabase purge error: {e}")
        return {"total_scanned": 0, "purged_count": 0, "purged_jobs": []}

def sync_sqlite_to_supabase() -> Dict[str, Any]:
    """Syncs existing SQLite jobs and evaluations into Supabase."""
    client = get_supabase_client()
    if not client:
        return {"success": False, "message": "Supabase credentials not configured."}
    
    import sqlite3
    if not DB_PATH.exists():
        return {"success": False, "message": f"SQLite database {DB_PATH} not found."}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM jobs")
    jobs = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM evaluations")
    evals = [dict(r) for r in cursor.fetchall()]

    conn.close()

    job_count = 0
    for j in jobs:
        try:
            client.table("jobs").upsert(j).execute()
            job_count += 1
        except Exception as e:
            logger.error(f"Error syncing job {j.get('id')}: {e}")

    eval_count = 0
    for ev in evals:
        try:
            # Ensure boolean
            ev["is_applicable"] = bool(ev.get("is_applicable", True))
            client.table("evaluations").upsert(ev).execute()
            eval_count += 1
        except Exception as e:
            logger.error(f"Error syncing evaluation {ev.get('job_id')}: {e}")

    return {
        "success": True,
        "synced_jobs": job_count,
        "synced_evaluations": eval_count,
        "message": f"Successfully synced {job_count} jobs and {eval_count} evaluations to Supabase cloud database!"
    }

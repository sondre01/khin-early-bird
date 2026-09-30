import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.database import get_jobs, get_job_by_id, update_job_status, get_stats
from app.config import (
    USER_NAME, USER_EMAIL, USER_PHONE, USER_LOCATION,
    DAILY_RUN_TIME, EMAIL_NOTIFICATIONS_ENABLED, GEMINI_API_KEY,
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    TARGET_CATEGORIES, JOB_TYPES, update_env_variable, DATA_DIR
)
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.notifier import EmailNotifier
from app.profile_loader import STRUCTURED_PROFILE, load_raw_resume_texts
from app.scheduler import scheduler_instance
from app.pipeline.link_validator import prune_dead_jobs, LinkValidator

logger = logging.getLogger(__name__)
router = APIRouter()

# Global state for active run tracking
active_pipeline_state = {
    "is_running": False,
    "current_phase": 0,
    "phase_name": "Idle",
    "percent": 0,
    "message": "Ready to run",
    "logs": []
}

class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    email_notifications_enabled: Optional[bool] = None
    daily_run_time: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str

@router.get("/api/stats")
async def api_stats():
    stats = get_stats()
    stats["scheduler"] = scheduler_instance.get_status()
    return stats

@router.get("/api/jobs")
async def api_jobs(
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
    location: Optional[str] = "ncr",
    limit: int = 500,
    offset: int = 0
):
    jobs = get_jobs(
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
        location_filter=location,
        limit=limit,
        offset=offset
    )
    return {"jobs": jobs, "count": len(jobs)}

@router.get("/api/cron")
async def api_vercel_cron():
    return {
        "status": "ok",
        "message": "Vercel cron ping received. Autonomous pipeline runs daily via GitHub Actions runner."
    }

@router.get("/api/jobs/{job_id}")
async def api_job_detail(job_id: str):
    job = get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/api/jobs/{job_id}/status")
async def api_update_job_status(job_id: str, payload: StatusUpdate):
    update_job_status(job_id, payload.status)
    return {"success": True, "job_id": job_id, "new_status": payload.status}

@router.get("/api/jobs/{job_id}/action", response_class=HTMLResponse)
async def api_job_quick_action(job_id: str, status: str = "applied"):
    """One-click direct action from daily email digest to cancel out or mark applied"""
    valid_status = status.lower()
    if valid_status not in ("applied", "dismissed", "saved", "new"):
        valid_status = "applied"

    job = get_job_by_id(job_id)
    title = job.get("title", "Job Posting") if job else "Job Opportunity"
    company = job.get("company", "Company") if job else ""

    update_job_status(job_id, valid_status)

    if valid_status == "applied":
        headline = "Application Recorded"
        subtext = "This role is marked as Applied. It will be hidden from all future daily email digests and active job searches."
        badge = "✓ APPLIED"
    elif valid_status == "dismissed":
        headline = "Opportunity Hidden & Cancelled"
        subtext = "This role has been cancelled out and hidden. It will no longer appear in your morning email digests."
        badge = "✕ HIDDEN"
    else:
        headline = "Status Updated"
        subtext = f"Status set to {valid_status}."
        badge = valid_status.upper()

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en" class="h-full bg-[#090A0C]">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{headline} | Khin Early Bird</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="h-full flex items-center justify-center p-4 font-sans text-zinc-300 antialiased">
    <div class="max-w-md w-full bg-[#121316] border border-zinc-800 rounded-2xl p-8 shadow-2xl text-center space-y-6">
        <div class="inline-flex items-center justify-center px-3 py-1 rounded-full text-xs font-mono font-medium tracking-wider bg-zinc-800 text-zinc-300 border border-zinc-700">
            {badge}
        </div>
        <div class="space-y-2">
            <h1 class="text-xl font-bold text-white tracking-tight">{headline}</h1>
            <p class="text-xs text-zinc-400 leading-relaxed">{subtext}</p>
        </div>
        <div class="bg-zinc-900/80 border border-zinc-800/80 rounded-xl p-4 text-left space-y-1">
            <div class="text-[10px] uppercase font-mono tracking-wider text-zinc-500">Target Role</div>
            <div class="text-sm font-semibold text-zinc-200">{title}</div>
            <div class="text-xs text-zinc-400">{company}</div>
        </div>
        <div class="pt-2">
            <a href="/" class="inline-block w-full py-2.5 px-4 rounded-xl text-xs font-semibold bg-white text-black hover:bg-zinc-200 transition shadow-sm">
                Open Web Dashboard &rarr;
            </a>
        </div>
    </div>
</body>
</html>
""")

def run_pipeline_worker():
    global active_pipeline_state
    active_pipeline_state["is_running"] = True
    active_pipeline_state["percent"] = 5
    active_pipeline_state["current_phase"] = 1
    active_pipeline_state["phase_name"] = "Extraction"
    active_pipeline_state["message"] = "Initializing ingestion engine..."
    active_pipeline_state["logs"] = []

    def on_progress(data: Dict[str, Any]):
        active_pipeline_state["current_phase"] = data.get("phase_id", 1)
        active_pipeline_state["phase_name"] = data.get("phase_name", "")
        active_pipeline_state["message"] = data.get("message", "")
        active_pipeline_state["percent"] = data.get("percent", 0)
        active_pipeline_state["logs"].append(f"[{data.get('timestamp')}] [{data.get('phase_name')}] {data.get('message')}")

    try:
        orch = PipelineOrchestrator()
        result = orch.run(limit_per_keyword=3, send_email=True, progress_callback=on_progress)
        active_pipeline_state["message"] = f"Finished! {result.get('total_scraped')} analyzed, {result.get('high_match_count')} high matches."
        active_pipeline_state["percent"] = 100
    except Exception as e:
        active_pipeline_state["message"] = f"Error: {str(e)}"
        active_pipeline_state["logs"].append(f"ERROR: {str(e)}")
    finally:
        active_pipeline_state["is_running"] = False

@router.get("/api/cron")
@router.post("/api/cron")
async def api_cron_trigger(background_tasks: BackgroundTasks):
    """Triggered daily by Vercel Cron or external schedulers"""
    logger.info("Received automated cron trigger from cloud scheduler.")
    orch = PipelineOrchestrator()
    # Run synchronously in serverless context before lambda terminates
    result = orch.run(limit_per_keyword=3, send_email=True)
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "total_analyzed": result.get("total_scraped"),
        "high_matches": result.get("high_match_count"),
        "email_sent": result.get("email_sent")
    }

@router.post("/api/pipeline/run")
async def api_trigger_pipeline(background_tasks: BackgroundTasks):
    global active_pipeline_state
    if active_pipeline_state["is_running"]:
        return {"success": False, "message": "Pipeline is already in progress"}
    
    background_tasks.add_task(run_pipeline_worker)
    return {"success": True, "message": "Pipeline run started in background"}

@router.get("/api/pipeline/status")
async def api_pipeline_status():
    return active_pipeline_state

@router.get("/api/pipeline/stream")
async def api_pipeline_stream():
    """SSE stream for real-time live log and progress updates"""
    async def event_generator():
        last_log_count = 0
        while True:
            current_state = dict(active_pipeline_state)
            new_logs = current_state["logs"][last_log_count:]
            last_log_count = len(current_state["logs"])
            
            payload = {
                "is_running": current_state["is_running"],
                "phase_id": current_state["current_phase"],
                "phase_name": current_state["phase_name"],
                "message": current_state["message"],
                "percent": current_state["percent"],
                "new_logs": new_logs
            }
            yield f"data: {json.dumps(payload)}\n\n"
            
            if not current_state["is_running"] and current_state["percent"] == 100:
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/api/settings")
async def api_get_settings():
    return {
        "user_name": USER_NAME,
        "user_email": USER_EMAIL,
        "user_phone": USER_PHONE,
        "user_location": USER_LOCATION,
        "daily_run_time": os.getenv("DAILY_RUN_TIME", DAILY_RUN_TIME),
        "email_notifications_enabled": os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() in ("1", "true", "yes"),
        "has_gemini_key": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "has_smtp_password": bool(os.getenv("SMTP_PASSWORD", "").strip()),
        "smtp_host": SMTP_HOST,
        "smtp_port": SMTP_PORT,
        "smtp_user": os.getenv("SMTP_USER", SMTP_USER),
        "target_categories": TARGET_CATEGORIES,
        "job_types": JOB_TYPES
    }

@router.post("/api/settings")
async def api_save_settings(settings: SettingsUpdate):
    if settings.gemini_api_key is not None:
        update_env_variable("GEMINI_API_KEY", settings.gemini_api_key.strip())
    if settings.smtp_user is not None:
        update_env_variable("SMTP_USER", settings.smtp_user.strip())
    if settings.smtp_password is not None:
        update_env_variable("SMTP_PASSWORD", settings.smtp_password.strip())
    if settings.email_notifications_enabled is not None:
        update_env_variable("EMAIL_NOTIFICATIONS_ENABLED", "true" if settings.email_notifications_enabled else "false")
    if settings.daily_run_time is not None:
        update_env_variable("DAILY_RUN_TIME", settings.daily_run_time.strip())
        scheduler_instance.update_schedule(settings.daily_run_time.strip())
        
    return {"success": True, "message": "Settings updated successfully"}

@router.post("/api/email/test")
async def api_test_email():
    notifier = EmailNotifier()
    result = notifier.send_test_email(recipient=USER_EMAIL)
    return result

@router.get("/api/preview/digest")
async def api_preview_digest():
    digest_path = DATA_DIR / "latest_digest.html"
    if digest_path.exists():
        with open(digest_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    
    # Generate on the fly from top jobs in database
    jobs = get_jobs(min_score=60, limit=20)
    notifier = EmailNotifier()
    html = notifier.generate_html_digest(jobs)
    return HTMLResponse(content=html)

@router.post("/api/jobs/verify-links")
@router.get("/api/jobs/verify-links")
async def api_verify_links():
    """Audits all active jobs in the database, removes dead/expired application links, and returns results."""
    result = prune_dead_jobs()
    return {
        "success": True,
        "checked": result["checked"],
        "removed": result["removed"],
        "active": result["active"],
        "message": f"Verified {result['checked']} links. Removed {result['removed']} dead/expired listings. {result['active']} active jobs remain."
    }

@router.get("/api/profile")
async def api_candidate_profile():
    raw_resumes = load_raw_resume_texts()
    return {
        "structured": STRUCTURED_PROFILE,
        "resume_files": list(raw_resumes.keys())
    }

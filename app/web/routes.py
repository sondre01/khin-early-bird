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
    search: Optional[str] = None,
    status: Optional[str] = None,
    hide_applied: bool = False,
    sort_by: Optional[str] = "recent",
    limit: int = 500,
    offset: int = 0
):
    jobs = get_jobs(
        job_type=job_type,
        role_category=role_category,
        source=source,
        min_score=min_score,
        search=search,
        status=status,
        hide_applied=hide_applied,
        sort_by=sort_by,
        limit=limit,
        offset=offset
    )
    return {"jobs": jobs, "count": len(jobs)}

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

@router.get("/api/profile")
async def api_candidate_profile():
    raw_resumes = load_raw_resume_texts()
    return {
        "structured": STRUCTURED_PROFILE,
        "resume_files": list(raw_resumes.keys())
    }

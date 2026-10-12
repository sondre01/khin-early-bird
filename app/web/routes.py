import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.database import (
    get_jobs, get_job_by_id, update_job_status, get_stats, purge_ineligible_jobs,
    db_create_user, db_get_user_by_email_or_username, db_get_user_by_id,
    db_create_verification_code, db_verify_code, db_create_session,
    db_get_or_create_owner_session, db_get_user_by_session, db_delete_session,
    db_get_user_preferences, db_save_user_preferences
)
from app.auth import (
    generate_fixated_username, verify_password, generate_otp_code,
    send_otp_email, get_gemini_preference_suggestions
)
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

from app.supabase_client import is_supabase_configured, sync_sqlite_to_supabase

class SettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    email_notifications_enabled: Optional[bool] = None
    daily_run_time: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None

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

@router.post("/api/jobs/purge-senior")
@router.get("/api/jobs/purge-senior")
async def api_purge_senior():
    """Audits active database listings and dismisses roles requiring 2+ years of experience or senior rank."""
    result = purge_ineligible_jobs()
    return {
        "success": True,
        "scanned": result["total_scanned"],
        "purged": result["purged_count"],
        "purged_jobs": result["purged_jobs"],
        "message": f"Purged {result['purged_count']} non-entry/senior roles from database. {result['total_scanned'] - result['purged_count']} fresh-grad compliant jobs remain."
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
        "job_types": JOB_TYPES,
        "is_supabase_configured": is_supabase_configured(),
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "has_supabase_key": bool(os.getenv("SUPABASE_KEY", "").strip() or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip())
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
    if settings.supabase_url is not None:
        update_env_variable("SUPABASE_URL", settings.supabase_url.strip())
    if settings.supabase_key is not None:
        update_env_variable("SUPABASE_KEY", settings.supabase_key.strip())
        
    return {"success": True, "message": "Settings updated successfully"}

@router.post("/api/supabase/sync")
@router.get("/api/supabase/sync")
async def api_supabase_sync():
    """Syncs existing SQLite jobs and evaluations into Supabase cloud database."""
    res = sync_sqlite_to_supabase()
    return res

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
    
    # Generate on the fly from fresh unnotified jobs in database
    jobs = get_jobs(unnotified_only=True, hide_applied=True, min_score=60, limit=15)
    if not jobs:
        jobs = get_jobs(hide_applied=True, min_score=60, limit=15)
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


# =====================================================================
# AUTHENTICATION & USER PREFERENCE SCHEMAS & ROUTES
# =====================================================================

class SignUpRequest(BaseModel):
    full_name: str
    email: str
    password: str

class SignInRequest(BaseModel):
    identifier: str  # email or username
    password: str

class VerifyCodeRequest(BaseModel):
    email: str
    code: str

class ResendCodeRequest(BaseModel):
    email: str

class AISuggestRequest(BaseModel):
    prompt: str
    user_id: Optional[str] = None

class UserPreferencesUpdate(BaseModel):
    target_categories: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    target_location: Optional[str] = None
    filter_ncr_only: Optional[bool] = None
    job_types: Optional[List[str]] = None
    platforms: Optional[List[str]] = None
    daily_alert_enabled: Optional[bool] = None
    alert_time: Optional[str] = None
    gemini_prompt: Optional[str] = None
    gemini_recommendations: Optional[Dict[str, Any]] = None

def get_current_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.query_params.get("token", "")
    if token:
        return db_get_user_by_session(token)
    return None

@router.get("/api/auth/preview-username")
async def api_preview_username(full_name: str = ""):
    """Computes fixated username live: first name + initials of next names (e.g. Khin Andrei Gamboa -> khinag)"""
    username = generate_fixated_username(full_name)
    return {"full_name": full_name, "username": username}

@router.post("/api/auth/sign-up")
async def api_sign_up(payload: SignUpRequest):
    """Registers user with fixated username and dispatches 6-digit verification code to their Gmail"""
    full_name = payload.full_name.strip()
    email = payload.email.lower().strip()
    password = payload.password.strip()

    if not full_name:
        raise HTTPException(status_code=400, detail="Full name is required.")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid Gmail / email address is required.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    fixated_username = generate_fixated_username(full_name)

    # Check if user already exists
    existing = db_get_user_by_email_or_username(email)
    if existing and existing.get("is_verified"):
        raise HTTPException(status_code=400, detail="An account with this email already exists. Please sign in.")

    # Create unverified user if doesn't exist
    if not existing:
        try:
            user = db_create_user(full_name=full_name, email=email, password=password, is_verified=False)
            fixated_username = user["username"]
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        fixated_username = existing["username"]

    # Generate 6-digit OTP code & save in database
    otp_code = generate_otp_code()
    db_create_verification_code(email=email, code=otp_code, minutes_valid=10)

    # Send verification email via Gmail SMTP
    dispatch_result = send_otp_email(recipient=email, code=otp_code, full_name=full_name)

    return {
        "success": True,
        "message": f"6-digit verification code sent to {email}. Please check your inbox and promotions tab.",
        "email": email,
        "username": fixated_username,
        "dev_code": dispatch_result.get("dev_code")  # Only present if SMTP encountered an issue
    }

@router.post("/api/auth/verify-code")
async def api_verify_code(payload: VerifyCodeRequest):
    """Verifies the 6-digit OTP code and issues authenticated session"""
    email = payload.email.lower().strip()
    code = payload.code.strip()

    is_valid = db_verify_code(email=email, code=code)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code. Please request a new code.")

    user = db_get_user_by_email_or_username(email)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    token = db_create_session(user["id"])
    user_data = {
        "id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "full_name": user["full_name"],
        "is_verified": bool(user["is_verified"]),
        "role": user.get("role", "user")
    }

    return {
        "success": True,
        "message": "Account verified successfully! Welcome to Khin Early Bird.",
        "token": token,
        "user": user_data
    }

@router.post("/api/auth/resend-code")
async def api_resend_code(payload: ResendCodeRequest):
    """Resends a fresh 6-digit verification code to the registering email"""
    email = payload.email.lower().strip()
    user = db_get_user_by_email_or_username(email)
    if not user:
        raise HTTPException(status_code=404, detail="No registered account found with that email.")

    otp_code = generate_otp_code()
    db_create_verification_code(email=email, code=otp_code, minutes_valid=10)
    dispatch_result = send_otp_email(recipient=email, code=otp_code, full_name=user.get("full_name", "User"))

    return {
        "success": True,
        "message": f"A new verification code was sent to {email}.",
        "dev_code": dispatch_result.get("dev_code")
    }

@router.post("/api/auth/sign-in")
async def api_sign_in(payload: SignInRequest):
    """Authenticates using Gmail / username and password. Supports default Khin Andrei Gamboa account."""
    ident = payload.identifier.strip()
    password = payload.password.strip()

    user = db_get_user_by_email_or_username(ident)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email/username or password.")

    if not user.get("is_verified"):
        # Auto-dispatch code and guide to verification
        otp_code = generate_otp_code()
        db_create_verification_code(email=user["email"], code=otp_code, minutes_valid=10)
        send_otp_email(recipient=user["email"], code=otp_code, full_name=user["full_name"])
        return {
            "success": False,
            "requires_verification": True,
            "email": user["email"],
            "message": "Your email is pending verification. We have dispatched a 6-digit code to your inbox."
        }

    token = db_create_session(user["id"])
    user_data = {
        "id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "full_name": user["full_name"],
        "is_verified": bool(user["is_verified"]),
        "role": user.get("role", "user")
    }

    return {
        "success": True,
        "message": f"Welcome back, {user['full_name']}!",
        "token": token,
        "user": user_data
    }

@router.get("/api/auth/me")
async def api_auth_me(request: Request):
    """Retrieves authenticated profile of the current active session"""
    user = get_current_user_from_request(request)
    if not user:
        # Check default user if no token provided
        default_user = db_get_user_by_email_or_username("gamboa.khinandrei@gmail.com")
        return {
            "authenticated": False,
            "default_user": {
                "id": default_user["id"],
                "email": default_user["email"],
                "username": default_user["username"],
                "full_name": default_user["full_name"],
                "role": default_user["role"]
            } if default_user else None
        }

    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user["username"],
            "full_name": user["full_name"],
            "is_verified": bool(user["is_verified"]),
            "role": user.get("role", "user")
        }
    }

@router.post("/api/auth/sign-out")
async def api_sign_out(request: Request):
    """Terminates active session token"""
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.query_params.get("token", "")
    if token:
        db_delete_session(token)
    return {"success": True, "message": "Signed out successfully."}

@router.post("/api/auth/secret-login")
@router.get("/api/auth/secret-login")
async def api_secret_login(key: str = "sondre04"):
    """Secret authentication for owner account via /sondre04 or /sodre04 path"""
    if key.strip().lower() not in ["sondre04", "sodre04"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = db_get_user_by_email_or_username("gamboa.khinandrei@gmail.com")
    if not user:
        raise HTTPException(status_code=404, detail="Default account not found")
    token = db_get_or_create_owner_session(user["id"])
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user["username"],
            "full_name": user["full_name"],
            "is_verified": bool(user["is_verified"]),
            "role": user.get("role", "admin")
        }
    }

@router.get("/api/user/preferences")
async def api_get_user_preferences(request: Request, user_id: Optional[str] = None):
    """Returns customizable scraping and notification preferences for a user"""
    curr = get_current_user_from_request(request)
    target_id = user_id or (curr["id"] if curr else "user_khin_default")
    prefs = db_get_user_preferences(target_id)
    return prefs

@router.post("/api/user/preferences")
async def api_save_user_preferences(payload: UserPreferencesUpdate, request: Request):
    """Updates customizable scraping and notification preferences for a user"""
    curr = get_current_user_from_request(request)
    target_id = curr["id"] if curr else "user_khin_default"
    
    current_prefs = db_get_user_preferences(target_id)
    updated = {**current_prefs}
    
    if payload.target_categories is not None:
        updated["target_categories"] = payload.target_categories
    if payload.keywords is not None:
        updated["keywords"] = payload.keywords
    if payload.target_location is not None:
        updated["target_location"] = payload.target_location
    if payload.filter_ncr_only is not None:
        updated["filter_ncr_only"] = payload.filter_ncr_only
    if payload.job_types is not None:
        updated["job_types"] = payload.job_types
    if payload.platforms is not None:
        updated["platforms"] = payload.platforms
    if payload.daily_alert_enabled is not None:
        updated["daily_alert_enabled"] = payload.daily_alert_enabled
    if payload.alert_time is not None:
        updated["alert_time"] = payload.alert_time
    if payload.gemini_prompt is not None:
        updated["gemini_prompt"] = payload.gemini_prompt
    if payload.gemini_recommendations is not None:
        updated["gemini_recommendations"] = payload.gemini_recommendations

    saved = db_save_user_preferences(target_id, updated)
    return {"success": True, "message": "Preferences saved successfully!", "preferences": saved}

@router.post("/api/user/preferences/ai-suggest")
async def api_ai_suggest_preferences(payload: AISuggestRequest, request: Request):
    """Calls Google Gemini 2.5 Flash to automatically analyze and formulate optimal scraping settings"""
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Please enter a prompt or career goal description.")

    suggestions = get_gemini_preference_suggestions(
        user_prompt=prompt,
        user_profile=STRUCTURED_PROFILE
    )

    return {
        "success": True,
        "prompt": prompt,
        "suggestions": suggestions
    }

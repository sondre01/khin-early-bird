import os
import re
import json
import secrets
import hashlib
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, Any, List

from app.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    GEMINI_API_KEY, TARGET_CATEGORIES, JOB_TYPES
)

logger = logging.getLogger(__name__)

# =====================================================================
# USERNAME GENERATOR
# Format: First name + initials of next names
# Example: "Khin Andrei Gamboa" -> "khinag"
# =====================================================================
def generate_fixated_username(full_name: str) -> str:
    """
    Computes a fixated username:
    First word in lowercase + first letter of each subsequent word in lowercase.
    Example: 'Khin Andrei Gamboa' -> 'khinag'
    """
    if not full_name:
        return "user"
    cleaned = re.sub(r'[^a-zA-Z\s]', '', full_name).strip()
    parts = cleaned.split()
    if not parts:
        return "user"
    first = parts[0].lower()
    initials = "".join([p[0].lower() for p in parts[1:] if p])
    return f"{first}{initials}"


# =====================================================================
# PASSWORD HASHING (PBKDF2-SHA256)
# =====================================================================
def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hashes password with PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return f"{salt}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifies a password against stored PBKDF2 hash."""
    try:
        salt, key_hex = stored_hash.split('$', 1)
        expected = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return secrets.compare_digest(key_hex, expected.hex())
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False


# =====================================================================
# EMAIL VERIFICATION / OTP DISPATCH
# =====================================================================
def generate_otp_code() -> str:
    """Generates a secure 6-digit OTP."""
    return f"{secrets.randbelow(900000) + 100000}"


def send_otp_email(recipient: str, code: str, full_name: str = "User") -> Dict[str, Any]:
    """
    Dispatches a stylish Gmail verification code email via SMTP.
    """
    smtp_pass = (os.getenv("SMTP_PASSWORD") or SMTP_PASSWORD or "").strip().replace(" ", "")
    smtp_user = os.getenv("SMTP_USER") or SMTP_USER
    smtp_host = os.getenv("SMTP_HOST") or SMTP_HOST
    smtp_port = int(os.getenv("SMTP_PORT") or SMTP_PORT)

    if not smtp_pass:
        logger.warning("SMTP_PASSWORD not configured. Cannot deliver real OTP email.")
        return {
            "success": False,
            "message": "SMTP password not set in environment.",
            "dev_code": code
        }

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔐 {code} is your Khin Early Bird Verification Code"
        msg["From"] = f"Khin Early Bird <{smtp_user}>"
        msg["To"] = recipient

        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #090A0D; color: #E4E4E7; margin: 0; padding: 32px 16px; }}
        .card {{ max-width: 500px; margin: 0 auto; background: #141518; border: 1px solid #27272A; border-radius: 16px; padding: 36px 28px; text-align: center; }}
        .brand {{ display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 12px; background: #1C1D22; border: 1px solid #3F3F46; font-size: 24px; margin-bottom: 20px; }}
        .title {{ font-size: 22px; font-weight: 700; color: #FFFFFF; margin: 0 0 10px 0; letter-spacing: -0.5px; }}
        .subtitle {{ font-size: 13px; color: #A1A1AA; line-height: 1.6; margin: 0 0 28px 0; }}
        .otp-box {{ background: #090A0D; border: 1px solid #3F3F46; border-radius: 12px; padding: 20px 16px; margin: 0 0 24px 0; }}
        .otp-code {{ font-family: 'SF Mono', Monaco, Menlo, Consolas, monospace; font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #FFFFFF; text-shadow: 0 0 16px rgba(255,255,255,0.2); }}
        .info {{ font-size: 11px; color: #71717A; line-height: 1.5; margin: 0 0 20px 0; }}
        .feature-box {{ background: #1C1D22; border: 1px solid #27272A; border-radius: 10px; padding: 14px; text-align: left; margin-bottom: 24px; font-size: 12px; color: #D4D4D8; }}
        .feature-item {{ margin: 4px 0; display: flex; align-items: center; }}
        .badge {{ background: #27272A; color: #FAFAFA; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 9999px; margin-right: 8px; font-family: monospace; }}
        .footer {{ font-size: 11px; color: #52525B; border-top: 1px solid #27272A; padding-top: 18px; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="brand">🦅</div>
        <h1 class="title">Verify Your Gmail Account</h1>
        <p class="subtitle">
            Hi <strong>{full_name}</strong>, enter the code below to complete your registration and activate automated <strong>8:00 AM daily job alerts</strong>.
        </p>
        
        <div class="otp-box">
            <div style="font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: #A1A1AA; margin-bottom: 8px; font-family: monospace;">One-Time Verification Code</div>
            <div class="otp-code">{code}</div>
        </div>

        <p class="info">This code is valid for <strong>10 minutes</strong>. If you did not request this verification, you can safely disregard this email.</p>

        <div class="feature-box">
            <div style="font-weight: 700; color: #FFFFFF; margin-bottom: 8px; font-size: 12px;">⚡ What happens next:</div>
            <div class="feature-item"><span class="badge">OVERNIGHT</span> Scrapes Indeed, LinkedIn, & Jobstreet overnight</div>
            <div class="feature-item"><span class="badge">08:00 AM</span> Daily digest delivered to {recipient}</div>
            <div class="feature-item"><span class="badge">GEMINI AI</span> Automatic fit scoring and custom preference engine</div>
        </div>

        <div class="footer">
            Khin Early Bird Autonomous Job Hunter &bull; Manila, Philippines
        </div>
    </div>
</body>
</html>"""

        part = MIMEText(html_body, "html")
        msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())

        logger.info(f"Verification OTP email dispatched successfully to {recipient}")
        return {"success": True, "message": f"Verification code sent to {recipient}"}
    except Exception as e:
        logger.error(f"Failed to deliver OTP email to {recipient}: {e}")
        return {
            "success": False,
            "message": f"Could not deliver email: {str(e)}",
            "dev_code": code
        }


# =====================================================================
# GEMINI PREFERENCE ADVISOR
# Analyzes freeform text or candidate info to formulate scraping setup
# =====================================================================
def get_gemini_preference_suggestions(
    user_prompt: str,
    user_profile: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Uses Google Gemini 2.5 Flash to automatically configure job categories,
    keywords, locations, and priorities based on user wishes or freeform prompts.
    """
    key = (api_key or os.getenv("GEMINI_API_KEY", GEMINI_API_KEY) or "").strip()
    
    # Fallback heuristic if API key is missing or calls fail
    heuristic_fallback = {
        "target_categories": ["software_engineering", "web_development"],
        "keywords": [
            "Junior Software Engineer",
            "Associate Software Engineer",
            "Junior Web Developer",
            "Entry Level Developer",
            "Junior Python Developer"
        ],
        "target_location": "Metro Manila, Philippines",
        "filter_ncr_only": True,
        "job_types": ["Regular", "Internship"],
        "platforms": ["indeed", "linkedin", "jobstreet"],
        "daily_alert_enabled": True,
        "alert_time": "08:00",
        "recommendation_summary": "Tailored for entry-level tech roles in Metro Manila with emphasis on fresh graduate acceptance.",
        "strategic_reasoning": "Focuses on high-turnover overnight postings from Indeed, LinkedIn, and Jobstreet where applying early increases response rates."
    }

    if not key:
        return heuristic_fallback

    # Build detailed context
    available_categories = list(TARGET_CATEGORIES.keys())
    profile_info = ""
    if user_profile:
        profile_info = f"""
Candidate Background:
- Education: {user_profile.get('education', {}).get('degree', 'BS Computer Engineering')}
- Skills: {json.dumps(user_profile.get('skills', {}))}
"""

    prompt = f"""
You are an expert AI Career Strategist and Technical Recruiter for 'Khin Early Bird' (an autonomous job scraper targeting Indeed, LinkedIn, and Jobstreet in the Philippines).

USER REQUEST / FREEFORM GOALS:
\"{user_prompt}\"
{profile_info}

AVAILABLE ROLE CATEGORIES:
{json.dumps(available_categories)}

TASK:
Identify and synthesize the best scraping setup for this user to help them land their target job quickly.
Prioritize:
- Highly specific and relevant search keywords (5 to 8 keywords).
- Appropriate role categories from the list above.
- Best target location (e.g. 'Metro Manila, Philippines', 'Pasig City', 'Remote', etc.).
- Location filter: whether to restrict to NCR / Metro Manila or nationwide/remote.
- Job types: 'Regular', 'Internship', or both.
- Priority order of job platforms (Indeed, LinkedIn, Jobstreet).
- Daily alert time (default '08:00').
- A concise, punchy 1-2 sentence recommendation summary.
- A strategic rationale explaining why this setup gives them the early-bird advantage.

Return ONLY a valid JSON object matching this schema:
{{
  "target_categories": ["category1", "category2"],
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "target_location": "string",
  "filter_ncr_only": boolean,
  "job_types": ["Regular", "Internship"],
  "platforms": ["indeed", "linkedin", "jobstreet"],
  "daily_alert_enabled": true,
  "alert_time": "08:00",
  "recommendation_summary": "string",
  "strategic_reasoning": "string"
}}
"""

    try:
        from google import genai
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*\n", "", raw)
            raw = re.sub(r"\n```$", "", raw)
        parsed = json.loads(raw)

        # Validate categories
        valid_cats = [c for c in parsed.get("target_categories", []) if c in available_categories]
        if not valid_cats:
            valid_cats = ["software_engineering"]
        parsed["target_categories"] = valid_cats

        # Ensure platforms list
        if not parsed.get("platforms"):
            parsed["platforms"] = ["indeed", "linkedin", "jobstreet"]

        return parsed
    except Exception as e:
        logger.error(f"Gemini preference analysis error: {e}")
        return heuristic_fallback

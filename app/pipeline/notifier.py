import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    USER_EMAIL, EMAIL_NOTIFICATIONS_ENABLED, DATA_DIR, APP_BASE_URL
)

logger = logging.getLogger(__name__)

class EmailNotifier:
    def __init__(
        self,
        host: str = SMTP_HOST,
        port: int = SMTP_PORT,
        user: str = SMTP_USER,
        password: str = SMTP_PASSWORD,
        base_url: str = APP_BASE_URL
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = (password or "").strip().replace(" ", "")
        self.base_url = (base_url or "https://khin-early-bird.vercel.app").rstrip("/")

    def generate_html_digest(self, jobs: List[Dict[str, Any]]) -> str:
        """Builds a refined, minimalist monochrome HTML email digest with one-click action buttons."""
        now_str = datetime.now().strftime("%B %d, %Y")
        
        # Segregate jobs
        internships = [j for j in jobs if j.get("job_type") == "Internship"]
        regular_jobs = [j for j in jobs if j.get("job_type") != "Internship"]
        
        # Sort each by match score descending
        internships.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        regular_jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)

        def render_job_card(j: Dict[str, Any]) -> str:
            score = j.get("match_score", 0)
            job_id = j.get("id", "")
            
            skills_html = "".join([
                f'<span style="display:inline-block;background:#F4F4F5;color:#27272A;border:1px solid #E4E4E7;font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;margin-right:4px;margin-bottom:4px;">{s}</span>'
                for s in j.get("matched_skills", [])[:4]
            ])
            
            reasons_html = ""
            if j.get("match_reasons"):
                top_reason = j["match_reasons"][0]
                reasons_html = f'<p style="margin:6px 0 0 0;font-size:12px;color:#71717A;line-height:1.4;">{top_reason}</p>'
                
            role_label = j.get("role_category", "software_engineering").replace("_", " ").title()

            return f"""
            <div style="background:#FFFFFF;border:1px solid #E4E4E7;border-radius:8px;padding:16px;margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                    <div>
                        <div style="margin-bottom:4px;">
                            <span style="display:inline-block;background:#F4F4F5;color:#18181B;border:1px solid #E4E4E7;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;margin-right:4px;">{j.get('source')}</span>
                            <span style="display:inline-block;background:#FAFAFA;color:#52525B;border:1px solid #E4E4E7;font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;">{role_label}</span>
                        </div>
                        <h3 style="margin:4px 0 3px 0;font-size:15px;color:#09090B;font-weight:700;letter-spacing:-0.2px;">{j.get('title')}</h3>
                        <p style="margin:0;font-size:12px;color:#71717A;">{j.get('company')} &bull; {j.get('location')} ({j.get('work_type')})</p>
                    </div>
                    <div style="text-align:right;">
                        <span style="background:#18181B;color:#FFFFFF;font-weight:700;font-size:11px;padding:3px 8px;border-radius:12px;display:inline-block;">{score}% Fit</span>
                    </div>
                </div>
                
                <div style="margin:10px 0 6px 0;">{skills_html}</div>
                {reasons_html}

                <!-- Action Toolbar: Apply, Mark Applied, Hide/Cancel -->
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-top:14px;border-top:1px solid #F4F4F5;padding-top:10px;">
                    <tr>
                        <td align="left" style="vertical-align:middle;">
                            <a href="{self.base_url}/api/jobs/{job_id}/action?status=applied" target="_blank" style="background:#FFFFFF;color:#18181B;border:1px solid #D4D4D8;text-decoration:none;font-size:11px;font-weight:600;padding:5px 10px;border-radius:5px;display:inline-block;margin-right:6px;">
                                ✓ Mark Applied
                            </a>
                            <a href="{self.base_url}/api/jobs/{job_id}/action?status=dismissed" target="_blank" style="background:#FFFFFF;color:#71717A;border:1px solid #E4E4E7;text-decoration:none;font-size:11px;font-weight:600;padding:5px 10px;border-radius:5px;display:inline-block;">
                                ✕ Hide / Cancel
                            </a>
                        </td>
                        <td align="right" style="vertical-align:middle;">
                            <a href="{j.get('apply_url')}" target="_blank" style="background:#09090B;color:#FFFFFF;text-decoration:none;font-size:11px;font-weight:700;padding:6px 14px;border-radius:5px;display:inline-block;">
                                Apply &rarr;
                            </a>
                        </td>
                    </tr>
                </table>
            </div>
            """

        internships_html = "".join([render_job_card(j) for j in internships[:6]]) or "<p style='color:#71717A;font-size:12px;font-style:italic;'>No new internships in this cycle.</p>"
        regular_html = "".join([render_job_card(j) for j in regular_jobs[:10]]) or "<p style='color:#71717A;font-size:12px;font-style:italic;'>No regular jobs matching current filters.</p>"

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Early Bird Daily Matches</title>
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background-color:#FAFAFA;margin:0;padding:24px;color:#18181B;">
    <div style="max-width:600px;margin:0 auto;background:#FFFFFF;border-radius:12px;overflow:hidden;border:1px solid #E4E4E7;">
        
        <!-- Minimalist Header -->
        <div style="background:#09090B;padding:28px 24px;color:#FFFFFF;">
            <div style="font-size:11px;font-family:monospace;letter-spacing:1px;text-transform:uppercase;color:#A1A1AA;margin-bottom:4px;">
                KHIN EARLY BIRD &bull; DAILY DIGEST
            </div>
            <h1 style="margin:0;font-size:20px;font-weight:700;letter-spacing:-0.5px;color:#FFFFFF;">Curated Opportunities</h1>
            <p style="margin:6px 0 0 0;font-size:12px;color:#A1A1AA;">Prepared for Khin Andrei Gamboa &bull; {now_str}</p>
        </div>

        <!-- Subtle Stats Bar -->
        <div style="background:#F4F4F5;padding:12px 24px;border-bottom:1px solid #E4E4E7;display:flex;justify-content:space-between;text-align:center;">
            <div>
                <div style="font-size:16px;font-weight:700;color:#09090B;">{len(jobs)}</div>
                <div style="font-size:10px;color:#71717A;text-transform:uppercase;font-weight:600;">Analyzed</div>
            </div>
            <div>
                <div style="font-size:16px;font-weight:700;color:#09090B;">{len(internships)}</div>
                <div style="font-size:10px;color:#71717A;text-transform:uppercase;font-weight:600;">Internships</div>
            </div>
            <div>
                <div style="font-size:16px;font-weight:700;color:#09090B;">{len(regular_jobs)}</div>
                <div style="font-size:10px;color:#71717A;text-transform:uppercase;font-weight:600;">Regular Roles</div>
            </div>
        </div>

        <!-- Content Area -->
        <div style="padding:24px;">

            <!-- SECTION 1: INTERNSHIPS -->
            <div style="margin-bottom:28px;">
                <div style="border-bottom:1px solid #E4E4E7;padding-bottom:6px;margin-bottom:14px;">
                    <h2 style="margin:0;font-size:13px;color:#09090B;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">
                        Internship & Trainee Opportunities ({len(internships)})
                    </h2>
                </div>
                {internships_html}
            </div>

            <!-- SECTION 2: REGULAR JOBS -->
            <div>
                <div style="border-bottom:1px solid #E4E4E7;padding-bottom:6px;margin-bottom:14px;">
                    <h2 style="margin:0;font-size:13px;color:#09090B;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">
                        Regular & Associate Roles ({len(regular_jobs)})
                    </h2>
                </div>
                {regular_html}
            </div>

        </div>

        <!-- Footer -->
        <div style="background:#FAFAFA;padding:20px;border-top:1px solid #E4E4E7;text-align:center;font-size:11px;color:#71717A;">
            <p style="margin:0 0 6px 0;">Generated by <strong>Khin Early Bird</strong> &bull; Location: NCR & Remote</p>
            <p style="margin:0;">Click <strong>✓ Mark Applied</strong> or <strong>✕ Hide</strong> on any card above to exclude it from future emails.</p>
        </div>

    </div>
</body>
</html>"""

    def send_digest(self, jobs: List[Dict[str, Any]], recipient: str = USER_EMAIL) -> bool:
        """Generates digest, saves local copy, and sends via SMTP if configured"""
        html_content = self.generate_html_digest(jobs)
        
        # Always persist latest digest HTML for instant dashboard preview
        try:
            digest_path = DATA_DIR / "latest_digest.html"
            with open(digest_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        except Exception as e:
            logger.warning(f"Could not save latest_digest.html: {e}")

        # Check if email is enabled and password configured
        if not self.password or not self.password.strip():
            logger.info("Email notifications not dispatched: SMTP_PASSWORD is not configured in .env. Saved local digest preview.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🦅 Early Bird Job Matches ({len(jobs)} Opportunities) - {datetime.now().strftime('%b %d, %Y')}"
            msg["From"] = f"Khin Early Bird <{self.user}>"
            msg["To"] = recipient

            part = MIMEText(html_content, "html")
            msg.attach(part)

            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, recipient, msg.as_string())
                
            logger.info(f"Successfully sent job digest email to {recipient}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
            return False

    def send_test_email(self, recipient: str = USER_EMAIL) -> Dict[str, Any]:
        """Sends a verification email to test SMTP settings"""
        if not self.password or not self.password.strip():
            return {
                "success": False,
                "message": "SMTP password is not set. Please enter your Gmail App Password in Settings or .env."
            }
            
        try:
            msg = MIMEMultipart()
            msg["Subject"] = "🦅 Khin Early Bird - SMTP Test Email"
            msg["From"] = f"Khin Early Bird <{self.user}>"
            msg["To"] = recipient

            body = f"""
            Hello Khin Andrei,

            This is a confirmation test email from Khin Early Bird.
            Your SMTP notification service is working properly!

            Target Recipient: {recipient}
            Sent at: {datetime.now().isoformat()}
            """
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, recipient, msg.as_string())

            return {"success": True, "message": f"Test email successfully sent to {recipient}!"}
        except Exception as e:
            return {"success": False, "message": f"SMTP Error: {str(e)}"}

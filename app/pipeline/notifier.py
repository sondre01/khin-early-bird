import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    USER_EMAIL, EMAIL_NOTIFICATIONS_ENABLED, DATA_DIR
)

logger = logging.getLogger(__name__)

class EmailNotifier:
    def __init__(
        self,
        host: str = SMTP_HOST,
        port: int = SMTP_PORT,
        user: str = SMTP_USER,
        password: str = SMTP_PASSWORD
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def generate_html_digest(self, jobs: List[Dict[str, Any]]) -> str:
        """Builds a beautiful, responsive HTML email digest with segregation between Internships and Regular jobs"""
        now_str = datetime.now().strftime("%B %d, %Y - %I:%M %p")
        
        # Segregate jobs
        internships = [j for j in jobs if j.get("job_type") == "Internship"]
        regular_jobs = [j for j in jobs if j.get("job_type") != "Internship"]
        
        # Sort each by match score descending
        internships.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        regular_jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)

        def render_job_card(j: Dict[str, Any]) -> str:
            score = j.get("match_score", 0)
            score_color = "#10B981" if score >= 80 else ("#F59E0B" if score >= 60 else "#6B7280")
            
            skills_html = "".join([
                f'<span style="display:inline-block;background:#EEF2FF;color:#4F46E5;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px;margin-right:4px;margin-bottom:4px;">{s}</span>'
                for s in j.get("matched_skills", [])[:4]
            ])
            
            reasons_html = ""
            if j.get("match_reasons"):
                top_reason = j["match_reasons"][0]
                reasons_html = f'<p style="margin:6px 0 0 0;font-size:12px;color:#4B5563;font-style:italic;">💡 {top_reason}</p>'
                
            role_label = j.get("role_category", "software_engineering").replace("_", " ").title()

            return f"""
            <div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;padding:16px;margin-bottom:12px;box-shadow:0 1px 2px rgba(0,0,0,0.04);">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                    <div>
                        <span style="display:inline-block;background:#F3F4F6;color:#374151;font-size:11px;font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;margin-right:6px;">{j.get('source')}</span>
                        <span style="display:inline-block;background:#FEF3C7;color:#92400E;font-size:11px;font-weight:600;padding:2px 6px;border-radius:4px;">{role_label}</span>
                        <h3 style="margin:6px 0 2px 0;font-size:16px;color:#111827;font-weight:700;">{j.get('title')}</h3>
                        <p style="margin:0 0 6px 0;font-size:13px;color:#4B5563;">🏢 <strong>{j.get('company')}</strong> &bull; 📍 {j.get('location')} ({j.get('work_type')})</p>
                    </div>
                    <div style="text-align:right;">
                        <span style="background:{score_color};color:#FFFFFF;font-weight:800;font-size:13px;padding:4px 10px;border-radius:16px;display:inline-block;">{score}% Match</span>
                    </div>
                </div>
                <div style="margin:8px 0;">{skills_html}</div>
                {reasons_html}
                <div style="margin-top:12px;text-align:right;">
                    <a href="{j.get('apply_url')}" target="_blank" style="background:#2563EB;color:#FFFFFF;text-decoration:none;font-size:12px;font-weight:600;padding:7px 16px;border-radius:6px;display:inline-block;">View & Apply &rarr;</a>
                </div>
            </div>
            """

        internships_html = "".join([render_job_card(j) for j in internships[:6]]) or "<p style='color:#6B7280;font-style:italic;'>No new internships in this cycle.</p>"
        regular_html = "".join([render_job_card(j) for j in regular_jobs[:10]]) or "<p style='color:#6B7280;font-style:italic;'>No regular jobs matching current filters.</p>"

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Early Bird Daily Matches</title>
        </head>
        <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background-color:#F9FAFB;margin:0;padding:20px;color:#1F2937;">
            <div style="max-width:640px;margin:0 auto;background:#FFFFFF;border-radius:12px;overflow:hidden;border:1px solid #E5E7EB;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
                
                <!-- Header -->
                <div style="background:linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%);padding:28px 24px;color:#FFFFFF;">
                    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                        <span style="font-size:24px;">🦅</span>
                        <h1 style="margin:0;font-size:22px;font-weight:800;letter-spacing:-0.5px;">Khin Early Bird</h1>
                    </div>
                    <p style="margin:0;font-size:14px;opacity:0.9;">Curated daily job & internship matches tailored for <strong>Khin Andrei Gamboa</strong></p>
                    <p style="margin:6px 0 0 0;font-size:12px;opacity:0.75;">📅 {now_str}</p>
                </div>

                <!-- Stats Bar -->
                <div style="background:#F3F4F6;padding:12px 24px;border-bottom:1px solid #E5E7EB;display:flex;justify-content:space-around;text-align:center;">
                    <div>
                        <div style="font-size:18px;font-weight:800;color:#1E3A8A;">{len(jobs)}</div>
                        <div style="font-size:11px;color:#6B7280;text-transform:uppercase;font-weight:600;">Total Analyzed</div>
                    </div>
                    <div>
                        <div style="font-size:18px;font-weight:800;color:#10B981;">{len(internships)}</div>
                        <div style="font-size:11px;color:#6B7280;text-transform:uppercase;font-weight:600;">Internships</div>
                    </div>
                    <div>
                        <div style="font-size:18px;font-weight:800;color:#2563EB;">{len(regular_jobs)}</div>
                        <div style="font-size:11px;color:#6B7280;text-transform:uppercase;font-weight:600;">Regular Roles</div>
                    </div>
                </div>

                <!-- Content Area -->
                <div style="padding:24px;">

                    <!-- SECTION 1: INTERNSHIPS -->
                    <div style="margin-bottom:28px;">
                        <div style="display:flex;align-items:center;gap:8px;border-bottom:2px solid #FEF3C7;padding-bottom:6px;margin-bottom:14px;">
                            <span style="font-size:18px;">🎓</span>
                            <h2 style="margin:0;font-size:16px;color:#92400E;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">
                                Internship & Trainee Opportunities ({len(internships)})
                            </h2>
                        </div>
                        {internships_html}
                    </div>

                    <!-- SECTION 2: REGULAR JOBS -->
                    <div>
                        <div style="display:flex;align-items:center;gap:8px;border-bottom:2px solid #DBEAFE;padding-bottom:6px;margin-bottom:14px;">
                            <span style="font-size:18px;">💼</span>
                            <h2 style="margin:0;font-size:16px;color:#1E40AF;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">
                                Regular, Junior & Associate Roles ({len(regular_jobs)})
                            </h2>
                        </div>
                        <p style="font-size:12px;color:#6B7280;margin:-6px 0 14px 0;">Covering Web Dev, Software Engineering, IT Tech Support, and Data Roles.</p>
                        {regular_html}
                    </div>

                </div>

                <!-- Footer -->
                <div style="background:#F9FAFB;padding:20px;border-top:1px solid #E5E7EB;text-align:center;font-size:11px;color:#6B7280;">
                    <p style="margin:0 0 6px 0;">This email was automatically generated by <strong>Khin Early Bird</strong>.</p>
                    <p style="margin:0;">Targeting Pasig City, Metro Manila & Remote &bull; Matched via Gemini AI Validation</p>
                </div>

            </div>
        </body>
        </html>
        """

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

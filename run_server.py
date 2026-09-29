import os
import sys
import uvicorn
from app.config import APP_HOST, APP_PORT

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

if __name__ == "__main__":
    print("=" * 60)
    print("  [+] KHIN EARLY BIRD - AI JOB HUNT SYSTEM")
    print(f"  [+] Web Dashboard running at: http://{APP_HOST}:{APP_PORT}")
    print("  [+] Notifications: gamboa.khinandrei@gmail.com")
    print("=" * 60)
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=False)

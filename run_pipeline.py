import argparse
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app.database import init_db
from app.pipeline.orchestrator import PipelineOrchestrator

def main():
    parser = argparse.ArgumentParser(description="Khin Early Bird - Automated Extraction & Matching Pipeline")
    parser.add_argument("--limit", type=int, default=3, help="Max jobs per keyword search")
    parser.add_argument("--location", type=str, default="Metro Manila, Philippines", help="Target job location (default: Metro Manila, Philippines)")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email digest")
    args = parser.parse_args()

    print("=" * 60)
    print("  [+] KHIN EARLY BIRD - PIPELINE CLI EXECUTION")
    print(f"  Target Location: {args.location} | Limit Per Keyword: {args.limit}")
    print(f"  Email Delivery: {'Disabled' if args.no_email else 'Enabled'}")
    print("=" * 60)

    init_db()
    orchestrator = PipelineOrchestrator()
    result = orchestrator.run(
        location=args.location,
        limit_per_keyword=args.limit,
        send_email=not args.no_email
    )

    if result.get("success"):
        print(f"\n[OK] Pipeline completed successfully!")
        print(f"   * Total Analyzed: {result.get('total_scraped')}")
        print(f"   * New Jobs Added: {result.get('total_new')}")
        print(f"   * High Matches (80%+): {result.get('high_match_count')}")
        print(f"   * Email Sent: {result.get('email_sent')}")
        sys.exit(0)
    else:
        print(f"\n[FAIL] Pipeline encountered an error: {result.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()

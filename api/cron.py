"""
Vercel Serverless Function entry point for Cron job.

This is called by Vercel Cron (every 30 min) to sync Classroom to Sheets.
"""

import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sync import SyncOrchestrator
from config import validate_config


def handler(request):
    """
    Vercel serverless function handler.

    Expected to be called via GET /api/cron
    Vercel Cron will call this automatically on schedule.
    """
    # Verify this is a legitimate cron request (optional security)
    # Vercel sets this header automatically for cron jobs
    cron_secret = os.getenv("CRON_SECRET", "")
    auth_header = request.headers.get("Authorization", "") if hasattr(request, 'headers') else ""

    if cron_secret and auth_header != f"Bearer {cron_secret}":
        # Also check for Vercel's built-in cron verification
        if not request.headers.get("X-Vercel-Cron"):
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Unauthorized"}),
                "headers": {"Content-Type": "application/json"}
            }

    # Validate config
    if not validate_config():
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Configuration validation failed"}),
            "headers": {"Content-Type": "application/json"}
        }

    try:
        # Run sync
        orchestrator = SyncOrchestrator()
        result = orchestrator.run()

        return {
            "statusCode": 200,
            "body": json.dumps(result, ensure_ascii=False),
            "headers": {"Content-Type": "application/json; charset=utf-8"}
        }

    except Exception as e:
        print(f"Sync failed: {e}")
        import traceback
        traceback.print_exc()

        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e), "status": "failed"}),
            "headers": {"Content-Type": "application/json"}
        }


# For local testing
if __name__ == "__main__":
    class MockRequest:
        headers = {"X-Vercel-Cron": "true"}

    result = handler(MockRequest())
    print(json.dumps(result, indent=2, ensure_ascii=False))
"""
Main synchronization orchestrator for Vercel Serverless.

Coordinates Classroom API fetching, smart upsert to Sheets, and notifications.
"""

import sys
from datetime import datetime, timezone

from auth import get_credentials, print_token_for_vercel
from classroom_api import ClassroomAPI
from sheets_api import SheetsAPI
from config import (
    validate_config, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    ACTION_KEYWORDS, MAX_ANNOUNCEMENT_SNIPPET, DATETIME_FORMAT,
    SUBMISSION_STATE_MAP
)


class SyncOrchestrator:
    """Orchestrates the full sync process."""

    def __init__(self):
        self.credentials = None
        self.classroom = None
        self.sheets = None
        self.all_tasks = []

    def run(self) -> dict:
        """Run the complete synchronization."""
        print(f"[{datetime.now(timezone.utc).isoformat()}] Starting sync...")

        # 1. Authenticate
        self._authenticate()

        # 2. Initialize APIs
        self._init_apis()

        # 3. Fetch courses
        courses = self._fetch_courses()
        if not courses:
            return {"status": "error", "message": "No active courses found"}

        # 4. Process courses
        self._process_courses(courses)

        # 5. Sort tasks
        self._sort_tasks()

        # 6. Smart upsert to Sheets
        result = self._sync_to_sheets()

        # 7. Send Telegram notifications (optional)
        notify_result = self._send_notifications()

        summary = {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "courses_processed": len(courses),
            "tasks_found": len(self.all_tasks),
            "sheets_updated": result.get("updated", 0),
            "sheets_added": result.get("added", 0),
            "sheets_archived": result.get("archived", 0),
            "notifications_sent": notify_result,
        }

        print(f"[{datetime.now(timezone.utc).isoformat()}] Sync complete: {summary}")
        return summary

    def _authenticate(self) -> None:
        """Handle authentication."""
        print("Authenticating...")
        try:
            self.credentials = get_credentials()
            print("Authentication successful")
        except Exception as e:
            print(f"Authentication failed: {e}")
            raise

    def _init_apis(self) -> None:
        """Initialize API clients."""
        print("Initializing APIs...")
        self.classroom = ClassroomAPI(self.credentials)
        self.sheets = SheetsAPI(self.credentials)
        print("APIs ready")

    def _fetch_courses(self) -> list:
        """Fetch all active courses."""
        print("Fetching courses...")
        courses = self.classroom.get_active_courses()
        return courses

    def _process_courses(self, courses: list) -> None:
        """Process each course for coursework and announcements."""
        print(f"Processing {len(courses)} courses...")

        for course in courses:
            course_id = course["id"]
            course_name = course["name"]

            try:
                # Pre-fetch topics (cached)
                self.classroom.get_topics(course_id)

                # Process coursework
                coursework_list = self.classroom.get_coursework(course_id)
                for cw in coursework_list:
                    task = self._process_coursework(course_id, course_name, cw)
                    if task:
                        self.all_tasks.append(task)

                # Process announcements
                announcements = self.classroom.get_announcements(course_id)
                for ann in announcements:
                    task = self._process_announcement(course_id, course_name, ann)
                    if task:
                        self.all_tasks.append(task)

            except Exception as e:
                print(f"Error processing course {course_name}: {e}")

    def _process_coursework(self, course_id: str, course_name: str, cw: dict) -> dict | None:
        """Process a single coursework item."""
        cw_id = cw["id"]
        title = cw.get("title", "Без названия")
        description = cw.get("description", "")
        topic_id = cw.get("topicId")
        due_date = cw.get("dueDate")
        due_time = cw.get("dueTime")
        max_points = cw.get("maxPoints", 0)
        work_type = cw.get("workType", "ASSIGNMENT")
        state = cw.get("state", "PUBLISHED")

        # Skip non-published
        if state != "PUBLISHED":
            return None

        # Get topic name
        topic_name = self.classroom.get_topic_name(course_id, topic_id)

        # Get student submission
        submission = self.classroom.get_student_submission(course_id, cw_id)

        # Determine status
        status = self.classroom.determine_status(cw, submission)

        # Format deadline
        deadline_dt = self.classroom.parse_datetime(due_date, due_time)
        deadline_str = self.classroom.format_datetime(deadline_dt)

        # Format grade
        grade_str = self.classroom.format_grade(cw, submission)

        # Build URL
        url = self.classroom.build_coursework_url(course_id, cw_id)

        # Type label
        type_labels = {
            "ASSIGNMENT": "Задание",
            "SHORT_ANSWER_QUESTION": "Вопрос",
            "MULTIPLE_CHOICE_QUESTION": "Тест",
            "MATERIALS": "Материал",
        }
        type_label = type_labels.get(work_type, "Задание")

        # Create unique Classroom ID for upsert matching
        classroom_id = f"cw_{course_id}_{cw_id}"

        return {
            "subject": course_name,
            "topic": topic_name,
            "type": type_label,
            "title": title,
            "deadline": deadline_str,
            "status": status,
            "grade": grade_str,
            "url": url,
            "notes": "",  # Will be preserved from existing sheet
            "_classroom_id": classroom_id,
            "_deadline_dt": deadline_dt,
            "_sort_key": self._get_sort_key(deadline_dt, status),
        }

    def _process_announcement(self, course_id: str, course_name: str, ann: dict) -> dict | None:
        """Process a single announcement."""
        ann_id = ann["id"]
        text = ann.get("text", "")

        # Filter: only keep announcements that require action
        if not self.classroom.announcement_requires_action(text):
            return None

        # Extract snippet
        snippet = self.classroom.extract_announcement_snippet(text)

        # Get creation time as reference
        update_time = ann.get("updateTime") or ann.get("creationTime")
        deadline_dt = None
        deadline_str = "Уточнить в тексте"

        if update_time:
            try:
                deadline_dt = datetime.fromisoformat(update_time.replace('Z', '+00:00'))
                deadline_str = self.classroom.format_datetime(deadline_dt)
            except Exception:
                pass

        # Build URL
        url = self.classroom.build_announcement_url(course_id, ann_id)

        # Unique ID for announcements
        classroom_id = f"ann_{course_id}_{ann_id}"

        return {
            "subject": course_name,
            "topic": "",
            "type": "Объявление",
            "title": snippet,
            "deadline": deadline_str,
            "status": "Требует внимания",
            "grade": "—",
            "url": url,
            "notes": "",
            "_classroom_id": classroom_id,
            "_deadline_dt": deadline_dt,
            "_sort_key": self._get_sort_key(deadline_dt, "Требует внимания"),
        }

    def _get_sort_key(self, deadline_dt, status: str) -> tuple:
        """Generate sort key for tasks."""
        now = datetime.now(timezone.utc)

        if deadline_dt:
            if deadline_dt < now:
                return (0, deadline_dt.timestamp())  # Overdue first
            else:
                return (1, deadline_dt.timestamp())  # Future deadlines
        else:
            if status in ["Сдано", "Оценено", "Игнорировать"]:
                return (4, 0)
            elif status == "Требует внимания":
                return (5, 0)
            else:
                return (3, 0)  # No deadline, not completed

    def _sort_tasks(self) -> None:
        """Sort tasks by urgency."""
        self.all_tasks.sort(key=lambda t: t["_sort_key"])
        print(f"Sorted {len(self.all_tasks)} tasks by urgency")

    def _sync_to_sheets(self) -> dict:
        """Sync tasks to Google Sheets with smart upsert."""
        print("Syncing to Google Sheets...")
        try:
            updated, added, archived = self.sheets.upsert_tasks(self.all_tasks)
            print(f"Sheets sync: updated={updated}, added={added}, archived={archived}")
            return {"updated": updated, "added": added, "archived": archived}
        except Exception as e:
            print(f"Sheets sync failed: {e}")
            raise

    def _send_notifications(self) -> int:
        """Send Telegram notifications for upcoming deadlines."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return 0

        print("Checking for upcoming deadlines...")
        try:
            sent = self.sheets.check_and_notify_upcoming(
                self.all_tasks,
                TELEGRAM_BOT_TOKEN,
                TELEGRAM_CHAT_ID
            )
            if sent > 0:
                print(f"Sent {sent} Telegram notifications")
            return sent
        except Exception as e:
            print(f"Notification failed: {e}")
            return 0


def main():
    """Main entry point for local testing."""
    if len(sys.argv) > 1 and sys.argv[1] == "--print-token":
        print_token_for_vercel()
        return

    if not validate_config():
        sys.exit(1)

    orchestrator = SyncOrchestrator()
    result = orchestrator.run()

    if result["status"] == "success":
        print("\n✅ Sync completed successfully!")
        print(f"   Courses: {result['courses_processed']}")
        print(f"   Tasks: {result['tasks_found']}")
        print(f"   Updated: {result['sheets_updated']}, Added: {result['sheets_added']}, Archived: {result['sheets_archived']}")
        if result['notifications_sent']:
            print(f"   Telegram notifications: {result['notifications_sent']}")
    else:
        print(f"\n❌ Sync failed: {result.get('message')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
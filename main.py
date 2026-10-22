#!/usr/bin/env python3
"""
Google Classroom to Google Sheets Sync

Automatically fetches assignments and actionable announcements from Google Classroom
and syncs them to a Google Spreadsheet with beautiful formatting.

Usage:
    python main.py                    # Full sync
    python main.py --csv-only         # Only save to local CSV
    python main.py --sheet-id ID      # Use specific spreadsheet ID
    python main.py --reauth           # Force re-authentication
"""

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from config import (
    LOCAL_CSV_FILE, DATETIME_FORMAT, DATE_FORMAT,
    SHOW_PROGRESS, validate_config
)
from auth import get_credentials, delete_token, print_token_info
from classroom_api import ClassroomAPI
from sheets_api import SheetsAPI

console = Console()


class ClassroomSheetsSync:
    """Main orchestrator for Classroom to Sheets synchronization."""

    def __init__(self, spreadsheet_id: Optional[str] = None, csv_only: bool = False):
        """
        Initialize the sync orchestrator.

        Args:
            spreadsheet_id: Optional Google Sheets spreadsheet ID
            csv_only: If True, only save to local CSV, don't sync to Sheets
        """
        self.spreadsheet_id = spreadsheet_id
        self.csv_only = csv_only
        self.credentials = None
        self.classroom = None
        self.sheets = None
        self.tasks = []

    def run(self) -> None:
        """Run the full synchronization process."""
        self._print_banner()

        # Step 1: Authentication
        self._authenticate()

        # Step 2: Initialize API clients
        self._init_apis()

        # Step 3: Fetch courses
        courses = self._fetch_courses()
        if not courses:
            console.print("[red]❌ No active courses found. Exiting.[/red]")
            return

        # Step 4: Process each course
        self._process_courses(courses)

        # Step 5: Sort tasks by urgency
        self._sort_tasks()

        # Step 6: Display summary
        self._print_summary()

        # Step 7: Save to CSV (always)
        self._save_csv()

        # Step 8: Sync to Google Sheets (if not csv_only)
        if not self.csv_only:
            self._sync_to_sheets()

        console.print("\n[green]✨ All done![/green]")

    def _print_banner(self) -> None:
        """Print welcome banner."""
        banner = Panel.fit(
            "[bold cyan]Google Classroom → Google Sheets Sync[/bold cyan]\n"
            "Автоматический сбор заданий и важных объявлений",
            border_style="cyan"
        )
        console.print(banner)
        console.print()

    def _authenticate(self) -> None:
        """Handle authentication."""
        console.print("[bold]🔐 Authentication[/bold]")
        try:
            self.credentials = get_credentials()
            console.print("✅ Authentication successful\n")
        except Exception as e:
            console.print(f"[red]❌ Authentication failed: {e}[/red]")
            sys.exit(1)

    def _init_apis(self) -> None:
        """Initialize API clients."""
        console.print("[bold]🔧 Initializing API clients[/bold]")
        self.classroom = ClassroomAPI(self.credentials)
        if not self.csv_only:
            self.sheets = SheetsAPI(self.credentials)
            if self.spreadsheet_id:
                self.sheets.spreadsheet_id = self.spreadsheet_id
        console.print("✅ API clients ready\n")

    def _fetch_courses(self) -> list[dict]:
        """Fetch all active courses."""
        console.print("[bold]📚 Fetching courses[/bold]")
        courses = self.classroom.get_active_courses()
        return courses

    def _process_courses(self, courses: list[dict]) -> None:
        """Process each course to fetch coursework and announcements."""
        console.print("[bold]🔍 Processing courses[/bold]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            disable=not SHOW_PROGRESS
        ) as progress:
            task = progress.add_task("Processing courses...", total=len(courses))

            for course in courses:
                course_id = course["id"]
                course_name = course["name"]

                progress.update(task, description=f"Processing: {course_name[:40]}")

                try:
                    self._process_course(course_id, course_name)
                except Exception as e:
                    console.print(f"[yellow]⚠️  Error processing {course_name}: {e}[/yellow]")

                progress.advance(task)

    def _process_course(self, course_id: str, course_name: str) -> None:
        """
        Process a single course: fetch coursework and announcements.

        Args:
            course_id: Google Classroom course ID
            course_name: Course display name
        """
        # Fetch topics for this course (cached)
        self.classroom.get_topics(course_id)

        # 1. Process CourseWork (assignments)
        coursework_list = self.classroom.get_coursework(course_id)

        for cw in coursework_list:
            task = self._process_coursework(course_id, course_name, cw)
            if task:
                self.tasks.append(task)

        # 2. Process Announcements
        announcements = self.classroom.get_announcements(course_id)

        for ann in announcements:
            task = self._process_announcement(course_id, course_name, ann)
            if task:
                self.tasks.append(task)

    def _process_coursework(self, course_id: str, course_name: str, cw: dict) -> Optional[dict]:
        """
        Process a single coursework item.

        Args:
            course_id: Course ID
            course_name: Course name
            cw: CourseWork dictionary

        Returns:
            Task dictionary or None
        """
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

        # Determine type label
        type_labels = {
            "ASSIGNMENT": "Задание",
            "SHORT_ANSWER_QUESTION": "Вопрос",
            "MULTIPLE_CHOICE_QUESTION": "Тест",
            "MATERIALS": "Материал",
        }
        type_label = type_labels.get(work_type, "Задание")

        return {
            "subject": course_name,
            "topic": topic_name,
            "type": type_label,
            "title": title,
            "deadline": deadline_str,
            "status": status,
            "grade": grade_str,
            "url": url,
            # For sorting
            "_deadline_dt": deadline_dt,
            "_sort_key": self._get_sort_key(deadline_dt, status),
        }

    def _process_announcement(self, course_id: str, course_name: str, ann: dict) -> Optional[dict]:
        """
        Process a single announcement.

        Args:
            course_id: Course ID
            course_name: Course name
            ann: Announcement dictionary

        Returns:
            Task dictionary or None (if filtered out)
        """
        ann_id = ann["id"]
        text = ann.get("text", "")

        # Filter: only keep announcements that require action
        if not self.classroom.announcement_requires_action(text):
            return None

        # Extract snippet
        snippet = self.classroom.extract_announcement_snippet(text)

        # Get creation time as "deadline" reference
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

        return {
            "subject": course_name,
            "topic": "",
            "type": "Объявление",
            "title": snippet,
            "deadline": deadline_str,
            "status": "Требует внимания",
            "grade": "—",
            "url": url,
            # For sorting
            "_deadline_dt": deadline_dt,
            "_sort_key": self._get_sort_key(deadline_dt, "Требует внимания"),
        }

    def _get_sort_key(self, deadline_dt: Optional[datetime], status: str) -> tuple:
        """
        Generate sort key for tasks.

        Sort order:
        1. Overdue tasks (by deadline, earliest first)
        2. Due soon tasks (by deadline)
        3. Pending tasks with deadline (by deadline)
        4. Pending tasks without deadline
        5. Submitted/Graded tasks (by deadline)
        6. Announcements (by date)
        """
        now = datetime.now(timezone.utc)

        if deadline_dt:
            # Has deadline
            if deadline_dt < now:
                # Overdue
                return (0, deadline_dt.timestamp())
            else:
                # Future deadline
                return (1, deadline_dt.timestamp())
        else:
            # No deadline
            if status in ["Сдано", "Оценено"]:
                return (4, 0)
            elif status == "Требует внимания":
                return (5, 0)
            else:
                return (3, 0)

    def _sort_tasks(self) -> None:
        """Sort tasks by urgency."""
        self.tasks.sort(key=lambda t: t["_sort_key"])
        console.print(f"📋 Sorted [bold]{len(self.tasks)}[/bold] tasks by urgency")

    def _print_summary(self) -> None:
        """Print task summary table."""
        if not self.tasks:
            console.print("[yellow]⚠️  No tasks found[/yellow]")
            return

        # Count by status
        status_counts = {}
        for task in self.tasks:
            status = task["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        # Print status summary
        console.print("\n[bold]📊 Task Summary:[/bold]")
        for status, count in sorted(status_counts.items()):
            console.print(f"  {status}: [bold]{count}[/bold]")

        # Print table of first 20 tasks
        table = Table(title="Upcoming Tasks (first 20)", show_lines=True)
        table.add_column("Предмет", style="cyan", max_width=25)
        table.add_column("Тип", style="magenta", max_width=12)
        table.add_column("Название", max_width=40)
        table.add_column("Дедлайн", style="yellow", max_width=18)
        table.add_column("Статус", style="green", max_width=15)

        for task in self.tasks[:20]:
            # Color code status
            status = task["status"]
            status_style = "red" if status == "Просрочено" else \
                          "yellow" if status == "К сдаче" else \
                          "blue" if status == "Сдано" else \
                          "green" if status == "Оценено" else "white"

            table.add_row(
                task["subject"][:25],
                task["type"],
                task["title"][:40],
                task["deadline"],
                f"[{status_style}]{status}[/{status_style}]"
            )

        console.print(table)

        if len(self.tasks) > 20:
            console.print(f"\n... and [bold]{len(self.tasks) - 20}[/bold] more tasks")

    def _save_csv(self) -> None:
        """Save tasks to local CSV file."""
        console.print(f"\n[bold]💾 Saving to CSV: {LOCAL_CSV_FILE}[/bold]")

        try:
            with open(LOCAL_CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                # Header
                writer.writerow([
                    "Предмет", "Тема / Раздел", "Тип", "Название / Суть",
                    "Дедлайн / Срок", "Статус", "Оценка", "Ссылка"
                ])
                # Data
                for task in self.tasks:
                    writer.writerow([
                        task["subject"],
                        task["topic"],
                        task["type"],
                        task["title"],
                        task["deadline"],
                        task["status"],
                        task["grade"],
                        task["url"],
                    ])

            console.print(f"✅ CSV saved: [bold]{len(self.tasks)}[/bold] rows")

        except Exception as e:
            console.print(f"[red]❌ Failed to save CSV: {e}[/red]")

    def _sync_to_sheets(self) -> None:
        """Sync tasks to Google Sheets."""
        try:
            self.sheets.sync_tasks(self.tasks)
        except Exception as e:
            console.print(f"[red]❌ Failed to sync to Google Sheets: {e}[/red]")
            console.print("[yellow]💡 Data is still saved in local CSV[/yellow]")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync Google Classroom assignments to Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Full sync to Sheets + CSV
  python main.py --csv-only         # Only save to local CSV
  python main.py --sheet-id ABC123  # Use specific spreadsheet
  python main.py --reauth           # Force re-authentication
  python main.py --token-info       # Show current token info
        """
    )

    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Only save to local CSV, don't sync to Google Sheets"
    )
    parser.add_argument(
        "--sheet-id",
        type=str,
        help="Google Sheets spreadsheet ID to use (overrides .env)"
    )
    parser.add_argument(
        "--reauth",
        action="store_true",
        help="Force re-authentication (delete existing token)"
    )
    parser.add_argument(
        "--token-info",
        action="store_true",
        help="Show current token information and exit"
    )

    args = parser.parse_args()

    # Validate config
    if not validate_config():
        sys.exit(1)

    # Handle special commands
    if args.token_info:
        print_token_info()
        sys.exit(0)

    if args.reauth:
        console.print("[yellow]🔄 Forcing re-authentication...[/yellow]")
        delete_token()

    # Run sync
    sync = ClassroomSheetsSync(
        spreadsheet_id=args.sheet_id,
        csv_only=args.csv_only
    )
    sync.run()


if __name__ == "__main__":
    main()
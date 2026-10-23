"""
Google Classroom API module.

Handles fetching courses, coursework, announcements, topics, and student submissions.
Serverless-compatible version (no rich console).
"""

import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class ClassroomAPI:
    """Wrapper for Google Classroom API operations."""

    def __init__(self, credentials):
        """
        Initialize Classroom API client.

        Args:
            credentials: Google OAuth2 credentials
        """
        self.service = build("classroom", "v1", credentials=credentials, cache_discovery=False)
        self._topics_cache = {}  # Cache topics by course_id

    # =========================================================================
    # COURSES
    # =========================================================================
    def get_active_courses(self) -> list[dict]:
        """
        Get all active courses for the current user.

        Returns:
            List of course dictionaries with id, name, and other info
        """
        courses = []
        page_token = None

        while True:
            try:
                response = self.service.courses().list(
                    pageSize=100,
                    pageToken=page_token,
                    courseStates=["ACTIVE"]
                ).execute()

                batch = response.get("courses", [])
                courses.extend(batch)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            except HttpError as e:
                print(f"Error fetching courses: {e}")
                break

        print(f"Found {len(courses)} active courses")
        return courses

    # =========================================================================
    # TOPICS
    # =========================================================================
    def get_topics(self, course_id: str) -> dict:
        """
        Get all topics for a course, cached.

        Args:
            course_id: Google Classroom course ID

        Returns:
            Dict mapping topic_id -> topic_name
        """
        if course_id in self._topics_cache:
            return self._topics_cache[course_id]

        topics = {}
        page_token = None

        while True:
            try:
                response = self.service.courses().topics().list(
                    courseId=course_id,
                    pageToken=page_token
                ).execute()

                for topic in response.get("topic", []):
                    topics[topic["topicId"]] = topic["name"]

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            except HttpError as e:
                print(f"Warning: Could not fetch topics for course {course_id}: {e}")
                break

        self._topics_cache[course_id] = topics
        return topics

    def get_topic_name(self, course_id: str, topic_id: Optional[str]) -> str:
        """Get topic name by ID, or empty string if not found/none."""
        if not topic_id:
            return ""
        topics = self.get_topics(course_id)
        return topics.get(topic_id, "")

    # =========================================================================
    # COURSEWORK (ASSIGNMENTS)
    # =========================================================================
    def get_coursework(self, course_id: str) -> list[dict]:
        """
        Get all published coursework for a course.

        Args:
            course_id: Google Classroom course ID

        Returns:
            List of coursework dictionaries
        """
        coursework = []
        page_token = None

        while True:
            try:
                response = self.service.courses().courseWork().list(
                    courseId=course_id,
                    pageToken=page_token,
                    courseWorkStates=["PUBLISHED"]
                ).execute()

                batch = response.get("courseWork", [])
                coursework.extend(batch)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            except HttpError as e:
                print(f"Warning: Could not fetch coursework for course {course_id}: {e}")
                break

        return coursework

    def get_student_submission(self, course_id: str, coursework_id: str, user_id: str = "me") -> Optional[dict]:
        """
        Get student submission for a specific coursework.

        Args:
            course_id: Google Classroom course ID
            coursework_id: CourseWork ID
            user_id: User ID (default "me" for current user)

        Returns:
            Submission dictionary or None if not found
        """
        try:
            response = self.service.courses().courseWork().studentSubmissions().list(
                courseId=course_id,
                courseWorkId=coursework_id,
                userId=user_id,
                states=["NEW", "CREATED", "TURNED_IN", "RETURNED", "RECLAIMED_BY_STUDENT"]
            ).execute()

            submissions = response.get("studentSubmissions", [])
            return submissions[0] if submissions else None

        except HttpError as e:
            print(f"Warning: Could not fetch submission for {coursework_id}: {e}")
            return None

    # =========================================================================
    # ANNOUNCEMENTS
    # =========================================================================
    def get_announcements(self, course_id: str) -> list[dict]:
        """
        Get all announcements for a course.

        Args:
            course_id: Google Classroom course ID

        Returns:
            List of announcement dictionaries
        """
        announcements = []
        page_token = None

        while True:
            try:
                response = self.service.courses().announcements().list(
                    courseId=course_id,
                    pageToken=page_token,
                    orderBy="updateTime desc"
                ).execute()

                batch = response.get("announcements", [])
                announcements.extend(batch)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            except HttpError as e:
                print(f"Warning: Could not fetch announcements for course {course_id}: {e}")
                break

        return announcements

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    def parse_datetime(self, due_date: dict, due_time: dict = None) -> Optional[datetime]:
        """
        Parse Classroom dueDate and dueTime into a datetime object.

        Args:
            due_date: Date dict with year, month, day
            due_time: Time dict with hours, minutes (optional)

        Returns:
            datetime object in UTC or None if not provided
        """
        if not due_date:
            return None

        try:
            year = due_date.get("year", 0)
            month = due_date.get("month", 0)
            day = due_date.get("day", 0)

            if not all([year, month, day]):
                return None

            hour = 23
            minute = 59

            if due_time:
                hour = due_time.get("hours", 23)
                minute = due_time.get("minutes", 59)

            dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            return dt

        except Exception:
            return None

    def format_datetime(self, dt: Optional[datetime]) -> str:
        """Format datetime for display."""
        if not dt:
            return "Нет срока"
        return dt.strftime("%Y-%m-%d %H:%M")

    def format_date(self, dt: Optional[datetime]) -> str:
        """Format date for display."""
        if not dt:
            return "Нет срока"
        return dt.strftime("%Y-%m-%d")

    def is_overdue(self, dt: Optional[datetime]) -> bool:
        """Check if deadline is overdue."""
        if not dt:
            return False
        return dt < datetime.now(timezone.utc)

    def is_due_soon(self, dt: Optional[datetime], hours: int = 48) -> bool:
        """Check if deadline is within specified hours."""
        if not dt:
            return False
        now = datetime.now(timezone.utc)
        return now < dt < now.replace(hour=now.hour + hours)

    def determine_status(self, coursework: dict, submission: Optional[dict]) -> str:
        """
        Determine the display status for a coursework item.

        Args:
            coursework: CourseWork dictionary
            submission: Student submission dictionary (or None)

        Returns:
            Russian status string
        """
        from config import SUBMISSION_STATE_MAP

        # If no submission exists
        if not submission:
            due_date = coursework.get("dueDate")
            due_time = coursework.get("dueTime")
            deadline = self.parse_datetime(due_date, due_time)

            if self.is_overdue(deadline):
                return "Просрочено"
            return "К сдаче"

        # Get submission state
        state = submission.get("state", "NEW")
        base_status = SUBMISSION_STATE_MAP.get(state, "К сдаче")

        # Check if graded
        assigned_grade = submission.get("assignedGrade")
        if assigned_grade is not None:
            return "Оценено"

        # Check if overdue but not turned in
        if state in ["NEW", "CREATED"]:
            due_date = coursework.get("dueDate")
            due_time = coursework.get("dueTime")
            deadline = self.parse_datetime(due_date, due_time)
            if self.is_overdue(deadline):
                return "Просрочено"

        return base_status

    def format_grade(self, coursework: dict, submission: Optional[dict]) -> str:
        """
        Format grade display string.

        Args:
            coursework: CourseWork dictionary
            submission: Student submission dictionary (or None)

        Returns:
            Grade string like "85/100" or "—"
        """
        max_points = coursework.get("maxPoints", 0)

        if not submission:
            return f"—/{max_points}" if max_points else "—"

        assigned_grade = submission.get("assignedGrade")
        draft_grade = submission.get("draftGrade")

        if assigned_grade is not None:
            return f"{assigned_grade}/{max_points}" if max_points else str(assigned_grade)
        elif draft_grade is not None:
            return f"{draft_grade}/{max_points} (черновик)" if max_points else f"{draft_grade} (черновик)"
        else:
            return f"—/{max_points}" if max_points else "—"

    def build_coursework_url(self, course_id: str, coursework_id: str) -> str:
        """Build direct URL to coursework in Classroom."""
        return f"https://classroom.google.com/c/{course_id}/a/{coursework_id}"

    def build_announcement_url(self, course_id: str, announcement_id: str) -> str:
        """Build direct URL to announcement in Classroom."""
        return f"https://classroom.google.com/c/{course_id}/p/{announcement_id}"

    def extract_announcement_snippet(self, text: str) -> str:
        """
        Extract first meaningful line from announcement text.

        Args:
            text: Full announcement text

        Returns:
            Short snippet (first line or first sentence)
        """
        if not text:
            return "Без текста"

        # Clean up text
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)

        # Try to get first line
        lines = text.split('\n')
        first_line = lines[0].strip() if lines else text

        # If first line is too short, try first sentence
        if len(first_line) < 20 and len(text) > 20:
            sentences = re.split(r'[.!?]+', text)
            for s in sentences:
                s = s.strip()
                if len(s) > 20:
                    first_line = s
                    break

        # Truncate if too long
        from config import MAX_ANNOUNCEMENT_SNIPPET
        if len(first_line) > MAX_ANNOUNCEMENT_SNIPPET:
            first_line = first_line[:MAX_ANNOUNCEMENT_SNIPPET - 3] + "..."

        return first_line

    def announcement_requires_action(self, text: str) -> bool:
        """
        Check if announcement contains action keywords.

        Args:
            text: Announcement text

        Returns:
            True if announcement likely requires student action
        """
        from config import ACTION_KEYWORDS
        if not text:
            return False

        text_lower = text.lower()
        return any(keyword in text_lower for keyword in ACTION_KEYWORDS)
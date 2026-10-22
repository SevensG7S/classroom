"""
Configuration module for Google Classroom to Google Sheets sync.

Centralizes all settings, scopes, keywords, and constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
ENV_FILE = BASE_DIR / ".env"
LOCAL_CSV_FILE = BASE_DIR / "classroom_tasks.csv"

# =============================================================================
# GOOGLE API SCOPES
# =============================================================================
# Combined scopes for Classroom API and Google Sheets API
SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.topics.readonly",
    "https://www.googleapis.com/auth/classroom.profile.emails",
    "https://www.googleapis.com/auth/spreadsheets",
]

# =============================================================================
# GOOGLE SHEETS SETTINGS
# =============================================================================
# Google Sheet ID (optional - if not provided, a new sheet will be created)
# Set this in .env file: SPREADSHEET_ID=your_sheet_id_here
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()

# Sheet name (tab name) within the spreadsheet
SHEET_NAME = "Задания и дедлайны"

# =============================================================================
# KEYWORDS FOR ANNOUNCEMENT FILTERING
# =============================================================================
# Keywords that indicate an announcement requires action from student
ACTION_KEYWORDS = [
    "сделать", "прислать", "сдать", "выполнить", "дедлайн", "до ",
    "дз", "задание", "лаба", "практическая", "проект",
    "домашнее", "работа", "отправить", "загрузить", "оформить",
    "подготовить", "написать", "решить", "изучить", "прочитать",
    "посмотреть", "послушать", "сделай", "сдай", "пришли",
    "deadline", "homework", "assignment", "lab", "project",
    "task", "submit", "upload", "complete", "finish"
]

# =============================================================================
# STATUS MAPPINGS
# =============================================================================
# Mapping from Classroom submission states to Russian display statuses
SUBMISSION_STATE_MAP = {
    "NEW": "К сдаче",
    "CREATED": "К сдаче",
    "TURNED_IN": "Сдано",
    "RETURNED": "Оценено",
    "RECLAIMED_BY_STUDENT": "Возвращено на доработку",
}

# Work type states for CourseWork
WORK_STATE_MAP = {
    "PUBLISHED": "Опубликовано",
    "DRAFT": "Черновик",
    "DELETED": "Удалено",
}

# =============================================================================
# COLUMN DEFINITIONS FOR GOOGLE SHEETS
# =============================================================================
COLUMNS = [
    "Предмет",
    "Тема / Раздел",
    "Тип",
    "Название / Суть",
    "Дедлайн / Срок",
    "Статус",
    "Оценка",
    "Ссылка",
]

# Column indices (1-based for Sheets API)
COL_SUBJECT = 1
COL_TOPIC = 2
COL_TYPE = 3
COL_TITLE = 4
COL_DEADLINE = 5
COL_STATUS = 6
COL_GRADE = 7
COL_LINK = 8

# =============================================================================
# CONDITIONAL FORMATTING RULES
# =============================================================================
# Colors for conditional formatting (RGB values 0-1)
COLORS = {
    "overdue_bg": {"red": 1.0, "green": 0.85, "blue": 0.85},      # Light red for overdue
    "due_soon_bg": {"red": 1.0, "green": 0.95, "blue": 0.75},     # Light orange for due soon
    "submitted_bg": {"red": 0.85, "green": 1.0, "blue": 0.85},    # Light green for submitted
    "graded_bg": {"red": 0.8, "green": 0.95, "blue": 0.8},        # Green for graded
    "header_bg": {"red": 0.2, "green": 0.2, "blue": 0.3},         # Dark header
    "header_text": {"red": 1.0, "green": 1.0, "blue": 1.0},       # White text
}

# =============================================================================
# LOGGING / DISPLAY SETTINGS
# =============================================================================
# Date/time format for display
DATETIME_FORMAT = "%Y-%m-%d %H:%M"
DATE_FORMAT = "%Y-%m-%d"

# Max length for announcement snippet
MAX_ANNOUNCEMENT_SNIPPET = 100

# Progress bar settings
SHOW_PROGRESS = True

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_spreadsheet_id() -> str | None:
    """Get spreadsheet ID from environment or return None to create new."""
    return SPREADSHEET_ID if SPREADSHEET_ID else None


def validate_config() -> bool:
    """Validate that required configuration exists."""
    if not CREDENTIALS_FILE.exists():
        print(f"❌ Credentials file not found: {CREDENTIALS_FILE}")
        return False
    return True
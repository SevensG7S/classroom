"""
Configuration module for Google Classroom to Google Sheets sync (Vercel Serverless).

Centralizes all settings, scopes, keywords, and constants.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
# Note: In Vercel, token is stored in GOOGLE_TOKEN_JSON env var, not file
TOKEN_FILE = BASE_DIR / "token.json"
ENV_FILE = BASE_DIR / ".env"

# =============================================================================
# GOOGLE API SCOPES
# =============================================================================
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
# REQUIRED: Google Sheet ID from .env (no auto-creation)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()

# Sheet names (tabs)
SHEET_UPCOMING = "📌 Ближайшие"
SHEET_ALL = "📋 Все задания"
SHEET_ARCHIVE = "📦 Архив"

# =============================================================================
# KEYWORDS FOR ANNOUNCEMENT FILTERING
# =============================================================================
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
SUBMISSION_STATE_MAP = {
    "NEW": "К сдаче",
    "CREATED": "К сдаче",
    "TURNED_IN": "Сдано",
    "RETURNED": "Оценено",
    "RECLAIMED_BY_STUDENT": "Возвращено на доработку",
}

WORK_STATE_MAP = {
    "PUBLISHED": "Опубликовано",
    "DRAFT": "Черновик",
    "DELETED": "Удалено",
}

# Valid statuses for Data Validation dropdown
VALID_STATUSES = [
    "К сдаче",
    "В работе",
    "Сдано",
    "На проверке",
    "Просрочено",
    "Оценено",
    "Игнорировать"
]

# Statuses that appear on "Ближайшие" sheet
UPCOMING_STATUSES = ["К сдаче", "В работе", "Просрочено"]

# Statuses considered "completed" for archiving
COMPLETED_STATUSES = ["Сдано", "Оценено", "Игнорировать"]

# =============================================================================
# COLUMN DEFINITIONS
# =============================================================================
# Main columns (visible to user)
# Column A (0): Предмет
# Column B (1): Тема / Раздел
# Column C (2): Тип
# Column D (3): Название / Суть
# Column E (4): Дедлайн / Срок
# Column F (5): Статус
# Column G (6): Оценка
# Column H (7): Ссылка
# Column I (8): Личные заметки (user-editable, preserved)
# Column J (9): Classroom ID (hidden, for upsert matching)

COL_SUBJECT = 0
COL_TOPIC = 1
COL_TYPE = 2
COL_TITLE = 3
COL_DEADLINE = 4
COL_STATUS = 5
COL_GRADE = 6
COL_LINK = 7
COL_NOTES = 8
COL_CLASSROOM_ID = 9  # Hidden column for upsert matching

COLUMNS_ALL = [
    "Предмет",
    "Тема / Раздел",
    "Тип",
    "Название / Суть",
    "Дедлайн / Срок",
    "Статус",
    "Оценка",
    "Ссылка",
    "Личные заметки",
    "Classroom ID",  # Hidden column
]

# Columns for "Ближайшие" sheet (no hidden ID column needed, but keep for consistency)
COLUMNS_UPCOMING = [
    "Предмет",
    "Тема / Раздел",
    "Тип",
    "Название / Суть",
    "Дедлайн / Срок",
    "Статус",
    "Оценка",
    "Ссылка",
    "Личные заметки",
]

# =============================================================================
# CONDITIONAL FORMATTING COLORS
# =============================================================================
COLORS = {
    "overdue_bg": {"red": 1.0, "green": 0.85, "blue": 0.85},      # Light red for overdue
    "due_soon_bg": {"red": 1.0, "green": 0.95, "blue": 0.7},      # Orange/yellow for <48h
    "submitted_bg": {"red": 0.85, "green": 1.0, "blue": 0.85},    # Light green for submitted
    "graded_bg": {"red": 0.8, "green": 0.95, "blue": 0.8},        # Green for graded
    "in_progress_bg": {"red": 0.9, "green": 0.95, "blue": 1.0},   # Light blue for "В работе"
    "ignored_bg": {"red": 0.95, "green": 0.95, "blue": 0.95},     # Gray for ignored
    "header_bg": {"red": 0.2, "green": 0.2, "blue": 0.3},         # Dark header
    "header_text": {"red": 1.0, "green": 1.0, "blue": 1.0},       # White text
}

# =============================================================================
# TELEGRAM SETTINGS (Optional)
# =============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# =============================================================================
# ARCHIVE SETTINGS
# =============================================================================
ARCHIVE_DAYS_THRESHOLD = 30  # Archive tasks older than this many days

# =============================================================================
# LOGGING / DISPLAY SETTINGS
# =============================================================================
DATETIME_FORMAT = "%Y-%m-%d %H:%M"
DATE_FORMAT = "%Y-%m-%d"
MAX_ANNOUNCEMENT_SNIPPET = 100
SHOW_PROGRESS = False  # Disable in serverless

# =============================================================================
# LOCAL FILE SETTINGS
# =============================================================================
LOCAL_CSV_FILE = BASE_DIR / "classroom_tasks.csv"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_spreadsheet_id(spreadsheet_id: str | None = None) -> str:
    """Get spreadsheet ID from environment or argument - REQUIRED, no auto-creation."""
    if spreadsheet_id:
        return spreadsheet_id
    if not SPREADSHEET_ID:
        raise ValueError("SPREADSHEET_ID is required in environment variables")
    return SPREADSHEET_ID


def get_token_json() -> dict | None:
    """Get token from GOOGLE_TOKEN_JSON environment variable."""
    token_json = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
    if not token_json:
        return None
    try:
        return json.loads(token_json)
    except json.JSONDecodeError:
        return None


def validate_config(spreadsheet_id: str | None = None, csv_only: bool = False) -> bool:
    """Validate that required configuration exists."""
    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: Credentials file not found: {CREDENTIALS_FILE}")
        return False
    # SPREADSHEET_ID can come from .env or command line argument
    # Not required if csv_only is True
    if not csv_only and not spreadsheet_id and not SPREADSHEET_ID:
        print("ERROR: SPREADSHEET_ID is required in .env or environment variables (or use --sheet-id)")
        return False
    return True


def get_credentials_dict() -> dict:
    """Load credentials from credentials.json file."""
    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
"""
Google Sheets API module for Vercel Serverless.

Features:
- Smart upsert: preserves user edits (status, notes) while updating Classroom data
- Two-tab structure: "📌 Ближайшие" (Top 10 active) + "📋 Все задания" (full registry)
- Hidden Classroom ID column for matching
- Data validation dropdowns for Status column
- Conditional formatting (overdue, due soon, submitted, etc.)
- Archive old tasks to "📦 Архив" sheet
- Semicolon-based HYPERLINK formulas for Russian locale compatibility
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import (
    SPREADSHEET_ID, SHEET_UPCOMING, SHEET_ALL, SHEET_ARCHIVE,
    COLUMNS_ALL, COLUMNS_UPCOMING,
    COL_SUBJECT, COL_TOPIC, COL_TYPE, COL_TITLE, COL_DEADLINE,
    COL_STATUS, COL_GRADE, COL_LINK, COL_NOTES, COL_CLASSROOM_ID,
    VALID_STATUSES, UPCOMING_STATUSES, COMPLETED_STATUSES,
    COLORS, ARCHIVE_DAYS_THRESHOLD, DATETIME_FORMAT, get_spreadsheet_id
)


class SheetsAPI:
    """Wrapper for Google Sheets API operations with smart upsert."""

    def __init__(self, credentials, spreadsheet_id: str | None = None):
        """Initialize Google Sheets API client."""
        self.service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self.spreadsheet_id = get_spreadsheet_id(spreadsheet_id)
        self._sheet_ids = {}  # Cache sheet_id by name

    # =========================================================================
    # SHEET MANAGEMENT
    # =========================================================================
    def get_sheet_id(self, sheet_name: str) -> int:
        """Get sheet ID by name, create if not exists."""
        if sheet_name in self._sheet_ids:
            return self._sheet_ids[sheet_name]

        spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("title") == sheet_name:
                self._sheet_ids[sheet_name] = props.get("sheetId")
                return props.get("sheetId")

        # Sheet doesn't exist, create it
        return self.create_sheet(sheet_name)

    def create_sheet(self, sheet_name: str, rows: int = 1000, cols: int = 12) -> int:
        """Create a new sheet with specified properties."""
        request = {
            "addSheet": {
                "properties": {
                    "title": sheet_name,
                    "gridProperties": {
                        "rowCount": rows,
                        "columnCount": cols,
                        "frozenRowCount": 1,
                    }
                }
            }
        }

        response = self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={"requests": [request]}
        ).execute()

        sheet_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]
        self._sheet_ids[sheet_name] = sheet_id
        print(f"Created sheet: {sheet_name} (ID: {sheet_id})")
        return sheet_id

    def ensure_all_sheets_exist(self) -> Dict[str, int]:
        """Ensure all three sheets exist, return dict of sheet_name -> sheet_id."""
        return {
            SHEET_UPCOMING: self.get_sheet_id(SHEET_UPCOMING),
            SHEET_ALL: self.get_sheet_id(SHEET_ALL),
            SHEET_ARCHIVE: self.get_sheet_id(SHEET_ARCHIVE),
        }

    # =========================================================================
    # DATA READING (for upsert)
    # =========================================================================
    def read_sheet_data(self, sheet_name: str) -> List[List[Any]]:
        """Read all data from a sheet (including hidden columns)."""
        try:
            range_name = f"'{sheet_name}'"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                majorDimension="ROWS"
            ).execute()
            return result.get("values", [])
        except HttpError as e:
            print(f"Warning: Could not read {sheet_name}: {e}")
            return []

    def read_all_tasks_from_sheets(self) -> Dict[str, Dict]:
        """
        Read existing tasks from both sheets to build lookup by Classroom ID.
        Returns dict: classroom_id -> {row_index, row_data, sheet_name}
        """
        existing = {}
        for sheet_name in [SHEET_ALL, SHEET_UPCOMING, SHEET_ARCHIVE]:
            data = self.read_sheet_data(sheet_name)
            if len(data) <= 1:  # Only header or empty
                continue
            for row_idx, row in enumerate(data[1:], start=2):  # 1-based, skip header
                # Classroom ID is in column J (index 9)
                if len(row) > COL_CLASSROOM_ID and row[COL_CLASSROOM_ID]:
                    classroom_id = str(row[COL_CLASSROOM_ID]).strip()
                    if classroom_id:
                        existing[classroom_id] = {
                            "row_index": row_idx,
                            "row_data": row,
                            "sheet_name": sheet_name
                        }
        return existing

    # =========================================================================
    # DATA WRITING
    # =========================================================================
    def write_headers(self, sheet_name: str, columns: List[str]) -> None:
        """Write headers to sheet."""
        range_name = f"'{sheet_name}'!A1"
        body = {"values": [columns]}
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body=body
        ).execute()

    def write_rows(self, sheet_name: str, start_row: int, rows: List[List[Any]]) -> None:
        """Write multiple rows starting at given row (1-based)."""
        if not rows:
            return
        range_name = f"'{sheet_name}'!A{start_row}"
        body = {"values": rows}
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",  # Allows formulas
            body=body
        ).execute()

    def update_row(self, sheet_name: str, row_index: int, row_data: List[Any]) -> None:
        """Update a single row."""
        range_name = f"'{sheet_name}'!A{row_index}"
        body = {"values": [row_data]}
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

    def clear_sheet_data(self, sheet_name: str, keep_header: bool = True) -> None:
        """Clear sheet data, optionally keeping header row."""
        start_row = 2 if keep_header else 1
        range_name = f"'{sheet_name}'!A{start_row}:Z"
        self.service.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=range_name
        ).execute()

    # =========================================================================
    # FORMATTING & VALIDATION
    # =========================================================================
    def apply_formatting(self, sheet_name: str, num_rows: int, is_upcoming: bool = False) -> None:
        """Apply all formatting to a sheet."""
        sheet_id = self.get_sheet_id(sheet_name)
        requests = []

        # 1. Format header row
        requests.append(self._format_header_row(sheet_id))

        # 2. Set column widths
        requests.extend(self._set_column_widths(sheet_id))

        # 3. Data validation for Status column
        requests.append(self._add_status_validation(sheet_id, num_rows))

        # 4. Conditional formatting
        requests.extend(self._conditional_formatting(sheet_id, num_rows, is_upcoming))

        # 5. Format data cells
        requests.append(self._format_data_cells(sheet_id, num_rows))

        # 6. Hide Classroom ID column (column J, index 9)
        requests.append(self._hide_column(sheet_id, COL_CLASSROOM_ID))

        # 7. Add filter
        requests.append(self._add_filter(sheet_id, num_rows))

        if requests:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests}
            ).execute()

    def _format_header_row(self, sheet_id: int) -> dict:
        return {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLORS["header_bg"],
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": COLORS["header_text"],
                            "fontSize": 11,
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)"
            }
        }

    def _set_column_widths(self, sheet_id: int) -> List[dict]:
        widths = [
            (COL_SUBJECT, 200),   # Предмет
            (COL_TOPIC, 180),     # Тема / Раздел
            (COL_TYPE, 120),      # Тип
            (COL_TITLE, 350),     # Название / Суть
            (COL_DEADLINE, 160),  # Дедлайн / Срок
            (COL_STATUS, 140),    # Статус
            (COL_GRADE, 120),     # Оценка
            (COL_LINK, 140),      # Ссылка
            (COL_NOTES, 200),     # Личные заметки
            (COL_CLASSROOM_ID, 0), # Hidden
        ]
        requests = []
        for col_index, width in widths:
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": col_index,
                        "endIndex": col_index + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize"
                }
            })
        return requests

    def _add_status_validation(self, sheet_id: int, num_rows: int) -> dict:
        """Add dropdown validation for Status column (F, index 5)."""
        return {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": num_rows + 1,
                    "startColumnIndex": COL_STATUS,
                    "endColumnIndex": COL_STATUS + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": s} for s in VALID_STATUSES]
                    },
                    "inputMessage": "Выберите статус задания",
                    "strict": True,
                    "showCustomUi": True
                }
            }
        }

    def _conditional_formatting(self, sheet_id: int, num_rows: int, is_upcoming: bool) -> List[dict]:
        """Add conditional formatting rules."""
        if num_rows == 0:
            return []

        requests = []
        end_col = COL_CLASSROOM_ID  # Include hidden column in formatting range

        # Rule 1: Overdue - light red
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": end_col,
                    }],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Просрочено"}]},
                        "format": {"backgroundColor": COLORS["overdue_bg"]}
                    }
                },
                "index": 0
            }
        })

        # Rule 2: Due soon (<48h) - orange/yellow
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": end_col,
                    }],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "К сдаче"}]},
                        "format": {"backgroundColor": COLORS["due_soon_bg"]}
                    }
                },
                "index": 1
            }
        })

        # Rule 3: In progress - light blue
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": end_col,
                    }],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "В работе"}]},
                        "format": {"backgroundColor": COLORS["in_progress_bg"]}
                    }
                },
                "index": 2
            }
        })

        # Rule 4: Submitted - light green
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": end_col,
                    }],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Сдано"}]},
                        "format": {"backgroundColor": COLORS["submitted_bg"]}
                    }
                },
                "index": 3
            }
        })

        # Rule 5: Graded - green
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": end_col,
                    }],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Оценено"}]},
                        "format": {"backgroundColor": COLORS["graded_bg"]}
                    }
                },
                "index": 4
            }
        })

        # Rule 6: Ignored - gray
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": end_col,
                    }],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Игнорировать"}]},
                        "format": {"backgroundColor": COLORS["ignored_bg"]}
                    }
                },
                "index": 5
            }
        })

        return requests

    def _format_data_cells(self, sheet_id: int, num_rows: int) -> dict:
        return {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": num_rows + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": COL_CLASSROOM_ID + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP",
                        "textFormat": {"fontSize": 10},
                    }
                },
                "fields": "userEnteredFormat(verticalAlignment,wrapStrategy,textFormat)"
            }
        }

    def _hide_column(self, sheet_id: int, col_index: int) -> dict:
        return {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": col_index,
                    "endIndex": col_index + 1,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser"
            }
        }

    def _add_filter(self, sheet_id: int, num_rows: int) -> dict:
        return {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": COL_CLASSROOM_ID,
                    }
                }
            }
        }

    # =========================================================================
    # ARCHIVE OPERATIONS
    # =========================================================================
    def archive_old_tasks(self, all_sheet_name: str = SHEET_ALL) -> int:
        """
        Move old completed tasks to Archive sheet.
        Returns number of archived rows.
        """
        # Read all tasks
        all_data = self.read_sheet_data(all_sheet_name)
        if len(all_data) <= 1:
            return 0

        archive_sheet_id = self.get_sheet_id(SHEET_ARCHIVE)
        # Ensure archive has headers
        archive_data = self.read_sheet_data(SHEET_ARCHIVE)
        if len(archive_data) == 0:
            self.write_headers(SHEET_ARCHIVE, COLUMNS_ALL)

        rows_to_archive = []
        rows_to_keep = [all_data[0]]  # Keep header
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=ARCHIVE_DAYS_THRESHOLD)

        for row in all_data[1:]:
            if len(row) <= COL_STATUS:
                rows_to_keep.append(row)
                continue

            status = str(row[COL_STATUS]).strip() if row[COL_STATUS] else ""
            deadline_str = str(row[COL_DEADLINE]).strip() if len(row) > COL_DEADLINE and row[COL_DEADLINE] else ""

            should_archive = False

            # Archive if completed status AND deadline older than threshold
            if status in COMPLETED_STATUSES:
                if deadline_str and deadline_str != "Нет срока":
                    try:
                        # Parse deadline
                        deadline = datetime.strptime(deadline_str, DATETIME_FORMAT).replace(tzinfo=timezone.utc)
                        if deadline < cutoff:
                            should_archive = True
                    except ValueError:
                        pass

            if should_archive:
                rows_to_archive.append(row)
            else:
                rows_to_keep.append(row)

        if rows_to_archive:
            # Append to archive
            start_row = len(archive_data) + 1
            self.write_rows(SHEET_ARCHIVE, start_row, rows_to_archive)

            # Rewrite ALL sheet with remaining rows
            self.clear_sheet_data(all_sheet_name)
            self.write_rows(all_sheet_name, 2, rows_to_keep[1:])  # Skip header, start at row 2

            print(f"Archived {len(rows_to_archive)} old tasks")
            return len(rows_to_archive)

        return 0

    # =========================================================================
    # SMART UPSERT LOGIC
    # =========================================================================
    def upsert_tasks(self, tasks: List[Dict]) -> Tuple[int, int, int]:
        """
        Smart upsert: update existing rows, add new ones, preserve user edits.

        Returns: (updated_count, added_count, archived_count)
        """
        # 1. Read existing data from ALL sheet (source of truth)
        existing = self.read_all_tasks_from_sheets()

        # 2. Build task lookup by Classroom ID
        task_by_id = {}
        for task in tasks:
            cid = task.get("_classroom_id")
            if cid:
                task_by_id[cid] = task

        # 3. Prepare rows for ALL sheet
        all_rows = [COLUMNS_ALL]
        updated = 0
        added = 0

        for cid, task in task_by_id.items():
            row = self._task_to_row(task, include_id=True)
            if cid in existing:
                # EXISTING: Merge - preserve user edits (Status, Notes)
                existing_row = existing[cid]["row_data"]
                existing_row_idx = existing[cid]["row_index"]

                # Preserve user's Status if they manually changed it
                # Only override if Classroom status is "Оценено" (authoritative)
                classroom_status = row[COL_STATUS]
                user_status = existing_row[COL_STATUS] if len(existing_row) > COL_STATUS else ""

                # Preserve Notes (user's personal notes)
                user_notes = existing_row[COL_NOTES] if len(existing_row) > COL_NOTES else ""

                # Preserve user status unless Classroom says "Оценено" (final)
                final_status = classroom_status
                if user_status and user_status != classroom_status:
                    # User manually changed status - keep it unless graded
                    if classroom_status != "Оценено":
                        final_status = user_status

                row[COL_STATUS] = final_status
                row[COL_NOTES] = user_notes

                # Update in place
                self.update_row(SHEET_ALL, existing_row_idx, row)
                updated += 1
            else:
                # NEW task
                all_rows.append(row)
                added += 1

        # 4. Write all tasks to ALL sheet (new tasks only, existing were updated in place)
        if added > 0:
            self.clear_sheet_data(SHEET_ALL)
            self.write_rows(SHEET_ALL, 1, all_rows)
            # Re-apply formatting
            self.apply_formatting(SHEET_ALL, len(all_rows) - 1)
        elif updated > 0:
            # Just re-apply formatting to ensure validation is on new rows
            all_data = self.read_sheet_data(SHEET_ALL)
            self.apply_formatting(SHEET_ALL, len(all_data) - 1)

        # 5. Rebuild UPCOMING sheet (Top 10 active)
        self._rebuild_upcoming_sheet(task_by_id, existing)

        # 6. Archive old tasks
        archived = self.archive_old_tasks(SHEET_ALL)

        return updated, added, archived

    def _task_to_row(self, task: Dict, include_id: bool = True) -> List[Any]:
        """Convert task dict to row array for Sheets."""
        url = task.get("url", "")
        if url:
            # Use semicolon for Russian locale compatibility
            link_formula = f'=HYPERLINK("{url}"; "Открыть")'
        else:
            link_formula = ""

        row = [
            task.get("subject", ""),           # A: Предмет
            task.get("topic", ""),             # B: Тема / Раздел
            task.get("type", ""),              # C: Тип
            task.get("title", ""),             # D: Название / Суть
            task.get("deadline", ""),          # E: Дедлайн / Срок
            task.get("status", ""),            # F: Статус
            task.get("grade", ""),             # G: Оценка
            link_formula,                      # H: Ссылка (formula)
            task.get("notes", ""),             # I: Личные заметки
        ]
        if include_id:
            row.append(task.get("_classroom_id", ""))  # J: Classroom ID (hidden)
        return row

    def _rebuild_upcoming_sheet(self, task_by_id: Dict, existing: Dict) -> None:
        """Rebuild the 'Ближайшие' sheet with Top 10 active tasks."""
        # Filter tasks with upcoming statuses
        upcoming_tasks = []
        for task in task_by_id.values():
            status = task.get("status", "")
            if status in UPCOMING_STATUSES:
                # Parse deadline for sorting
                deadline_str = task.get("deadline", "")
                deadline_dt = None
                if deadline_str and deadline_str != "Нет срока":
                    try:
                        deadline_dt = datetime.strptime(deadline_str, DATETIME_FORMAT).replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                upcoming_tasks.append((deadline_dt, task))

        # Sort: with deadline first (earliest), then without deadline
        upcoming_tasks.sort(key=lambda x: (x[0] is None, x[0] or datetime.max))

        # Take top 10
        top_tasks = [t[1] for t in upcoming_tasks[:10]]

        # Build rows for upcoming sheet (preserve notes from existing)
        rows = [COLUMNS_UPCOMING]
        for task in top_tasks:
            cid = task.get("_classroom_id")
            # Check if user has notes in existing
            notes = ""
            if cid and cid in existing:
                existing_row = existing[cid]["row_data"]
                if len(existing_row) > COL_NOTES:
                    notes = existing_row[COL_NOTES]

            row = self._task_to_row(task, include_id=False)
            row[COL_NOTES] = notes  # Override with preserved notes
            rows.append(row)

        # Write upcoming sheet
        self.clear_sheet_data(SHEET_UPCOMING)
        self.write_rows(SHEET_UPCOMING, 1, rows)
        self.apply_formatting(SHEET_UPCOMING, len(rows) - 1, is_upcoming=True)

    # =========================================================================
    # TELEGRAM NOTIFICATIONS
    # =========================================================================
    def check_and_notify_upcoming(self, tasks: List[Dict], bot_token: str, chat_id: str) -> int:
        """
        Check for tasks due within 24h with status 'К сдаче' and send Telegram notifications.
        Returns number of notifications sent.
        """
        if not bot_token or not chat_id:
            return 0

        import requests
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)
        sent = 0

        for task in tasks:
            status = task.get("status", "")
            if status != "К сдаче":
                continue

            deadline_str = task.get("deadline", "")
            if not deadline_str or deadline_str == "Нет срока":
                continue

            try:
                deadline = datetime.strptime(deadline_str, DATETIME_FORMAT).replace(tzinfo=timezone.utc)
                if now < deadline < cutoff:
                    # Send notification
                    message = (
                        f"⚠️ <b>Дедлайн через 24 часа!</b>\n\n"
                        f"📚 <b>Предмет:</b> {task.get('subject', '')}\n"
                        f"📝 <b>Задание:</b> {task.get('title', '')}\n"
                        f"📅 <b>Срок:</b> {deadline_str}\n"
                        f"🔗 <a href='{task.get('url', '')}'>Открыть в Classroom</a>"
                    )
                    resp = requests.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": message,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True
                        },
                        timeout=10
                    )
                    if resp.status_code == 200:
                        sent += 1
            except (ValueError, requests.RequestException) as e:
                print(f"Telegram notification failed: {e}")

        return sent
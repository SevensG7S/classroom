"""
Google Sheets API module.

Handles creating/updating spreadsheets, formatting, conditional formatting,
and writing task data to Google Sheets.
"""

from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from rich.console import Console

from config import (
    COLUMNS, COL_SUBJECT, COL_TOPIC, COL_TYPE, COL_TITLE,
    COL_DEADLINE, COL_STATUS, COL_GRADE, COL_LINK,
    SHEET_NAME, COLORS, get_spreadsheet_id
)

console = Console()


class SheetsAPI:
    """Wrapper for Google Sheets API operations."""

    def __init__(self, credentials):
        """
        Initialize Google Sheets API client.

        Args:
            credentials: Google OAuth2 credentials
        """
        self.service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self.drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self.spreadsheet_id = None

    # =========================================================================
    # SPREADSHEET MANAGEMENT
    # =========================================================================
    def get_or_create_spreadsheet(self) -> str:
        """
        Get existing spreadsheet by ID or create a new one.

        Returns:
            Spreadsheet ID
        """
        spreadsheet_id = get_spreadsheet_id()

        if spreadsheet_id:
            # Try to use existing spreadsheet
            try:
                self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                console.print(f"📄 Using existing spreadsheet: [link]https://docs.google.com/spreadsheets/d/{spreadsheet_id}[/link]")
                self.spreadsheet_id = spreadsheet_id
                return spreadsheet_id
            except HttpError as e:
                console.print(f"[yellow]⚠️  Could not access spreadsheet {spreadsheet_id}: {e}[/yellow]")
                console.print("   Creating new spreadsheet instead...")

        # Create new spreadsheet
        return self.create_spreadsheet()

    def create_spreadsheet(self) -> str:
        """
        Create a new Google Spreadsheet with the tasks sheet.

        Returns:
            New spreadsheet ID
        """
        spreadsheet_body = {
            "properties": {
                "title": f"Classroom Задания - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "locale": "ru_RU",
                "timeZone": "Europe/Moscow",
            },
            "sheets": [{
                "properties": {
                    "title": SHEET_NAME,
                    "gridProperties": {
                        "rowCount": 1000,
                        "columnCount": len(COLUMNS),
                        "frozenRowCount": 1,  # Freeze header row
                    }
                }
            }]
        }

        try:
            response = self.service.spreadsheets().create(body=spreadsheet_body).execute()
            self.spreadsheet_id = response["spreadsheetId"]
            console.print(f"✅ Created new spreadsheet: [link]https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}[/link]")
            return self.spreadsheet_id

        except HttpError as e:
            console.print(f"[red]❌ Failed to create spreadsheet: {e}[/red]")
            raise

    def ensure_sheet_exists(self) -> int:
        """
        Ensure the target sheet exists, create if needed.

        Returns:
            Sheet ID (gid)
        """
        if not self.spreadsheet_id:
            self.get_or_create_spreadsheet()

        # Get spreadsheet metadata
        spreadsheet = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()

        # Check if sheet exists
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            if props.get("title") == SHEET_NAME:
                return props.get("sheetId")

        # Sheet doesn't exist, create it
        return self.add_sheet()

    def add_sheet(self) -> int:
        """Add a new sheet with the correct name and properties."""
        request = {
            "addSheet": {
                "properties": {
                    "title": SHEET_NAME,
                    "gridProperties": {
                        "rowCount": 1000,
                        "columnCount": len(COLUMNS),
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
        console.print(f"✅ Created sheet '{SHEET_NAME}' (ID: {sheet_id})")
        return sheet_id

    # =========================================================================
    # DATA OPERATIONS
    # =========================================================================
    def clear_sheet(self) -> None:
        """Clear all data from the sheet (except header formatting)."""
        self.ensure_sheet_exists()

        # Clear all content
        self.service.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{SHEET_NAME}'",
        ).execute()

        console.print("🧹 Sheet cleared")

    def write_headers(self) -> None:
        """Write column headers to the first row."""
        range_name = f"'{SHEET_NAME}'!A1"
        body = {"values": [COLUMNS]}

        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body=body
        ).execute()

    def write_data(self, rows: list[list]) -> None:
        """
        Write data rows to the sheet.

        Args:
            rows: List of row data (each row is a list of cell values)
        """
        if not rows:
            console.print("[yellow]⚠️  No data rows to write[/yellow]")
            return

        range_name = f"'{SHEET_NAME}'!A2"
        body = {"values": rows}

        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",  # Allows formulas like HYPERLINK
            body=body
        ).execute()

        console.print(f"📝 Written [bold]{len(rows)}[/bold] data rows")

    def apply_formatting(self, num_rows: int) -> None:
        """
        Apply all formatting to the sheet.

        Args:
            num_rows: Number of data rows (excluding header)
        """
        sheet_id = self.ensure_sheet_exists()
        requests = []

        # 1. Format header row
        requests.append(self._format_header_row(sheet_id))

        # 2. Set column widths
        requests.extend(self._set_column_widths(sheet_id))

        # 3. Apply conditional formatting
        requests.extend(self._conditional_formatting(sheet_id, num_rows))

        # 4. Format data cells (alignment, wrap)
        requests.append(self._format_data_cells(sheet_id, num_rows))

        # 5. Add filter view
        requests.append(self._add_filter(sheet_id, num_rows))

        if requests:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests}
            ).execute()
            console.print("🎨 Formatting applied")

    def _format_header_row(self, sheet_id: int) -> dict:
        """Format header row with dark background and white bold text."""
        return {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                },
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

    def _set_column_widths(self, sheet_id: int) -> list[dict]:
        """Set column widths for better readability."""
        widths = [
            (COL_SUBJECT - 1, 200),   # Предмет
            (COL_TOPIC - 1, 180),     # Тема / Раздел
            (COL_TYPE - 1, 120),      # Тип
            (COL_TITLE - 1, 350),     # Название / Суть
            (COL_DEADLINE - 1, 160),  # Дедлайн / Срок
            (COL_STATUS - 1, 140),    # Статус
            (COL_GRADE - 1, 120),     # Оценка
            (COL_LINK - 1, 140),      # Ссылка
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

    def _conditional_formatting(self, sheet_id: int, num_rows: int) -> list[dict]:
        """Add conditional formatting rules for status column."""
        if num_rows == 0:
            return []

        requests = []

        # Rule 1: Overdue / Просрочено - light red
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(COLUMNS),
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": "Просрочено"}]
                        },
                        "format": {
                            "backgroundColor": COLORS["overdue_bg"]
                        }
                    }
                },
                "index": 0
            }
        })

        # Rule 2: Due soon / К сдаче (if deadline soon) - light orange
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(COLUMNS),
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": "К сдаче"}]
                        },
                        "format": {
                            "backgroundColor": COLORS["due_soon_bg"]
                        }
                    }
                },
                "index": 1
            }
        })

        # Rule 3: Submitted / Сдано - light green
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(COLUMNS),
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": "Сдано"}]
                        },
                        "format": {
                            "backgroundColor": COLORS["submitted_bg"]
                        }
                    }
                },
                "index": 2
            }
        })

        # Rule 4: Graded / Оценено - green
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(COLUMNS),
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_EQ",
                            "values": [{"userEnteredValue": "Оценено"}]
                        },
                        "format": {
                            "backgroundColor": COLORS["graded_bg"]
                        }
                    }
                },
                "index": 3
            }
        })

        return requests

    def _format_data_cells(self, sheet_id: int, num_rows: int) -> dict:
        """Format data cells with alignment and text wrapping."""
        return {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": num_rows + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(COLUMNS),
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

    def _add_filter(self, sheet_id: int, num_rows: int) -> dict:
        """Add filter view to the header row."""
        return {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": num_rows + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(COLUMNS),
                    }
                }
            }
        }

    # =========================================================================
    # HIGH-LEVEL OPERATIONS
    # =========================================================================
    def sync_tasks(self, tasks: list[dict]) -> str:
        """
        Full sync: clear sheet, write headers, write data, apply formatting.

        Args:
            tasks: List of task dictionaries

        Returns:
            Spreadsheet URL
        """
        console.print("\n📊 Syncing to Google Sheets...")

        # Get or create spreadsheet
        self.get_or_create_spreadsheet()

        # Clear existing data
        self.clear_sheet()

        # Write headers
        self.write_headers()

        # Convert tasks to rows
        rows = self._tasks_to_rows(tasks)

        # Write data
        self.write_data(rows)

        # Apply formatting
        self.apply_formatting(len(rows))

        # Return URL
        url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
        console.print(f"\n✅ Sync complete! Open: [link]{url}[/link]")
        return url

    def _tasks_to_rows(self, tasks: list[dict]) -> list[list]:
        """
        Convert task dictionaries to row arrays for Sheets.

        Args:
            tasks: List of task dictionaries

        Returns:
            List of rows (each row is a list of cell values)
        """
        rows = []

        for task in tasks:
            # Build hyperlink formula for the link column
            url = task.get("url", "")
            if url:
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
            ]
            rows.append(row)

        return rows

    def get_spreadsheet_url(self) -> str:
        """Get the spreadsheet URL."""
        if self.spreadsheet_id:
            return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
        return ""
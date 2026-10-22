"""
Authentication module for Google APIs (Classroom and Sheets).

Handles OAuth 2.0 flow, token storage, and credential refresh.
"""

import os
import json
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from rich.console import Console

from config import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, validate_config

console = Console()


def get_credentials() -> Credentials:
    """
    Get valid Google API credentials.

    Loads existing token, refreshes if expired, or runs OAuth flow if needed.
    Saves updated token to token.json.

    Returns:
        Credentials: Valid Google OAuth2 credentials
    """
    if not validate_config():
        raise FileNotFoundError("Configuration validation failed. Check credentials.json")

    creds = None

    # Load existing token if available
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load existing token: {e}[/yellow]")
            creds = None

    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            console.print("[cyan]Refreshing expired token...[/cyan]")
            try:
                creds.refresh(Request())
                console.print("[green]Token refreshed successfully[/green]")
            except Exception as e:
                console.print(f"[red]Failed to refresh token: {e}[/red]")
                creds = None
        else:
            console.print("[bold cyan]Starting OAuth authorization flow...[/bold cyan]")
            console.print("   A browser window will open for you to grant permissions.")
            creds = run_oauth_flow()

        # Save the new/refreshed credentials
        if creds:
            save_credentials(creds)

    return creds


def run_oauth_flow() -> Credentials:
    """
    Run the OAuth 2.0 authorization flow for installed applications.

    Returns:
        Credentials: New OAuth2 credentials
    """
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        SCOPES
    )

    # Run local server on port 0 (auto-select available port)
    creds = flow.run_local_server(port=0, open_browser=True)

    return creds


def save_credentials(creds: Credentials) -> None:
    """
    Save credentials to token.json file.

    Args:
        creds: Google OAuth2 credentials to save
    """
    try:
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }

        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)

        # Set restrictive permissions on token file (Unix-like systems)
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except Exception:
            pass  # Windows doesn't support chmod the same way

        console.print(f"[green]Token saved to {TOKEN_FILE}[/green]")

    except Exception as e:
        console.print(f"[red]Failed to save token: {e}[/red]")


def delete_token() -> bool:
    """
    Delete the stored token file (useful for re-authentication).

    Returns:
        bool: True if file was deleted, False if it didn't exist
    """
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        console.print(f"[yellow]Token file deleted: {TOKEN_FILE}[/yellow]")
        return True
    return False


def print_token_info() -> None:
    """Print information about the current token (for debugging)."""
    if not TOKEN_FILE.exists():
        console.print("[red]No token file found[/red]")
        return

    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token_data = json.load(f)

        console.print("\n[bold]Token Information:[/bold]")
        console.print(f"   Client ID: {token_data.get('client_id', 'N/A')[:20]}...")
        console.print(f"   Scopes: {len(token_data.get('scopes', []))} scopes")
        console.print(f"   Has refresh token: {'Yes' if token_data.get('refresh_token') else 'No'}")
        console.print(f"   Expires: {token_data.get('expiry', 'N/A')}")
        console.print(f"   File: {TOKEN_FILE}")

    except Exception as e:
        console.print(f"[red]Failed to read token: {e}[/red]")
"""
Authentication module for Google APIs (Classroom and Sheets).

Handles OAuth 2.0 flow, token storage in environment variable (for Vercel serverless).
"""

import os
import json
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2 import service_account

from config import SCOPES, CREDENTIALS_FILE, get_token_json, get_credentials_dict

# In-memory token cache for serverless (persists across warm invocations)
_cached_credentials: Optional[Credentials] = None


def get_credentials() -> Credentials:
    """
    Get valid Google API credentials for serverless environment.

    Priority:
    1. In-memory cache (warm start)
    2. GOOGLE_TOKEN_JSON environment variable
    3. Local token.json file (for local development)
    4. OAuth flow (only works locally, not on Vercel)

    Returns:
        Credentials: Valid Google OAuth2 credentials
    """
    global _cached_credentials

    # 1. Return cached credentials if valid
    if _cached_credentials and _cached_credentials.valid:
        return _cached_credentials

    # 2. Try loading from environment variable (Vercel)
    token_data = get_token_json()
    if token_data:
        try:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            if creds and creds.valid:
                _cached_credentials = creds
                return creds
            # Try refresh if expired
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _cached_credentials = creds
                # Note: In Vercel, you'd need to update the env var manually
                # or use a persistent store. For now, cache in memory.
                return creds
        except Exception as e:
            print(f"Warning: Failed to load token from env: {e}")

    # 3. Try local token.json file (local development)
    if os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            if creds and creds.valid:
                _cached_credentials = creds
                return creds
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _cached_credentials = creds
                # Save back to file for local dev
                save_credentials_to_file(creds)
                return creds
        except Exception as e:
            print(f"Warning: Failed to load local token: {e}")

    # 4. Service Account support (alternative for serverless)
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if sa_json:
        try:
            sa_info = json.loads(sa_json)
            creds = service_account.Credentials.from_service_account_info(
                sa_info, scopes=SCOPES
            )
            _cached_credentials = creds
            return creds
        except Exception as e:
            print(f"Warning: Failed to load service account: {e}")

    # 5. OAuth flow (only works locally with browser)
    # This will fail on Vercel since no browser
    print("Starting OAuth authorization flow (local only)...")
    creds = run_oauth_flow()
    if creds:
        _cached_credentials = creds
        save_credentials_to_file(creds)
    return creds


def run_oauth_flow() -> Credentials:
    """
    Run the OAuth 2.0 authorization flow for installed applications.
    Only works locally, not on Vercel.
    """
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        SCOPES
    )
    creds = flow.run_local_server(port=0, open_browser=True)
    return creds


def save_credentials_to_file(creds: Credentials) -> None:
    """Save credentials to local token.json file (local dev only)."""
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
        with open("token.json", "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save token file: {e}")


def get_token_for_env_var() -> str:
    """
    Generate token JSON string for setting GOOGLE_TOKEN_JSON environment variable.
    Run this locally after authentication to get the token string.
    """
    creds = get_credentials()
    if not creds or not creds.valid:
        return ""

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    return json.dumps(token_data, ensure_ascii=False)


def print_token_for_vercel() -> None:
    """Print token JSON for copying to Vercel environment variables."""
    token_str = get_token_for_env_var()
    if token_str:
        print("\n" + "="*60)
        print("COPY THIS TO VERCEL ENVIRONMENT VARIABLE GOOGLE_TOKEN_JSON:")
        print("="*60)
        print(token_str)
        print("="*60 + "\n")
    else:
        print("No valid token available. Run locally first to authenticate.")


def delete_token() -> None:
    """Delete local token.json file (for re-authentication)."""
    if os.path.exists("token.json"):
        os.remove("token.json")
        print("Token file deleted.")
    else:
        print("No token file found.")


def print_token_info() -> None:
    """Print current token information."""
    creds = get_credentials()
    if not creds:
        print("No valid credentials found.")
        return

    print("\n" + "="*60)
    print("TOKEN INFORMATION:")
    print("="*60)
    print(f"Valid: {creds.valid}")
    print(f"Expired: {creds.expired}")
    print(f"Has refresh token: {bool(creds.refresh_token)}")
    print(f"Client ID: {creds.client_id}")
    print(f"Scopes: {creds.scopes}")
    if creds.expiry:
        print(f"Expires at: {creds.expiry}")
    print("="*60 + "\n")
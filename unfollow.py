#!/usr/bin/env python3
"""
Instagram Unfollower — Web API Edition
=======================================
Uses Instagram's *browser-facing* web API with your session cookie.
No instagrapi / mobile private API required.

Usage:
    python unfollow.py --dry-run    # preview without making changes
    python unfollow.py              # interactive confirmation, then unfollow
"""

import argparse
import json
import os
import random
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

WHITELIST_FILE = "config/whitelist.json"

# Standard browser headers so Instagram treats requests like Chrome
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "936619743392459",   # Instagram web app ID
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_whitelist() -> set:
    """Load whitelisted usernames from config/whitelist.json."""
    try:
        with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        usernames = data.get("whitelist", []) if isinstance(data, dict) else data
        return {u.lower().strip() for u in usernames if u}
    except FileNotFoundError:
        print(f"[WARN] {WHITELIST_FILE} not found — no accounts will be whitelisted.")
        return set()
    except Exception as e:
        print(f"[WARN] Could not load whitelist: {e}")
        return set()


def build_session(session_id: str) -> requests.Session:
    """Create a requests.Session pre-loaded with the Instagram session cookie."""
    s = requests.Session()
    # Set the cookie on all instagram.com sub-domains
    for domain in [".instagram.com", "www.instagram.com", "instagram.com"]:
        s.cookies.set("sessionid", session_id, domain=domain)
    s.headers.update(HEADERS)
    return s


def init_session(session: requests.Session) -> bool:
    """
    Visit instagram.com to pick up csrftoken and other required cookies.
    Returns True if the site is reachable.
    """
    try:
        resp = session.get("https://www.instagram.com/", timeout=15)
        return resp.status_code == 200
    except Exception as e:
        print(f"[ERROR] Could not reach instagram.com: {e}")
        return False


def get_user_id(session: requests.Session, username: str) -> str | None:
    """Fetch the numeric user ID via the web profile-info endpoint."""
    try:
        resp = session.get(
            "https://www.instagram.com/api/v1/users/web_profile_info/",
            params={"username": username},
            timeout=30,
        )
        if resp.status_code == 200 and resp.text.strip():
            data = resp.json()
            return data.get("data", {}).get("user", {}).get("id")
        if resp.status_code == 200 and not resp.text.strip():
            print("[ERROR] Profile lookup returned an empty response — session ID is likely expired.")
        else:
            print(f"[ERROR] Profile lookup returned HTTP {resp.status_code}.")
        return None
    except Exception as e:
        print(f"[ERROR] Profile lookup failed: {e}")
        return None


def get_following(session: requests.Session, user_id: str) -> list:
    """
    Fetch the complete following list using the *web* friendships API
    (www.instagram.com instead of i.instagram.com).

    Returns a list of user dicts with keys: pk, username, full_name, is_private.
    """
    following = []
    max_id = None
    page = 1

    while True:
        params = {"count": 200}
        if max_id:
            params["max_id"] = max_id

        try:
            resp = session.get(
                f"https://www.instagram.com/api/v1/friendships/{user_id}/following/",
                params=params,
                timeout=30,
            )
        except requests.RequestException as e:
            raise Exception(f"Network error while fetching following list: {e}") from e

        if resp.status_code == 401:
            raise Exception(
                "HTTP 401 — session ID is invalid or expired. "
                "Re-copy it from instagram.com and update IG_SESSIONID in .env."
            )
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code} from Instagram — unexpected error.")

        if not resp.text.strip():
            raise Exception(
                "Instagram returned an empty response (no JSON body). "
                "Your session ID may be expired or Instagram is rate-limiting you. "
                "Wait 30 minutes, refresh your session ID, and try again."
            )

        data = resp.json()
        users = data.get("users", [])
        following.extend(users)
        print(f"  Page {page}: +{len(users)} users  (total: {len(following)})")

        next_max_id = data.get("next_max_id")
        if not next_max_id or not users:
            break

        max_id = next_max_id
        page += 1
        time.sleep(1.5)   # polite pause between pages

    return following


def get_csrf_token(session: requests.Session) -> str:
    """Extract the csrftoken cookie from the session."""
    token = session.cookies.get("csrftoken")
    if not token:
        for cookie in session.cookies:
            if cookie.name == "csrftoken":
                return cookie.value
    return token or ""


def unfollow_user(
    session: requests.Session,
    user_id: str,
    username: str,
    csrf: str,
) -> bool:
    """Send an unfollow request via the web friendships/destroy endpoint."""
    try:
        resp = session.post(
            f"https://www.instagram.com/api/v1/friendships/destroy/{user_id}/",
            data={"user_id": user_id},
            headers={
                "X-CSRFToken": csrf,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"https://www.instagram.com/{username}/",
            },
            timeout=30,
        )
        return resp.status_code == 200
    except Exception:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unfollow everyone on Instagram except whitelisted accounts."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which accounts would be unfollowed without making any changes.",
    )
    args = parser.parse_args()

    # ── Credentials ───────────────────────────────────────────────────────────
    username   = os.getenv("IG_USERNAME",  "").strip()
    session_id = os.getenv("IG_SESSIONID", "").strip()

    if not username:
        print("[ERROR] IG_USERNAME is not set in your .env file.")
        sys.exit(1)

    if not session_id:
        print("[ERROR] IG_SESSIONID is not set in your .env file.")
        print()
        print("How to get your session ID:")
        print("  1. Open https://www.instagram.com in Chrome and log in.")
        print("  2. Press F12 (or Cmd+Option+I) to open DevTools.")
        print("  3. Go to: Application → Cookies → https://www.instagram.com")
        print("  4. Find the cookie named 'sessionid' and copy its value.")
        print("  5. Add to .env:  IG_SESSIONID=<paste here>")
        sys.exit(1)

    # ── Whitelist ─────────────────────────────────────────────────────────────
    whitelist = load_whitelist()
    print(f"Loaded {len(whitelist)} whitelisted account(s): {', '.join(sorted(whitelist)) or '(none)'}")

    # ── Build session ─────────────────────────────────────────────────────────
    print("\nInitialising web session...")
    session = build_session(session_id)
    if not init_session(session):
        print("[ERROR] Could not reach instagram.com — check your internet connection.")
        sys.exit(1)

    # ── Resolve user ID ───────────────────────────────────────────────────────
    print(f"Looking up user ID for @{username}...")
    user_id = get_user_id(session, username)

    if not user_id:
        print()
        print("=" * 55)
        print("Could not fetch your profile.")
        print("Your session ID is most likely expired.")
        print()
        print("Fix:")
        print("  1. Open instagram.com — make sure you are still logged in.")
        print("  2. DevTools → Application → Cookies → copy 'sessionid'.")
        print("  3. Update IG_SESSIONID in your .env file.")
        print("=" * 55)
        sys.exit(1)

    print(f"User ID: {user_id}")

    # ── Fetch following list ──────────────────────────────────────────────────
    print("\nFetching your following list (this may take a moment)...")
    try:
        following = get_following(session, user_id)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)

    print(f"\nTotal accounts you follow : {len(following)}")

    # ── Save following list to file ───────────────────────────────────────────
    os.makedirs("data", exist_ok=True)
    following_file = "data/following.json"
    with open(following_file, "w", encoding="utf-8") as f:
        json.dump(following, f, indent=2, ensure_ascii=False)
    print(f"Following list saved to {following_file}")

    # ── Apply whitelist ───────────────────────────────────────────────────────
    targets = [
        u for u in following
        if u.get("username", "").lower().strip() not in whitelist
    ]
    kept = len(following) - len(targets)
    print(f"Accounts to unfollow      : {len(targets)}")
    print(f"Accounts to keep          : {kept}  (whitelisted)")

    if not targets:
        print("\nNothing to unfollow — you only follow whitelisted accounts!")
        return

    # ── Dry-run mode ──────────────────────────────────────────────────────────
    if args.dry_run:
        print("\n--- DRY RUN: accounts that WOULD be unfollowed ---\n")
        for u in targets:
            priv_tag = "  [private]" if u.get("is_private") else ""
            print(f"  @{u.get('username', '?')}{priv_tag}")
        print(f"\nTotal: {len(targets)} accounts would be unfollowed.")
        print("(No changes were made — remove --dry-run to actually unfollow.)")
        return

    # ── Live confirmation ─────────────────────────────────────────────────────
    print(f"\nAbout to unfollow {len(targets)} accounts.")
    confirm = input("Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Aborted — no changes made.")
        return

    csrf = get_csrf_token(session)

    unfollowed = 0
    failed     = 0

    for i, user in enumerate(targets, 1):
        uid   = str(user.get("pk") or user.get("id", ""))
        uname = user.get("username", "?")
        print(f"[{i:>4}/{len(targets)}] @{uname:<30} ... ", end="", flush=True)

        if unfollow_user(session, uid, uname, csrf):
            print("unfollowed")
            unfollowed += 1
        else:
            print("FAILED")
            failed += 1

        # Human-paced delay to avoid triggering rate limits
        time.sleep(random.uniform(2.0, 4.0))

    print(f"\nDone. Unfollowed {unfollowed}/{len(targets)} accounts.  ({failed} failed.)")


if __name__ == "__main__":
    main()

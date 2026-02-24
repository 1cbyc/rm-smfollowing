#!/usr/bin/env python3
"""
main.py — Orchestration entry point for the Instagram Human-Like Unfollow Bot.

Execution order:
    1.  Load credentials from config/credentials.json
    2.  Log into Instagram via Selenium (ig_login.py)
    3.  Scrape accounts you follow  (get_following.py)
    4.  Apply whitelist filter  (compare.py)
    5.  Show a preview of accounts to unfollow
    6.  Ask user: "Proceed? (y/n)"
    7.  Run unfollow session with auto-pause on rate-limits  (unfollow.py)
    8.  Close the browser cleanly

Usage:
    python3 main.py               # normal run
    python3 main.py --dry-run     # preview only, no unfollows
    python3 main.py --skip-scrape # skip scraping, use existing JSON files

"""

import sys
import json
import argparse
import logging

from src.helpers import log, human_sleep, long_pause
from src.ig_login import login
from src.get_following import get_following
from src.compare import compare, show_preview
from src.unfollow import run_unfollow_session

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

CREDENTIALS_FILE = "config/credentials.json"
OUTPUT_FILE      = "data/not_following_back.json"

BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║        SM Un/Following Bot   (Instagram)                 ║
║   Unfollows everyone except your whitelist (15–20/hr)    ║
╚══════════════════════════════════════════════════════════╝
"""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_credentials() -> dict:
    """Load Instagram credentials from config/credentials.json."""
    try:
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            creds = json.load(f)
        username = creds.get("username", "").strip()
        password = creds.get("password", "").strip()

        if not username or username == "YOUR_INSTAGRAM_USERNAME":
            log.error(
                "Please fill in your Instagram username in config/credentials.json"
            )
            sys.exit(1)
        if not password or password == "YOUR_INSTAGRAM_PASSWORD":
            log.error(
                "Please fill in your Instagram password in config/credentials.json"
            )
            sys.exit(1)

        return creds
    except FileNotFoundError:
        log.error(f"Credentials file not found: {CREDENTIALS_FILE}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON in {CREDENTIALS_FILE}: {e}")
        sys.exit(1)


def load_existing_targets() -> list:
    """
    Load previously saved not_following_back.json if the user chose --skip-scrape.
    """
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            targets = json.load(f)
        log.info(f"Loaded {len(targets)} targets from {OUTPUT_FILE}")
        return targets
    except FileNotFoundError:
        log.error(
            f"{OUTPUT_FILE} not found — you must run a full scrape first "
            "(do not use --skip-scrape on the first run)."
        )
        sys.exit(1)


def ask_user_to_proceed(targets: list) -> bool:
    """
    Show the user the target count and ask whether to proceed with unfollowing.

    Returns True if the user types 'y', False otherwise.
    """
    print(f"\nFound {len(targets)} account(s) to unfollow.")
    try:
        answer = input("Proceed to unfollow? (y/n): ").strip().lower()
        return answer == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Instagram Human-Like Unfollow Bot (Selenium)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be unfollowed without actually unfollowing.",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip follower/following scraping — use existing data JSON files.",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(BANNER)

    args = parse_args()

    if args.dry_run:
        log.info("🔵 DRY-RUN mode enabled — no accounts will be unfollowed.")

    # ── Step 1: Load credentials ──────────────────────────────
    log.info("Loading credentials …")
    credentials = load_credentials()
    username = credentials["username"]

    # ── Step 2: Login ─────────────────────────────────────────
    log.info("Logging into Instagram …")
    driver = login(credentials)

    # Let the page settle after login
    long_pause(5.0, 10.0)

    try:
        if args.skip_scrape:
            # ── Skip scraping — load from disk ─────────────────
            log.info("--skip-scrape flag set. Loading existing data …")
            targets = load_existing_targets()
        else:
            # ── Step 3: Scrape following ───────────────────────
            log.info("=" * 55)
            log.info("STEP 3/3: Scraping accounts you FOLLOW …")
            log.info("=" * 55)
            following = get_following(driver, username)
            long_pause(5.0, 12.0)

            # ── Step 4: Apply whitelist filter ────────────────
            log.info("=" * 55)
            log.info("Applying whitelist filter …")
            log.info("=" * 55)
            targets = compare(following=following)

        # ── Step 6: Preview ───────────────────────────────────
        show_preview(targets)

        if not targets:
            log.info("🎉 Everyone you follow follows you back! Nothing to unfollow.")
            return

        # ── Step 7: Ask to proceed ────────────────────────────
        if not args.dry_run:
            proceed = ask_user_to_proceed(targets)
            if not proceed:
                log.info("Aborted by user. No accounts were unfollowed.")
                return
        else:
            proceed = True

        # ── Step 8: Unfollow session ──────────────────────────
        log.info("=" * 55)
        log.info("Starting unfollow session …")
        log.info("=" * 55)
        stats = run_unfollow_session(driver, targets, dry_run=args.dry_run)

        # ── Final summary ──────────────────────────────────────
        print("\n" + "=" * 55)
        print("  📊  Final Summary")
        print("=" * 55)
        print(f"  ✅  Unfollowed:        {stats['unfollowed']}")
        print(f"  🔒  Skipped (private): {stats['skipped_private']}")
        print(f"  ℹ️   Not following:     {stats['not_following']}")
        print(f"  ❌  Errors:            {stats['errors']}")
        print("=" * 55 + "\n")

    except KeyboardInterrupt:
        log.info("\nBot interrupted by user (Ctrl+C). Closing browser …")

    finally:
        # ── Step 9: Clean browser close ───────────────────────
        try:
            driver.quit()
            log.info("Browser closed cleanly. 👋")
        except Exception:
            pass


if __name__ == "__main__":
    main()

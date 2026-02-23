"""
compare.py — Compare following vs. followers to find non-followers.

Logic:
    not_following_back = following_set - followers_set - whitelist_set

Loads:
  data/following.json     → accounts you follow
  data/followers.json     → accounts that follow you
  config/whitelist.json   → accounts to never unfollow

Saves:
  data/not_following_back.json  → targets for unfollowing
"""

import json
import logging

from src.helpers import log

FOLLOWING_FILE        = "data/following.json"
FOLLOWERS_FILE        = "data/followers.json"
WHITELIST_FILE        = "config/whitelist.json"
OUTPUT_FILE           = "data/not_following_back.json"


def load_json_list(filepath: str) -> list:
    """Load a JSON file that contains a list. Returns [] on error."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        # whitelist.json stores {"whitelist": [...]}
        if isinstance(data, dict):
            return data.get("whitelist", [])
        return []
    except FileNotFoundError:
        log.warning(f"File not found: {filepath} — treating as empty list.")
        return []
    except json.JSONDecodeError as e:
        log.error(f"JSON decode error in {filepath}: {e}")
        return []


def compare(
    following: list = None,
    followers: list = None,
) -> list:
    """
    Compute the list of accounts you follow that do NOT follow you back,
    excluding any accounts in the whitelist.

    Args:
        following: Optional pre-loaded following list.
                   If None, loads from data/following.json.
        followers: Optional pre-loaded followers list.
                   If None, loads from data/followers.json.

    Returns:
        Sorted list of usernames to unfollow.
    """
    # ── Load data ──────────────────────────────────────────────
    if following is None:
        following = load_json_list(FOLLOWING_FILE)
    if followers is None:
        followers = load_json_list(FOLLOWERS_FILE)

    whitelist_data = load_json_list(WHITELIST_FILE)

    # ── Normalise to lowercase sets for reliable comparison ───
    following_set  = {u.lower().strip() for u in following if u}
    followers_set  = {u.lower().strip() for u in followers if u}
    whitelist_set  = {u.lower().strip() for u in whitelist_data if u}

    log.info(f"You follow:           {len(following_set):>6} accounts")
    log.info(f"Followers:            {len(followers_set):>6} accounts")
    log.info(f"Whitelist:            {len(whitelist_set):>6} accounts")

    # ── Core set logic ─────────────────────────────────────────
    not_following_back = following_set - followers_set - whitelist_set

    result = sorted(not_following_back)
    log.info(f"Not following back:   {len(result):>6} accounts  (after whitelist exclusion)")

    # ── Save results ───────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    log.info(f"Saved → {OUTPUT_FILE}")

    return result


def show_preview(not_following_back: list, limit: int = 30) -> None:
    """
    Print a formatted preview table of users to be unfollowed.

    Args:
        not_following_back: List of usernames.
        limit:              Max rows to show before truncating.
    """
    total = len(not_following_back)
    print("\n" + "=" * 55)
    print(f"  👥  Accounts to Unfollow ({total} total)")
    print("=" * 55)

    display = not_following_back[:limit]
    for i, username in enumerate(display, start=1):
        print(f"  {i:>4}.  @{username}")

    if total > limit:
        print(f"\n  … and {total - limit} more (see {OUTPUT_FILE})")

    print("=" * 55 + "\n")

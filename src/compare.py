"""
compare.py — Compare following list against whitelist to find unfollow targets.

Logic:
    to_unfollow = following_set - whitelist_set

    Unfollows EVERYONE you follow, regardless of whether they follow you back,
    EXCEPT accounts listed in the whitelist.

Loads:
  data/following.json     → accounts you follow
  config/whitelist.json   → accounts to never unfollow

Saves:
  data/not_following_back.json  → targets for unfollowing
"""

import json
import logging

from src.helpers import log

FOLLOWING_FILE        = "data/following.json"
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
    Compute the list of accounts to unfollow.

    Unfollows EVERYONE you follow except accounts in the whitelist,
    regardless of whether they follow you back.

    Args:
        following: Optional pre-loaded following list.
                   If None, loads from data/following.json.
        followers: Ignored. Kept for backwards-compatibility.

    Returns:
        Sorted list of usernames to unfollow.
    """
    # ── Load data ──────────────────────────────────────────────
    if following is None:
        following = load_json_list(FOLLOWING_FILE)

    whitelist_data = load_json_list(WHITELIST_FILE)

    # ── Normalise to lowercase sets for reliable comparison ───
    following_set = {u.lower().strip() for u in following if u}
    whitelist_set = {u.lower().strip() for u in whitelist_data if u}

    log.info(f"You follow:           {len(following_set):>6} accounts")
    log.info(f"Whitelist:            {len(whitelist_set):>6} accounts (will be kept)")

    # ── Core set logic ─────────────────────────────────────────
    # Unfollow everyone except whitelisted accounts
    to_unfollow = following_set - whitelist_set

    result = sorted(to_unfollow)
    log.info(f"To unfollow:          {len(result):>6} accounts  (after whitelist exclusion)")

    # ── Save results ───────────────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    log.info(f"Saved → {OUTPUT_FILE}")

    return result


def show_preview(targets: list, limit: int = 30) -> None:
    """
    Print a formatted preview table of users to be unfollowed.

    Args:
        targets: List of usernames to unfollow.
        limit:   Max rows to show before truncating.
    """
    total = len(targets)
    print("\n" + "=" * 55)
    print(f"  👥  Accounts to Unfollow ({total} total)")
    print("=" * 55)

    display = targets[:limit]
    for i, username in enumerate(display, start=1):
        print(f"  {i:>4}.  @{username}")

    if total > limit:
        print(f"\n  … and {total - limit} more (see {OUTPUT_FILE})")

    print("=" * 55 + "\n")

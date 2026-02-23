"""
unfollow.py — Core Unfollow Engine for the Instagram Unfollow Bot.

Features:
  - Visits each user's profile page
  - Detects and SKIPS private accounts
  - Clicks the "Following" button → waits → clicks "Unfollow" in the popup
  - Logs each action to the console
  - Enforces medium-risk speed: ~15–20 unfollows/hour
    (170–240 seconds between each unfollow)
  - Auto-detects Instagram rate-limit phrases on ANY page
  - Auto-pauses 10–20 minutes and then resumes automatically
  - Handles errors gracefully without crashing
"""

import time
import random
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)

from src.helpers import (
    human_sleep,
    brief_pause,
    long_pause,
    human_move_to,
    wait_for_element,
    check_for_rate_limit,
    auto_pause_after_rate_limit,
    random_unfollow_delay,
    log,
)

# ── Limits ────────────────────────────────────────────────────────────────────
# Instagram allows roughly 200 unfollows per day safely. We target 15–20/hr
# which is about 360–480/day if run all day. Keep it under 20/hour.
MAX_UNFOLLOWS_PER_HOUR = 20

# ── Unfollow button detection constants ─────────────────────────────────────
# Instagram uses aria-label and text to render the Following button.
_FOLLOWING_BTN_SELECTORS = [
    "//button[.//div[text()='Following']]",
    "//button[@aria-label='Following']",
    "//button[text()='Following']",
    "//button[contains(@class, '_acan') and .//span[text()='Following']]",
]

_UNFOLLOW_CONFIRM_SELECTORS = [
    "//button[text()='Unfollow']",
    "//button[contains(text(),'Unfollow')]",
    "//div[@role='dialog']//button[.//span[text()='Unfollow']]",
]

_PRIVATE_INDICATORS = [
    "This account is private",
    "Follow to see their photos and videos",
    "Private Account",
]

_LOCK_ICON_ALT = "This Account is Private"


def _is_private_account(driver: webdriver.Chrome) -> bool:
    """
    Return True if the currently opened profile is a private account.
    Checks both page text and the lock icon alt-text.
    """
    try:
        page_source = driver.page_source
        for phrase in _PRIVATE_INDICATORS:
            if phrase.lower() in page_source.lower():
                return True
        # Check for lock icon
        lock_icons = driver.find_elements(
            By.XPATH, f"//img[contains(@alt, 'Private')]"
        )
        if lock_icons:
            return True
    except Exception:
        pass
    return False


def _click_following_button(driver: webdriver.Chrome) -> bool:
    """
    Find and click the blue "Following" button on a user's profile.

    Returns True if clicked successfully, False otherwise.
    """
    for selector in _FOLLOWING_BTN_SELECTORS:
        try:
            btn = wait_for_element(driver, By.XPATH, selector, timeout=8)
            human_move_to(driver, btn)
            brief_pause()
            btn.click()
            log.debug("Clicked 'Following' button.")
            return True
        except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
            continue
    return False


def _confirm_unfollow(driver: webdriver.Chrome) -> bool:
    """
    After clicking "Following", a confirmation dialog appears.
    Find and click the "Unfollow" button in that dialog.

    Returns True if confirmed successfully, False otherwise.
    """
    human_sleep(1.0, 2.5)  # Wait for the dialog to animate in

    for selector in _UNFOLLOW_CONFIRM_SELECTORS:
        try:
            confirm_btn = wait_for_element(driver, By.XPATH, selector, timeout=8)
            human_move_to(driver, confirm_btn)
            brief_pause()
            confirm_btn.click()
            log.debug("Clicked 'Unfollow' confirm button.")
            return True
        except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
            continue
    return False


def unfollow_user(driver: webdriver.Chrome, username: str) -> str:
    """
    Attempt to unfollow a single Instagram user.

    Args:
        driver:   Authenticated WebDriver.
        username: The Instagram username to unfollow.

    Returns:
        One of: 'unfollowed', 'skipped_private', 'not_following', 'error'
    """
    profile_url = f"https://www.instagram.com/{username}/"

    try:
        log.info(f"Visiting @{username} …")
        driver.get(profile_url)
        human_sleep(2.5, 5.0)

        # ── Check for rate-limit phrases ─────────────────────
        if check_for_rate_limit(driver):
            auto_pause_after_rate_limit()
            # Retry the profile after pausing
            driver.get(profile_url)
            human_sleep(3.0, 5.5)

        # ── Skip private accounts ─────────────────────────────
        if _is_private_account(driver):
            log.info(f"  ⚠️  @{username} is private — skipping.")
            return "skipped_private"

        # ── Check we are actually following this person ────────
        # If the button says "Follow" instead of "Following", skip.
        page_src = driver.page_source
        if ">Follow<" in page_src and ">Following<" not in page_src:
            log.info(f"  ℹ️  @{username} — not currently following. Skipping.")
            return "not_following"

        # ── Click "Following" button ──────────────────────────
        human_sleep(1.0, 2.5)
        clicked = _click_following_button(driver)
        if not clicked:
            log.warning(f"  ⚠️  Could not find 'Following' button for @{username}.")
            return "error"

        # ── Confirm unfollow in the popup dialog ──────────────
        confirmed = _confirm_unfollow(driver)
        if not confirmed:
            log.warning(f"  ⚠️  Could not confirm unfollow for @{username}.")
            return "error"

        # ── Second rate-limit check after action ──────────────
        human_sleep(1.5, 3.0)
        if check_for_rate_limit(driver):
            auto_pause_after_rate_limit()

        log.info(f"  ✅  Unfollowed @{username}")
        return "unfollowed"

    except Exception as exc:
        log.error(f"  ❌  Error unfollowing @{username}: {exc}")
        return "error"


def run_unfollow_session(
    driver: webdriver.Chrome,
    targets: list,
    dry_run: bool = False,
) -> dict:
    """
    Run through the list of target usernames, unfollowing each one
    while enforcing human-like pacing and auto-pause on rate limits.

    Args:
        driver:   Authenticated WebDriver.
        targets:  List of usernames to unfollow.
        dry_run:  If True, prints what WOULD be unfollowed without acting.

    Returns:
        Summary dict: {unfollowed, skipped_private, not_following, errors}
    """
    stats = {
        "unfollowed": 0,
        "skipped_private": 0,
        "not_following": 0,
        "errors": 0,
    }

    if not targets:
        log.info("No targets to unfollow.")
        return stats

    total = len(targets)
    log.info(f"Starting unfollow session — {total} targets queued.")

    # Track per-hour rate
    hour_start = time.time()
    hour_unfollow_count = 0

    for index, username in enumerate(targets, start=1):
        # ── Rate limit enforcement: 20 per hour max ───────────
        elapsed_hours = (time.time() - hour_start) / 3600.0
        if elapsed_hours >= 1.0:
            # Reset the hourly counter every 60 minutes
            hour_start = time.time()
            hour_unfollow_count = 0
            log.info("Hourly window reset — continuing …")

        if hour_unfollow_count >= MAX_UNFOLLOWS_PER_HOUR:
            wait_seconds = 3600 - int(time.time() - hour_start)
            wait_seconds = max(60, wait_seconds)
            log.info(
                f"Reached {MAX_UNFOLLOWS_PER_HOUR} unfollows this hour. "
                f"Waiting {wait_seconds // 60} min before continuing …"
            )
            # Count down in 1-minute blocks
            for _ in range(wait_seconds // 60):
                log.info(f"  ⏳ {(wait_seconds - _ * 60) // 60} min remaining …")
                time.sleep(60)
            # Reset counters
            hour_start = time.time()
            hour_unfollow_count = 0

        log.info(f"[{index}/{total}] Processing @{username} …")

        if dry_run:
            log.info(f"  [DRY RUN] Would unfollow: @{username}")
            stats["unfollowed"] += 1
            time.sleep(random.uniform(0.5, 1.5))
            continue

        # ── Perform the actual unfollow ────────────────────────
        result = unfollow_user(driver, username)

        if result == "unfollowed":
            stats["unfollowed"] += 1
            hour_unfollow_count += 1
        elif result == "skipped_private":
            stats["skipped_private"] += 1
        elif result == "not_following":
            stats["not_following"] += 1
        else:
            stats["errors"] += 1

        # ── Human-paced delay between unfollows ───────────────
        # Only add delay if we actually performed an unfollow attempt
        if result in ("unfollowed",):
            random_unfollow_delay()  # 170–240 seconds
        elif result in ("error",):
            # Shorter backoff on errors (~60–120 seconds)
            backoff = random.randint(60, 120)
            log.info(f"  Error back-off: sleeping {backoff}s …")
            time.sleep(backoff)
        else:
            # Skipped — tiny pause before next iteration
            brief_pause()

    # ── Session summary ────────────────────────────────────────
    log.info("=" * 50)
    log.info(f"Session complete.")
    log.info(f"  Unfollowed:      {stats['unfollowed']}")
    log.info(f"  Skipped(private):{stats['skipped_private']}")
    log.info(f"  Not following:   {stats['not_following']}")
    log.info(f"  Errors:          {stats['errors']}")
    log.info("=" * 50)

    return stats

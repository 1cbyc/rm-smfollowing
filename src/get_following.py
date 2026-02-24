"""
get_following.py — Scrape the accounts you follow from your Instagram profile modal.

Method:
  1. Navigate to https://www.instagram.com/<username>/
  2. Read the REAL expected following count from the page header
  3. Click the "Following" link to open the list modal
  4. Wait for the scrollable modal container (div._aano)
  5. Scroll the modal continuously until scrollTop stabilises (no new height)
  6. Extract every username from <span><a href="/username/"> links inside the modal
  7. Cross-check scraped count against the expected count and retry if too low
  8. Save results to data/following.json

This completely replaces any Access Tool approach.
"""

import json
import time
import random
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

from src.helpers import (
    human_sleep,
    brief_pause,
    check_for_rate_limit,
    auto_pause_after_rate_limit,
    log,
)

FOLLOWING_DATA_FILE = "data/following.json"

# Maximum scroll rounds before giving up on a single pass
MAX_SCROLL_ROUNDS = 200

# How many times to retry the whole scrape if count is too low
MAX_RETRIES = 2

# Threshold: scraped count must be >= this fraction of expected to be accepted
COUNT_THRESHOLD = 0.90


def _js_click(driver: webdriver.Chrome, element) -> None:
    """Click via JavaScript to avoid ChromeDriver native event crashes on macOS."""
    driver.execute_script("arguments[0].click();", element)
    time.sleep(random.uniform(0.3, 0.8))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_expected_count(driver: webdriver.Chrome) -> int:
    """
    Read the expected following count displayed on the profile page header.
    Returns 0 if the count cannot be determined.
    """
    try:
        # Instagram renders counts in <span> tags inside <li> items.
        # The text looks like "342 following" or just "342" with aria context.
        count_elements = driver.find_elements(
            By.XPATH,
            "//a[contains(@href,'/following/')]//span[@title or text()]",
        )
        for el in count_elements:
            raw = el.get_attribute("title") or el.text
            raw = raw.replace(",", "").replace(".", "").strip()
            if raw.isdigit():
                return int(raw)

        # Fallback: search page source for pattern like >342<
        match = re.search(r'"edge_follow":\{"count":(\d+)\}', driver.page_source)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return 0


def _open_modal(driver: webdriver.Chrome, username: str) -> None:
    """
    Open the following list by:
      1. First trying direct URL navigation to /<username>/following/
         (most reliable — no click needed)
      2. Falling back to clicking the Following link on the profile page
    """
    # Strategy 1: Direct URL to following list page
    following_url = f"https://www.instagram.com/{username}/following/"
    log.info(f"Navigating directly to: {following_url}")
    driver.get(following_url)
    human_sleep(3.5, 5.5)

    if check_for_rate_limit(driver):
        auto_pause_after_rate_limit()
        driver.get(following_url)
        human_sleep(3.5, 5.5)

    # Check if we landed on the following page (has a dialog or list)
    current_url = driver.current_url
    log.info(f"Current URL after navigation: {current_url}")

    # If Instagram redirected back to profile (not signed in or URL unsupported),
    # fall back to clicking the link on the profile page.
    if "/following" not in current_url:
        log.warning("Direct following URL redirected — falling back to profile page click ...")
        profile_url = f"https://www.instagram.com/{username}/"
        driver.get(profile_url)
        human_sleep(3.5, 6.0)

        # Try multiple selectors for the following link or button
        clicked = False
        for xpath in [
            "//a[contains(@href,'/following/')]",
            "//a[contains(@href,'following')]",
            "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'following')]/ancestor::a",
            "//div[contains(@role,'button') and .//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'following')]]",
        ]:
            try:
                el = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                time.sleep(random.uniform(0.5, 1.0))
                _js_click(driver, el)
                log.info(f"Clicked Following via: {xpath}")
                clicked = True
                break
            except TimeoutException:
                continue

        if not clicked:
            log.error("Could not find or click the Following link on your profile.")
            return

    human_sleep(2.5, 4.5)



def _get_modal(driver: webdriver.Chrome):
    """
    Wait for and return the scrollable modal container element.
    Instagram uses div._aano as the inner scroll pane inside the dialog.
    Falls back to the role=dialog element itself if _aano is not found.
    """
    try:
        modal = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div._aano"))
        )
        log.info("Modal located via div._aano")
        return modal
    except TimeoutException:
        pass

    try:
        modal = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
        log.info("Modal located via role=dialog fallback")
        return modal
    except TimeoutException:
        log.error("Could not locate the following list modal.")
        return None


def _scroll_modal_to_end(driver: webdriver.Chrome, modal) -> None:
    """
    Scroll the modal container until scrollTop no longer increases.
    Uses JavaScript scrollTop manipulation for reliable modal scrolling.
    Each round sleeps a random human-like delay.
    """
    last_height = -1
    stale_rounds = 0

    for _ in range(MAX_SCROLL_ROUNDS):
        # Scroll to the bottom of the modal
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight", modal
        )
        time.sleep(random.uniform(1.2, 2.2))

        try:
            new_height = driver.execute_script(
                "return arguments[0].scrollTop", modal
            )
        except StaleElementReferenceException:
            log.warning("Modal element went stale during scroll — re-locating ...")
            modal = _get_modal(driver)
            if modal is None:
                break
            continue

        if new_height == last_height:
            stale_rounds += 1
            if stale_rounds >= 3:
                log.info("Scroll position stable — modal fully loaded.")
                break
        else:
            stale_rounds = 0

        last_height = new_height

        if check_for_rate_limit(driver):
            auto_pause_after_rate_limit()


def _extract_usernames(driver: webdriver.Chrome) -> list:
    """
    Extract all usernames visible inside the followers/following modal.

    Uses JavaScript to collect all anchor hrefs at once — more reliable than
    XPath-based element scanning because it avoids stale element exceptions
    and works regardless of how Instagram nests the <a> tags in the current
    React render (which changes between app versions).
    """
    seen = set()
    usernames = []

    # Strategy 1: JS-based — collect all hrefs inside the dialog in one call.
    # This is the fastest and most stable approach.
    try:
        hrefs = driver.execute_script("""
            var dialog = document.querySelector('[role="dialog"]');
            if (!dialog) return [];
            var anchors = dialog.querySelectorAll('a[href]');
            var hrefs = [];
            anchors.forEach(function(a) { hrefs.push(a.href); });
            return hrefs;
        """)
        for href in (hrefs or []):
            # href: https://www.instagram.com/username/ or /username/
            parts = [p for p in href.replace("https://www.instagram.com", "").split("/") if p]
            if len(parts) == 1:
                uname = parts[0]
                if uname and uname not in ("explore", "accounts", "p", "reels", "stories") and uname not in seen:
                    seen.add(uname)
                    usernames.append(uname)
    except Exception as e:
        log.warning(f"JS extraction failed: {e} — falling back to XPath.")

    # Strategy 2: XPath fallback — broader selector without requiring span parent.
    if not usernames:
        try:
            elements = driver.find_elements(
                By.XPATH, "//div[@role='dialog']//a[@href]"
            )
            for el in elements:
                try:
                    href = el.get_attribute("href") or ""
                    parts = [p for p in href.replace("https://www.instagram.com", "").split("/") if p]
                    if len(parts) == 1:
                        uname = parts[0]
                        if uname and uname not in ("explore", "accounts", "p", "reels", "stories") and uname not in seen:
                            seen.add(uname)
                            usernames.append(uname)
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            log.warning(f"XPath extraction failed: {e}")

    log.info(f"Extracted {len(usernames)} unique usernames from modal.")
    return usernames


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_following(driver: webdriver.Chrome, username: str) -> list:
    """
    Full scrape of the Following list, with count verification and retry.

    Args:
        driver:   Authenticated Selenium WebDriver.
        username: Your Instagram username.

    Returns:
        Deduplicated list of following usernames.
    """
    for attempt in range(1, MAX_RETRIES + 2):
        log.info(f"Following scrape — attempt {attempt} ...")

        # Open the profile page and click Following
        _open_modal(driver, username)

        # Read expected count NOW (before the modal replaces the header)
        expected_count = _read_expected_count(driver)
        if expected_count:
            log.info(f"Expected Following count : {expected_count}")
        else:
            log.warning("Could not read expected following count from profile.")

        # Locate the modal
        modal = _get_modal(driver)
        if modal is None:
            log.error("Modal not found — skipping this attempt.")
            continue

        # Scroll until all users are loaded
        _scroll_modal_to_end(driver, modal)

        # DOM diagnostic probe — log what the page actually contains
        try:
            diag = driver.execute_script("""
                var d = {};
                d.url = window.location.href;
                d.dialogFound = !!document.querySelector('[role="dialog"]');
                var dialog = document.querySelector('[role="dialog"]');
                d.aTagsInDialog = dialog ? dialog.querySelectorAll('a').length : -1;
                d.aHrefTagsInDialog = dialog ? dialog.querySelectorAll('a[href]').length : -1;
                d.spanTagsInDialog = dialog ? dialog.querySelectorAll('span').length : -1;
                d.divAanoFound = !!document.querySelector('div._aano');
                d.totalATags = document.querySelectorAll('a[href]').length;
                // Sample first 3 a[href] on whole page
                var allA = document.querySelectorAll('a[href]');
                d.sampleHrefs = [];
                for(var i=0; i < Math.min(3, allA.length); i++) d.sampleHrefs.push(allA[i].href);
                return d;
            """)
            log.info(f"DOM probe: {diag}")
        except Exception as e:
            log.warning(f"DOM probe failed: {e}")

        # Extract usernames
        following = _extract_usernames(driver)
        scraped_count = len(following)
        log.info(f"Scraped Following count  : {scraped_count}")

        # Count verification
        if expected_count and scraped_count < int(expected_count * COUNT_THRESHOLD):
            log.warning(
                f"Scraped count ({scraped_count}) is below "
                f"{int(COUNT_THRESHOLD * 100)}% of expected ({expected_count}). "
                f"Retrying ..."
            )
            if attempt <= MAX_RETRIES:
                human_sleep(5.0, 10.0)
                continue
            else:
                log.warning("Max retries reached — using best result obtained.")
        else:
            log.info("Count verification passed.")

        return following

    return []


def save_following(following: list) -> None:
    """Persist the following list to data/following.json."""
    with open(FOLLOWING_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(following, f, indent=2, ensure_ascii=False)
    log.info(f"Saved {len(following)} following users -> {FOLLOWING_DATA_FILE}")


def get_following(driver: webdriver.Chrome, username: str) -> list:
    """
    Public entry point: scrape and save the following list.

    Args:
        driver:   Authenticated WebDriver.
        username: Your Instagram username.

    Returns:
        List of following usernames.
    """
    following = scrape_following(driver, username)
    save_following(following)
    return following

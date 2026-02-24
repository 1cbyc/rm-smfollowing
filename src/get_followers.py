"""
get_followers.py — Scrape the accounts that follow you from your Instagram profile modal.

Method:
  1. Navigate to https://www.instagram.com/<username>/
  2. Read the REAL expected followers count from the page header
  3. Click the "Followers" link to open the list modal
  4. Wait for the scrollable modal container (div._aano)
  5. Scroll the modal continuously until scrollTop stabilises (no new height)
  6. Extract every username from <span><a href="/username/"> links inside the modal
  7. Cross-check scraped count against the expected count and retry if too low
  8. Save results to data/followers.json

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

FOLLOWERS_DATA_FILE = "data/followers.json"

MAX_SCROLL_ROUNDS = 200
MAX_RETRIES = 2
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
    Read the expected followers count displayed on the profile page header.
    Returns 0 if the count cannot be determined.
    """
    try:
        count_elements = driver.find_elements(
            By.XPATH,
            "//a[contains(@href,'/followers/')]//span[@title or text()]",
        )
        for el in count_elements:
            raw = el.get_attribute("title") or el.text
            raw = raw.replace(",", "").replace(".", "").strip()
            if raw.isdigit():
                return int(raw)

        # Fallback: parse the JSON embedded in the page source
        match = re.search(r'"edge_followed_by":\{"count":(\d+)\}', driver.page_source)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return 0


def _open_modal(driver: webdriver.Chrome, username: str) -> None:
    """
    Navigate to the user's profile and click the Followers link to open the modal.
    """
    profile_url = f"https://www.instagram.com/{username}/"
    log.info(f"Navigating to profile: {profile_url}")
    driver.get(profile_url)
    human_sleep(3.5, 6.0)

    if check_for_rate_limit(driver):
        auto_pause_after_rate_limit()
        driver.get(profile_url)
        human_sleep(3.5, 6.0)

    log.info("Clicking Followers link ...")
    try:
        followers_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//a[contains(@href,'/followers/')]")
            )
        )
        time.sleep(random.uniform(0.5, 1.0))
        _js_click(driver, followers_link)
    except TimeoutException:
        try:
            followers_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//li[.//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'follower')]]")
                )
            )
            _js_click(driver, followers_link)
        except TimeoutException:
            log.error("Could not find or click the Followers link on your profile.")
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
        log.error("Could not locate the followers list modal.")
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

def scrape_followers(driver: webdriver.Chrome, username: str) -> list:
    """
    Full scrape of the Followers list, with count verification and retry.

    Args:
        driver:   Authenticated Selenium WebDriver.
        username: Your Instagram username.

    Returns:
        Deduplicated list of follower usernames.
    """
    for attempt in range(1, MAX_RETRIES + 2):
        log.info(f"Followers scrape — attempt {attempt} ...")

        _open_modal(driver, username)

        expected_count = _read_expected_count(driver)
        if expected_count:
            log.info(f"Expected Followers count : {expected_count}")
        else:
            log.warning("Could not read expected followers count from profile.")

        modal = _get_modal(driver)
        if modal is None:
            log.error("Modal not found — skipping this attempt.")
            continue

        _scroll_modal_to_end(driver, modal)

        followers = _extract_usernames(driver)
        scraped_count = len(followers)
        log.info(f"Scraped Followers count  : {scraped_count}")

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

        return followers

    return []


def save_followers(followers: list) -> None:
    """Persist the followers list to data/followers.json."""
    with open(FOLLOWERS_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(followers, f, indent=2, ensure_ascii=False)
    log.info(f"Saved {len(followers)} followers -> {FOLLOWERS_DATA_FILE}")


def get_followers(driver: webdriver.Chrome, username: str) -> list:
    """
    Public entry point: scrape and save the followers list.

    Args:
        driver:   Authenticated WebDriver.
        username: Your Instagram username.

    Returns:
        List of follower usernames.
    """
    followers = scrape_followers(driver, username)
    save_followers(followers)
    return followers

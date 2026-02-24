"""
get_following.py — Scrape the list of accounts you follow on Instagram.

Strategy:
  - Navigate to your own profile page
  - Click the "Following" link to open the following modal
  - Scroll the modal until all usernames are loaded (infinite-scroll pattern)
  - Extract every username from the list items
  - Save results to data/following.json

Note: Instagram loads users lazily; we must keep scrolling until the
      bottom is reached (i.e., the count stops growing).
"""

import json
import time
import random
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)

from src.helpers import (
    human_sleep,
    brief_pause,
    long_pause,
    smooth_scroll_element,
    wait_for_element,
    check_for_rate_limit,
    auto_pause_after_rate_limit,
    log,
)

FOLLOWING_DATA_FILE = "data/following.json"


def _get_username_from_driver(driver: webdriver.Chrome) -> str:
    """
    Extract the currently logged-in username from the Instagram page URL
    or from the profile avatar link in the nav bar.
    """
    # Try clicking on the profile link in the sidebar — it contains the username in href
    try:
        profile_links = driver.find_elements(
            By.XPATH,
            "//a[contains(@href, '/') and .//span[contains(@class,'_aa8j')]]",
        )
        for link in profile_links:
            href = link.get_attribute("href") or ""
            if href.count("/") == 4 and "accounts" not in href and "explore" not in href:
                username = href.rstrip("/").split("/")[-1]
                if username:
                    return username
    except Exception:
        pass

    # Fallback: find username via the "Edit profile" button on the profile page
    try:
        # Navigate to feed and find profile link in nav
        driver.get("https://www.instagram.com/")
        human_sleep(2, 4)
        links = driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            href = link.get_attribute("href") or ""
            if href.endswith("/?hl=en") or not href:
                continue
            parts = [p for p in href.split("/") if p]
            if len(parts) == 1 and "instagram.com" not in parts[0]:
                return parts[0]
    except Exception:
        pass

    raise RuntimeError(
        "Could not determine your Instagram username automatically. "
        "Please verify you are logged in."
    )


def scrape_following(driver: webdriver.Chrome, username: str) -> list:
    """
    Scrape every username in your Following list.

    Args:
        driver:   Authenticated Selenium WebDriver.
        username: Your Instagram username (e.g. 'johndoe').

    Returns:
        List of usernames (strings) you follow.
    """
    profile_url = f"https://www.instagram.com/{username}/"
    following_usernames = []

    log.info(f"Navigating to profile: {profile_url}")
    driver.get(profile_url)
    human_sleep(3.0, 5.5)

    # ── Check for rate-limit on page load ────────────────────
    if check_for_rate_limit(driver):
        auto_pause_after_rate_limit()
        driver.get(profile_url)
        human_sleep(3.0, 5.5)

    # ── Click the "Following" count link to open the modal ───
    log.info("Clicking 'Following' link to open modal …")
    try:
        following_link = wait_for_element(
            driver,
            By.XPATH,
            "//a[contains(@href, '/following/')]",
            timeout=15,
        )
        brief_pause()
        following_link.click()
    except TimeoutException:
        # Some profiles render a different structure — try the text-based approach
        try:
            following_link = wait_for_element(
                driver,
                By.XPATH,
                "//li[.//span[contains(text(),'following')]]//a",
                timeout=10,
            )
            following_link.click()
        except TimeoutException:
            log.error("Could not find the 'Following' button on your profile page.")
            return []

    human_sleep(2.5, 5.0)

    # ── Locate the scrollable modal container ────────────────
    log.info("Locating the following list modal …")
    try:
        # The modal dialog is a role=dialog element
        modal = wait_for_element(
            driver,
            By.XPATH,
            "//div[@role='dialog']//div[contains(@class,'_aano') or @style]",
            timeout=15,
        )
    except TimeoutException:
        # Fallback: grab any scrollable div inside the dialog
        try:
            modal = wait_for_element(
                driver,
                By.XPATH,
                "//div[@role='dialog']",
                timeout=10,
            )
        except TimeoutException:
            log.error("Could not find the following modal.")
            return []

    # ── Scroll until no new users appear ─────────────────────
    log.info("Scrolling the following modal to load all users …")
    last_count = 0
    stale_rounds = 0  # How many rounds without new users

    while True:
        # Collect usernames currently visible
        try:
            user_items = driver.find_elements(
                By.XPATH,
                "//div[@role='dialog']//a[contains(@href, '/') and not(contains(@href,'#'))]",
            )
            current_usernames = set()
            for item in user_items:
                href = item.get_attribute("href") or ""
                parts = [p for p in href.replace("https://www.instagram.com", "").split("/") if p]
                if len(parts) == 1:
                    current_usernames.add(parts[0])
        except StaleElementReferenceException:
            current_usernames = set()

        following_usernames = list(set(following_usernames) | current_usernames)
        current_count = len(following_usernames)

        log.info(f"  Loaded {current_count} following users so far …")

        if current_count == last_count:
            stale_rounds += 1
            if stale_rounds >= 4:
                # No new users after 4 scroll attempts — likely reached the end
                log.info("No new users after repeated scrolling. Assuming all loaded.")
                break
        else:
            stale_rounds = 0

        last_count = current_count

        # ── Scroll modal down ─────────────────────────────────
        smooth_scroll_element(driver, modal, pixels=random.randint(600, 1200))
        human_sleep(1.8, 3.5)  # Wait for new users to lazy-load

        # Check for rate limiting mid-scroll
        if check_for_rate_limit(driver):
            auto_pause_after_rate_limit()

    log.info(f"✅ Scraped {len(following_usernames)} accounts you follow.")
    return following_usernames


def save_following(following_usernames: list) -> None:
    """Save the following list to data/following.json."""
    with open(FOLLOWING_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(following_usernames, f, indent=2, ensure_ascii=False)
    log.info(f"Saved following list → {FOLLOWING_DATA_FILE}")


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

"""
get_followers.py — Scrape the list of accounts that follow you on Instagram.

Strategy:
  - Navigate to your own profile page
  - Click the "Followers" link to open the followers modal
  - Scroll the modal until all usernames are loaded
  - Extract every username from the list items
  - Save results to data/followers.json

This module mirrors get_following.py but targets the Followers modal.
"""

import json
import random
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
)

from src.helpers import (
    human_sleep,
    brief_pause,
    smooth_scroll_element,
    wait_for_element,
    check_for_rate_limit,
    auto_pause_after_rate_limit,
    log,
)

FOLLOWERS_DATA_FILE = "data/followers.json"


def scrape_followers(driver: webdriver.Chrome, username: str) -> list:
    """
    Scrape every username in your Followers list.

    Args:
        driver:   Authenticated Selenium WebDriver.
        username: Your Instagram username.

    Returns:
        List of usernames (strings) who follow you.
    """
    profile_url = f"https://www.instagram.com/{username}/"
    followers_usernames = []

    log.info(f"Navigating to profile: {profile_url}")
    driver.get(profile_url)
    human_sleep(3.5, 6.0)

    # ── Check for rate-limit on page load ─────────────────────
    if check_for_rate_limit(driver):
        auto_pause_after_rate_limit()
        driver.get(profile_url)
        human_sleep(3.0, 5.5)

    # ── Click the "Followers" count link to open the modal ────
    log.info("Clicking 'Followers' link to open modal …")
    try:
        followers_link = wait_for_element(
            driver,
            By.XPATH,
            "//a[contains(@href, '/followers/')]",
            timeout=15,
        )
        brief_pause()
        followers_link.click()
    except TimeoutException:
        try:
            followers_link = wait_for_element(
                driver,
                By.XPATH,
                "//li[.//span[contains(text(),'follower')]]//a",
                timeout=10,
            )
            followers_link.click()
        except TimeoutException:
            log.error("Could not find the 'Followers' button on your profile page.")
            return []

    human_sleep(2.5, 5.0)

    # ── Locate the scrollable modal container ─────────────────
    log.info("Locating the followers list modal …")
    try:
        modal = wait_for_element(
            driver,
            By.XPATH,
            "//div[@role='dialog']//div[contains(@class,'_aano') or @style]",
            timeout=15,
        )
    except TimeoutException:
        try:
            modal = wait_for_element(
                driver,
                By.XPATH,
                "//div[@role='dialog']",
                timeout=10,
            )
        except TimeoutException:
            log.error("Could not find the followers modal.")
            return []

    # ── Scroll until no new users appear ──────────────────────
    log.info("Scrolling the followers modal to load all users …")
    last_count = 0
    stale_rounds = 0

    while True:
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

        followers_usernames = list(set(followers_usernames) | current_usernames)
        current_count = len(followers_usernames)

        log.info(f"  Loaded {current_count} followers so far …")

        if current_count == last_count:
            stale_rounds += 1
            if stale_rounds >= 4:
                log.info("No new followers after repeated scrolling. Assuming all loaded.")
                break
        else:
            stale_rounds = 0

        last_count = current_count

        smooth_scroll_element(driver, modal, pixels=random.randint(600, 1200))
        human_sleep(1.8, 3.5)

        if check_for_rate_limit(driver):
            auto_pause_after_rate_limit()

    log.info(f"✅ Scraped {len(followers_usernames)} followers.")
    return followers_usernames


def save_followers(followers_usernames: list) -> None:
    """Save the followers list to data/followers.json."""
    with open(FOLLOWERS_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(followers_usernames, f, indent=2, ensure_ascii=False)
    log.info(f"Saved followers list → {FOLLOWERS_DATA_FILE}")


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

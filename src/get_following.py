import json
import os
import random
import time
from typing import List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.helpers import log, check_for_rate_limit, auto_pause_after_rate_limit

# ---------------------------------------------------------------------------
# Instagram blocks direct navigation to /<username>/following/ and
# redirects silently to login.
#
# This scraper MUST use the internal React modal by:
#  1. Loading the profile page.
#  2. Waiting for the profile header to render.
#  3. CLICKING the Following number to trigger the JS modal.
#  4. Waiting for the internal modal container (div._aano).
#  5. Scrolling that container to the bottom.
#  6. Extracting the username links.
# ---------------------------------------------------------------------------


def scrape_following(driver: webdriver.Chrome, username: str) -> List[str]:
    """
    Full scrape of the Following list via profile modal click.
    """
    log.info("Following scrape — attempt 1 ...")

    # A. Navigate to profile
    profile_url = f"https://www.instagram.com/{username}/"
    log.info(f"Navigating to profile: {profile_url}")
    driver.get(profile_url)

    if check_for_rate_limit(driver):
        auto_pause_after_rate_limit()
        driver.get(profile_url)

    # B. Wait for profile header to load
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//header"))
        )
        log.info("Profile header loaded.")
    except Exception:
        log.error("Profile header did not load in time.")
        return []

    # C. Click FOLLOWING
    log.info("Clicking the Following link ...")
    try:
        # We query and click entirely inside JS to avoid passing WebElements over
        # the CDP bridge. If React re-renders between fetching the element and
        # clicking, ChromeDriver 145 on macOS Arm64 segfaults when serializing the stale element.
        clicked = False
        for _ in range(20):
            success = driver.execute_script("""
                var links = document.querySelectorAll('a');
                for (var i = 0; i < links.length; i++) {
                    if (links[i].href && links[i].href.indexOf('/following') !== -1) {
                        links[i].click();
                        return true;
                    }
                }
                return false;
            """)
            if success:
                clicked = True
                break
            time.sleep(1)
            
        if not clicked:
            raise Exception("Timeout waiting for 'following' link to appear in DOM.")
    except Exception as e:
        log.error(f"Could not find or click the Following link: {e}")
        return []

    # D. Wait for modal
    log.info("Waiting for Following modal (div._aano) ...")
    try:
        modal = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div._aano"))
        )
    except Exception:
        log.error("Following modal did not load in time.")
        return []

    # E. Scroll modal
    log.info("Scrolling modal to load all users ...")
    last_height = 0
    while True:
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight", modal
        )
        time.sleep(random.uniform(1.2, 2.3))

        new_height = driver.execute_script(
            "return arguments[0].scrollTop", modal
        )
        if new_height == last_height:
            break
        last_height = new_height

        if check_for_rate_limit(driver):
            auto_pause_after_rate_limit()

    # F. Extract usernames
    log.info("Extracting usernames ...")
    following_list = []
    seen = set()
    try:
        links = modal.find_elements(By.XPATH, ".//a[contains(@href, '/') and not(contains(@href, 'stories'))]")
        for link in links:
            href = link.get_attribute("href")
            if href:
                parts = [p for p in href.replace("https://www.instagram.com", "").split("/") if p]
                if parts:
                    uname = parts[0]
                    # Filter out system paths just in case
                    if uname and uname not in ("explore", "accounts", "p", "reels") and uname not in seen:
                        seen.add(uname)
                        following_list.append(uname)
    except Exception as e:
        log.error(f"Error extracting usernames: {e}")

    scraped_count = len(following_list)
    log.info(f"Scraped Following count  : {scraped_count}")

    # Save to JSON
    os.makedirs("data", exist_ok=True)
    with open("data/following.json", "w", encoding="utf-8") as f:
        json.dump(following_list, f, indent=4)
    log.info(f"Saved {scraped_count} following users -> data/following.json")

    return following_list

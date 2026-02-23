"""
ig_login.py — Instagram Login Module (Selenium-Based).

Responsibilities:
  - Build a Chrome WebDriver via driver_setup.get_driver()
  - Navigate to instagram.com/accounts/login
  - Fill in username and password with human-like typing
  - Submit the form
  - Pause for 2FA if Instagram requests it (user approves manually)
  - Detect and dismiss post-login popups ("Save info?", "Notifications?")
  - Return the authenticated driver for use by other modules

Chrome is ALWAYS run in full visible mode. Headless mode is intentionally
disabled because Instagram detects it via JavaScript fingerprinting and
blocks or challenges the session before login can complete.
"""

import time
import random
import sys

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from src.driver_setup import get_driver
from src.helpers import (
    human_sleep,
    brief_pause,
    long_pause,
    wait_for_element,
    log,
)

LOGIN_URL = "https://www.instagram.com/accounts/login/"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _type_like_human(element, text: str) -> None:
    """
    Type text into an element character-by-character at human typing speed.
    Random delay of 50-200 ms per character mimics realistic keystrokes.
    """
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.20))


def _dismiss_popup(driver: webdriver.Chrome, button_text: str, timeout: int = 5) -> None:
    """
    Try to find and click a button containing button_text.
    Silently ignores if the button is not present within timeout seconds.
    """
    try:
        btn = wait_for_element(
            driver,
            By.XPATH,
            f"//button[contains(text(), '{button_text}')]",
            timeout=timeout,
        )
        brief_pause()
        btn.click()
        log.info(f"Dismissed popup: '{button_text}'")
        brief_pause()
    except (TimeoutException, NoSuchElementException):
        pass  # popup did not appear; continue normally


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def login(credentials: dict) -> webdriver.Chrome:
    """
    Log into Instagram using the provided credentials.

    Steps:
        1. Launch Chrome in full visible mode via get_driver()
        2. Navigate to the Instagram login page
        3. Accept any cookie consent banners
        4. Enter username and password with human-like typing
        5. Submit the login form
        6. Wait for the page to load and detect any 2FA/challenge screen
        7. Pause and prompt user to complete 2FA if needed
        8. Dismiss post-login dialogs ("Save info?", "Turn on notifications?")
        9. Verify the session is active and return the driver

    Args:
        credentials: dict with keys "username" and "password"

    Returns:
        An authenticated Selenium WebDriver (browser stays open).

    Raises:
        SystemExit on unrecoverable login failure.
    """
    username = credentials.get("username", "").strip()
    password = credentials.get("password", "").strip()

    if not username or not password:
        log.error("Credentials missing in config/credentials.json")
        sys.exit(1)

    # Step 1: Launch browser (always visible, never headless)
    driver = get_driver()

    try:
        # Step 2: Navigate to Instagram login page
        log.info("Navigating to Instagram login page ...")
        driver.get(LOGIN_URL)
        human_sleep(4.0, 7.0)  # Wait for the page to fully render

        # Step 3: Accept cookie / GDPR consent banner if present (EU regions)
        _dismiss_popup(driver, "Allow", timeout=5)
        _dismiss_popup(driver, "Accept All", timeout=5)
        human_sleep(1.0, 2.5)

        # Step 4: Locate login fields
        log.info("Filling in credentials ...")
        username_field = wait_for_element(driver, By.NAME, "username", timeout=20)
        password_field = wait_for_element(driver, By.NAME, "password", timeout=20)

        # Click username field then type
        username_field.click()
        brief_pause()
        _type_like_human(username_field, username)
        human_sleep(0.8, 2.0)

        # Move to password field then type
        password_field.click()
        brief_pause()
        _type_like_human(password_field, password)
        human_sleep(0.5, 1.5)

        # Step 5: Submit the form
        log.info("Submitting login form ...")
        login_button = wait_for_element(
            driver, By.XPATH, "//button[@type='submit']", timeout=10
        )
        brief_pause()
        login_button.click()

        # Step 6: Wait for post-login page to load
        log.info("Waiting for Instagram to load after login ...")
        human_sleep(5.0, 9.0)

        # Step 7: Handle 2FA or security challenge
        #
        # If Instagram shows a verification/challenge screen the bot pauses
        # and waits for the user to approve it on their phone before continuing.
        current_url = driver.current_url
        if any(k in current_url for k in ("challenge", "two_factor", "verify")):
            log.warning("-" * 60)
            log.warning("Instagram requires 2FA / security verification.")
            log.warning("Complete the verification on your phone, then press Enter.")
            log.warning("-" * 60)
            input("  Press Enter after completing 2FA: ")
            human_sleep(3.0, 6.0)

        # Step 8: Dismiss post-login dialogs
        _dismiss_popup(driver, "Not Now", timeout=7)
        _dismiss_popup(driver, "Not now", timeout=5)
        human_sleep(1.5, 3.0)

        _dismiss_popup(driver, "Not Now", timeout=7)  # Notifications dialog
        _dismiss_popup(driver, "Not now", timeout=5)
        human_sleep(2.0, 4.0)

        # Step 9: Verify the session is active
        if "instagram.com" not in driver.current_url:
            log.error("Login may have failed — not on Instagram. Check your credentials.")
            driver.quit()
            sys.exit(1)

        log.info(f"Successfully logged in as @{username}")
        return driver  # Browser stays open for subsequent modules

    except Exception as exc:
        log.error(f"Login failed: {exc}")
        try:
            driver.quit()
        except Exception:
            pass
        sys.exit(1)

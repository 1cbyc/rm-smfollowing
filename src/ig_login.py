"""
ig_login.py — Instagram Login Module (Selenium-Based).

Responsibilities:
  - Build a Chrome WebDriver with anti-bot flags
  - Navigate to instagram.com/accounts/login
  - Fill in username & password with human-like typing
  - Submit the form
  - Pause for 2FA if required (user must approve manually)
  - Detect and handle post-login popups ("Save info?", "Notifications?")
  - Return the authenticated driver for use by other modules
"""

import time
import random
import logging
import sys
import platform

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from src.helpers import (
    human_sleep,
    brief_pause,
    long_pause,
    wait_for_element,
    get_random_user_agent,
    log,
)

LOGIN_URL = "https://www.instagram.com/accounts/login/"


def _get_chromedriver_path() -> str:
    """
    Return the correct ChromeDriver binary path for the current OS.
    Falls back to 'chromedriver' (assumes it's on system PATH).
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        return "drivers/chromedriver_mac"
    elif system == "Windows":
        return "drivers/chromedriver_win.exe"
    else:
        # Linux / CI — rely on PATH
        return "chromedriver"


def build_driver(headless: bool = False) -> webdriver.Chrome:
    """
    Build and return a Chrome WebDriver configured to minimise bot detection.

    Args:
        headless: If True, runs Chrome without a visible window.
                  Recommended to leave False so Instagram doesn't flag headless.

    Returns:
        A configured selenium.webdriver.Chrome instance.
    """
    options = Options()

    # ── Anti-bot detection flags ──────────────────────────────
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # ── Realistic window size ─────────────────────────────────
    options.add_argument("--window-size=1280,900")
    options.add_argument("--start-maximized")

    # ── Disable infobars and unnecessary logging ──────────────
    options.add_argument("--disable-infobars")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    # ── Random realistic user agent ───────────────────────────
    options.add_argument(f"user-agent={get_random_user_agent()}")

    # ── Optional headless mode ────────────────────────────────
    if headless:
        options.add_argument("--headless=new")

    # ── Build the service ─────────────────────────────────────
    chromedriver_path = _get_chromedriver_path()
    try:
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        # If the local driver fails, try letting Selenium Manager handle it
        log.warning(
            f"Local ChromeDriver at '{chromedriver_path}' not found or failed. "
            "Falling back to Selenium Manager auto-detection …"
        )
        driver = webdriver.Chrome(options=options)

    # ── Remove the 'webdriver' flag from navigator ────────────
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        },
    )

    return driver


def _type_like_human(element, text: str) -> None:
    """
    Type `text` into `element` character-by-character with random delays,
    mimicking human typing speed (50–200 ms per character).
    """
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.20))


def _dismiss_popup(driver: webdriver.Chrome, button_text: str, timeout: int = 5) -> None:
    """
    Try to find and click a button containing `button_text`.
    Silently ignores if the button is not present within `timeout` seconds.
    """
    try:
        btn = wait_for_element(driver, By.XPATH, f"//button[contains(text(), '{button_text}')]", timeout=timeout)
        brief_pause()
        btn.click()
        log.info(f"Dismissed popup: '{button_text}'")
        brief_pause()
    except (TimeoutException, NoSuchElementException):
        pass  # Popup didn't appear — that's fine


def login(credentials: dict) -> webdriver.Chrome:
    """
    Log into Instagram using the provided credentials dict.

    Args:
        credentials: {"username": "...", "password": "..."}

    Returns:
        An authenticated Selenium WebDriver.

    Raises:
        SystemExit if login fails or credentials are missing.
    """
    username = credentials.get("username", "").strip()
    password = credentials.get("password", "").strip()

    if not username or not password:
        log.error("Credentials missing in config/credentials.json")
        sys.exit(1)

    log.info("Launching Chrome browser …")
    driver = build_driver(headless=False)

    try:
        # ── 1. Open Instagram login page ──────────────────────
        log.info("Navigating to Instagram login page …")
        driver.get(LOGIN_URL)
        human_sleep(3.0, 6.0)  # Wait for page to fully render

        # ── 2. Accept cookies if the banner appears (EU) ──────
        _dismiss_popup(driver, "Allow", timeout=5)
        _dismiss_popup(driver, "Accept All", timeout=5)
        human_sleep(1.0, 2.5)

        # ── 3. Locate username and password fields ────────────
        log.info("Filling in credentials …")
        username_field = wait_for_element(driver, By.NAME, "username", timeout=20)
        password_field = wait_for_element(driver, By.NAME, "password", timeout=20)

        # Click username field first (more natural)
        username_field.click()
        brief_pause()

        # Type username character by character
        _type_like_human(username_field, username)
        human_sleep(0.8, 2.0)

        # Move to password field
        password_field.click()
        brief_pause()

        # Type password character by character
        _type_like_human(password_field, password)
        human_sleep(0.5, 1.5)

        # ── 4. Submit the login form ──────────────────────────
        log.info("Submitting login form …")
        login_button = wait_for_element(
            driver, By.XPATH, "//button[@type='submit']", timeout=10
        )
        brief_pause()
        login_button.click()

        # ── 5. Wait for post-login page to load ───────────────
        log.info("Waiting for Instagram to load after login …")
        human_sleep(5.0, 9.0)

        # ── 6. Handle 2FA if Instagram requires it ────────────
        #
        # If Instagram shows a 2FA / verification screen, we pause here
        # and tell the user to approve it on their phone, then press Enter.
        #
        current_url = driver.current_url
        if "challenge" in current_url or "two_factor" in current_url or "verify" in current_url:
            log.warning("=" * 60)
            log.warning("Instagram is asking for 2FA / security verification!")
            log.warning("Please complete the verification on your phone,")
            log.warning("then press Enter here to continue …")
            log.warning("=" * 60)
            input("  ▶  Press Enter after completing 2FA: ")
            human_sleep(3.0, 6.0)

        # ── 7. Dismiss post-login dialogs ─────────────────────
        # "Save Your Login Info?" dialog
        _dismiss_popup(driver, "Not Now", timeout=7)
        _dismiss_popup(driver, "Not now", timeout=5)
        human_sleep(1.5, 3.0)

        # "Turn On Notifications?" dialog
        _dismiss_popup(driver, "Not Now", timeout=7)
        _dismiss_popup(driver, "Not now", timeout=5)
        human_sleep(2.0, 4.0)

        # ── 8. Verify we are now logged in ────────────────────
        if "instagram.com" not in driver.current_url:
            log.error("Login may have failed — not on Instagram. Check credentials.")
            driver.quit()
            sys.exit(1)

        log.info(f"✅ Successfully logged in as @{username}")
        return driver

    except Exception as exc:
        log.error(f"Login failed with exception: {exc}")
        try:
            driver.quit()
        except Exception:
            pass
        sys.exit(1)

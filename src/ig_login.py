"""
ig_login.py — Instagram Login Module (Selenium-Based).

All DOM interactions use JavaScript execution (driver.execute_script) instead
of Selenium's native event injection (.click(), .send_keys). This bypasses a
ChromeDriver 145 / macOS Sonoma crash where the Rust-based native event system
segfaults on certain element interactions.

Responsibilities:
  - Build a Chrome WebDriver via driver_setup.get_driver()
  - Navigate to instagram.com/accounts/login
  - Fill in username and password with human-like JS typing
  - Submit the form via JS click
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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from src.driver_setup import get_driver
from src.helpers import (
    human_sleep,
    brief_pause,
    log,
)

LOGIN_URL = "https://www.instagram.com/accounts/login/"


# ---------------------------------------------------------------------------
# JS-safe interaction helpers
# ---------------------------------------------------------------------------

def _js_click(driver: webdriver.Chrome, element) -> None:
    """
    Click an element using JavaScript instead of Selenium's native event.
    Avoids the ChromeDriver 145 / macOS Arm64 Rust segfault on .click().
    """
    driver.execute_script("arguments[0].click();", element)
    brief_pause()


def _js_type(driver: webdriver.Chrome, element, text: str) -> None:
    """
    Type text into an input field using JavaScript, one character at a time,
    with a random human-like delay between characters (50-180 ms).

    Uses nativeInputValueSetter to trigger React's synthetic onChange events,
    which Instagram's login form requires to register keystrokes correctly.
    """
    # First focus the field via JS
    driver.execute_script("arguments[0].focus();", element)
    brief_pause()

    for char in text:
        # Inject the character by simulating native input value mutation.
        # Without this, React's controlled input ignores value changes.
        driver.execute_script(
            """
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(arguments[0], arguments[0].value + arguments[1]);
            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
            """,
            element,
            char,
        )
        time.sleep(random.uniform(0.05, 0.18))


def _wait_and_js_click(
    driver: webdriver.Chrome,
    by: str,
    selector: str,
    timeout: int = 15,
    label: str = "",
) -> bool:
    """
    Wait for an element, then click it via JavaScript.

    Returns True on success, False if the element was not found in time.
    """
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        brief_pause()
        _js_click(driver, element)
        if label:
            log.info(f"Clicked: {label}")
        return True
    except (TimeoutException, NoSuchElementException):
        return False


def _dismiss_popup(driver: webdriver.Chrome, button_text: str, timeout: int = 5) -> None:
    """
    Try to find and JS-click a button containing button_text.
    Silently ignores if the button is not present within timeout seconds.
    """
    _wait_and_js_click(
        driver,
        By.XPATH,
        f"//button[contains(text(), '{button_text}')]",
        timeout=timeout,
        label=f"popup '{button_text}'",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def login(credentials: dict) -> webdriver.Chrome:
    """
    Log into Instagram using the provided credentials.

    Steps:
        1.  Launch Chrome in full visible mode via get_driver()
        2.  Navigate to the Instagram login page
        3.  Accept any cookie consent banners (JS click)
        4.  Enter username field (JS type)
        5.  Enter password field (JS type)
        6.  Submit the login form (JS click)
        7.  Wait for the page to load
        8.  Detect and handle 2FA / challenge screen
        9.  Dismiss post-login dialogs (JS click)
        10. Verify the session is active and return the driver

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
        human_sleep(4.0, 7.0)  # wait for full render including JS bundles

        # Step 3: Cookie / GDPR consent banner (EU regions) — JS click
        _dismiss_popup(driver, "Allow", timeout=5)
        _dismiss_popup(driver, "Accept All", timeout=5)
        human_sleep(1.0, 2.5)

        # Step 4: Locate username field and type via JS
        log.info("Filling in credentials ...")
        log.info(f"Current URL before field detection: {driver.current_url}")

        username_field = None
        # Try up to 2 page loads: standard login URL and mobile fallback
        for attempt_url in [LOGIN_URL, "https://www.instagram.com/"]:
            try:
                if "login" not in driver.current_url:
                    log.info(f"Not on login page — navigating to {attempt_url} ...")
                    driver.get(attempt_url)
                    human_sleep(4.0, 6.0)

                # Try multiple selectors — Instagram's React form sometimes
                # renders name= only after JS hydration, but aria-label and
                # placeholder are in the initial HTML render.
                for selector in [
                    (By.NAME,        "username"),
                    (By.XPATH,       "//input[@aria-label='Phone number, username, or email']"),
                    (By.XPATH,       "//input[contains(@placeholder,'username') or contains(@placeholder,'phone') or contains(@placeholder,'email')]"),
                    (By.CSS_SELECTOR, "input[type='text']"),
                ]:
                    try:
                        username_field = WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located(selector)
                        )
                        log.info(f"Username field found via: {selector[1]}")
                        break
                    except TimeoutException:
                        continue

                if username_field:
                    break
            except Exception as e:
                log.warning(f"Field detection error: {e} — retrying ...")
                continue

        if username_field is None:
            log.error(
                f"Username field not found. Current URL: {driver.current_url}\n"
                "Instagram may be showing a consent page or blocking the bot."
            )
            driver.quit()
            sys.exit(1)

        _js_click(driver, username_field)
        _js_type(driver, username_field, username)
        human_sleep(0.8, 2.0)

        # Step 5: Locate password field via multi-selector fallback
        password_field = None
        for selector in [
            (By.NAME,        "password"),
            (By.XPATH,       "//input[@aria-label='Password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ]:
            try:
                password_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(selector)
                )
                log.info(f"Password field found via: {selector[1]}")
                break
            except TimeoutException:
                continue

        if password_field is None:
            log.error("Password field not found.")
            driver.quit()
            sys.exit(1)

        _js_click(driver, password_field)
        _js_type(driver, password_field, password)
        human_sleep(0.5, 1.5)

        # Step 6: Submit the login form via JS click (avoids native click crash)
        log.info("Submitting login form ...")
        submitted = _wait_and_js_click(
            driver,
            By.XPATH,
            "//button[@type='submit']",
            timeout=10,
            label="submit button",
        )
        if not submitted:
            # Fallback: submit via Enter key on the password field using JS
            log.warning("Submit button not found — submitting via form.submit() ...")
            driver.execute_script(
                "arguments[0].closest('form').submit();", password_field
            )
            brief_pause()

        # Step 7: Wait for post-login page to load
        log.info("Waiting for Instagram to load after login ...")
        human_sleep(5.0, 9.0)

        # Step 8: Handle 2FA or security challenge
        current_url = driver.current_url
        if any(k in current_url for k in ("challenge", "two_factor", "verify")):
            log.warning("-" * 60)
            log.warning("Instagram requires 2FA / security verification.")
            log.warning("Complete the verification on your phone, then press Enter.")
            log.warning("-" * 60)
            input("  Press Enter after completing 2FA: ")
            human_sleep(3.0, 6.0)

        # Step 9: Dismiss post-login dialogs ("Save Login Info?", "Notifications?")
        _dismiss_popup(driver, "Not Now", timeout=7)
        _dismiss_popup(driver, "Not now", timeout=5)
        human_sleep(1.5, 3.0)
        _dismiss_popup(driver, "Not Now", timeout=7)
        _dismiss_popup(driver, "Not now", timeout=5)
        human_sleep(2.0, 4.0)

        # Step 10: Verify the session is still on Instagram
        if "instagram.com" not in driver.current_url:
            log.error("Login may have failed — redirected away from Instagram.")
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

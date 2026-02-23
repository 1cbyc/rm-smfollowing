"""
driver_setup.py — Stable Chrome WebDriver factory for the Instagram Unfollow Bot.

Why visible (non-headless) mode is mandatory for Instagram:
- Instagram's front-end actively detects headless Chrome via JavaScript APIs
  (navigator.webdriver, window.chrome, plugin count, rendering fingerprints).
- In headless mode these APIs return values that differ from a real browser,
  causing Instagram to immediately flag the session as automated and block login
  or force a verification checkpoint before any action is taken.
- Running in full visible mode means Chrome behaves identically to a real user
  session, passing all client-side bot-detection checks.

This module is the ONLY place in the project where webdriver.Chrome is created.
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from src.helpers import log


def get_driver() -> webdriver.Chrome:
    """
    Build and return a Chrome WebDriver in safe visible mode.

    Chrome options chosen for maximum stability on macOS and Windows:
      --start-maximized          : Open at full screen so elements are visible
      --disable-gpu              : Prevent GPU-related crashes (especially macOS ARM)
      --no-sandbox               : Required in some macOS permission setups
      --disable-dev-shm-usage    : Prevent /dev/shm memory errors on Mac/Linux
      --disable-blink-features=AutomationControlled : Hide the automation flag
      excludeSwitches            : Remove the "Chrome is being controlled" banner
      useAutomationExtension     : Disable Selenium's default automation extension

    ChromeDriver is auto-selected by Selenium Manager (no manual path needed).
    """
    options = Options()

    # SAFEST MODE: always run in full visible browser window
    # options.add_argument("--headless")     <- INTENTIONALLY REMOVED
    # options.add_argument("--headless=new") <- INTENTIONALLY REMOVED

    # Stability flags
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Anti-bot-detection flags
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Suppress Chrome's own logging noise
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    # Let Selenium Manager auto-download the correct ChromeDriver version
    # No executable_path needed — Selenium 4.6+ handles this automatically
    service = Service()

    log.info("Launching Chrome browser (visible mode) ...")
    driver = webdriver.Chrome(service=service, options=options)

    # Patch navigator.webdriver to undefined so Instagram JS checks pass
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

    log.info("Chrome launched successfully.")
    return driver

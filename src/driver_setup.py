"""
driver_setup.py — Chrome WebDriver factory for the Instagram Unfollow Bot.

Why Selenium Manager crashes on macOS Sonoma:
  Selenium 4.6+ ships a bundled binary called "Selenium Manager" (written in Rust)
  that auto-downloads ChromeDriver at runtime. On macOS Sonoma (14.x) this binary
  is blocked by Gatekeeper, triggers OS-level quarantine, and can segfault inside
  the Rust allocator — producing the chromedriver Rust stacktrace you see in the
  terminal. The fix is to disable Selenium Manager entirely and point Selenium at
  a pre-approved local ChromeDriver binary.

Setup — place ChromeDriver v114 in the drivers/ folder:
  macOS:
    1. Download from https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_mac64.zip
    2. Unzip and rename the binary to:  drivers/chromedriver_mac
    3. Make it executable:  chmod +x drivers/chromedriver_mac
    4. Remove quarantine:   xattr -d com.apple.quarantine drivers/chromedriver_mac

  Windows:
    1. Download from https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_win32.zip
    2. Rename to: drivers/chromedriver_win.exe

  IMPORTANT: ChromeDriver version must match your installed Chrome version.
  Check your Chrome version at chrome://settings/help and download accordingly.
"""

import os
import platform

# ---------------------------------------------------------------------------
# Disable Selenium Manager BEFORE any selenium import uses it.
# These three env-vars stop Selenium from invoking its bundled Rust binary.
# ---------------------------------------------------------------------------
os.environ["SE_DOWNLOAD_DRIVER"] = "0"
os.environ["SE_MANAGER"] = "0"
os.environ["SE_SIDECAR"] = "0"

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from src.helpers import log


def _chromedriver_path() -> str:
    """Return the path to the local ChromeDriver binary for the current OS."""
    system = platform.system()
    if system == "Windows":
        return "drivers/chromedriver_win.exe"
    # macOS or Linux
    return "drivers/chromedriver_mac"


def get_driver() -> webdriver.Chrome:
    """
    Build and return a Chrome WebDriver using the local ChromeDriver binary.

    Selenium Manager is fully disabled via environment variables set at module
    load time. The Service is always constructed with an explicit path so
    Selenium never falls back to auto-detection.

    Chrome is ALWAYS run in full visible mode — headless mode is disabled
    because Instagram's JavaScript fingerprinting detects headless browsers
    and blocks or challenges the session before login can complete.
    """
    log.info("Selenium Manager disabled.")
    log.info("Using local ChromeDriver v145 at: " + _chromedriver_path())
    log.info("Expecting Chrome browser version 145.")

    options = Options()

    # SAFEST MODE: always visible — headless intentionally removed
    # options.add_argument("--headless")      <- DO NOT UNCOMMENT
    # options.add_argument("--headless=new")  <- DO NOT UNCOMMENT

    # Stability flags required for reliable macOS operation
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Anti-bot-detection flags
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Suppress Chrome's own logging noise in the terminal
    options.add_argument("--log-level=3")
    options.add_argument("--silent")

    # Explicit local ChromeDriver path — no Service() fallback, no auto-detect
    service = Service(_chromedriver_path())

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

    # Version compatibility check — warn if Chrome major version does not match.
    try:
        browser_version = driver.capabilities.get("browserVersion", "")
        if not browser_version.startswith("145"):
            log.warning("-" * 65)
            log.warning("Chrome version mismatch detected!")
            log.warning(f"  ChromeDriver version : 145")
            log.warning(f"  Chrome browser found : {browser_version}")
            log.warning("ChromeDriver and Chrome must share the same major version.")
            log.warning("Download the matching ChromeDriver from:")
            log.warning("  https://googlechromelabs.github.io/chrome-for-testing/")
            log.warning("-" * 65)
    except Exception:
        pass  # Non-critical

    return driver

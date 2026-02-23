"""
helpers.py — Shared utility functions for the Instagram Unfollow Bot.

Provides:
  - Human-like random delays
  - Human-like mouse movement simulation
  - Smooth scroll inside a modal element
  - Waiting for elements with retry
  - Rate-limit phrase detection
  - Clean logging helpers
"""

import time
import random
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

# ──────────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("IGBot")


# ──────────────────────────────────────────────────────────────
# Rate-limit phrase detection
# ──────────────────────────────────────────────────────────────

# These phrases appear on Instagram when you are being rate-limited or blocked.
RATE_LIMIT_PHRASES = [
    "Try Again Later",
    "Action Blocked",
    "Please Wait",
    "Protecting our community",
    "We restrict certain activity",
    "Please Slow Down",
    "Something went wrong",
]


def check_for_rate_limit(driver: webdriver.Chrome) -> bool:
    """
    Scan the current page source for any known rate-limit / block phrases.

    Returns True if a rate-limit phrase is found, False otherwise.
    """
    try:
        page_text = driver.page_source
        for phrase in RATE_LIMIT_PHRASES:
            if phrase.lower() in page_text.lower():
                log.warning(f"Rate-limit phrase detected: '{phrase}'")
                return True
    except Exception:
        pass
    return False


# ──────────────────────────────────────────────────────────────
# Human-like timing helpers
# ──────────────────────────────────────────────────────────────

def human_sleep(min_sec: float = 1.5, max_sec: float = 4.8) -> None:
    """Sleep for a random duration that mimics human reaction time."""
    delay = round(random.uniform(min_sec, max_sec), 2)
    log.debug(f"Sleeping {delay}s …")
    time.sleep(delay)


def brief_pause() -> None:
    """Very short pause — 0.3 to 1.2 seconds — for between micro-actions."""
    time.sleep(random.uniform(0.3, 1.2))


def long_pause(min_sec: float = 8.0, max_sec: float = 18.0) -> None:
    """Longer pause used when transitioning between major actions."""
    delay = round(random.uniform(min_sec, max_sec), 2)
    log.info(f"Long pause: waiting {delay}s …")
    time.sleep(delay)


def auto_pause_after_rate_limit(
    min_minutes: float = 10.0, max_minutes: float = 20.0
) -> None:
    """
    Auto-pause for 10–20 minutes when Instagram rate-limits are detected.
    Prints a countdown every minute so the user can see progress.
    """
    minutes = round(random.uniform(min_minutes, max_minutes), 1)
    seconds = int(minutes * 60)
    log.warning(
        f"Instagram rate limit detected — auto-pausing for {minutes} minutes."
    )
    for remaining in range(seconds, 0, -60):
        mins_left = remaining // 60
        log.info(f"  ⏸  Resuming in ~{mins_left} minute(s) …")
        time.sleep(min(60, remaining))
    log.info("Resuming unfollowing …")


# ──────────────────────────────────────────────────────────────
# Scrolling helpers
# ──────────────────────────────────────────────────────────────

def smooth_scroll_down(driver: webdriver.Chrome, pixels: int = None) -> None:
    """
    Scroll the main page down by a random or specified number of pixels.
    Uses JavaScript to avoid triggering bot detection.
    """
    if pixels is None:
        pixels = random.randint(300, 800)
    driver.execute_script(f"window.scrollBy(0, {pixels});")
    brief_pause()


def smooth_scroll_element(
    driver: webdriver.Chrome, element, pixels: int = None
) -> None:
    """
    Scroll a specific DOM element (e.g. a modal) by a given pixel amount.
    Used to load more users inside the followers/following modal.
    """
    if pixels is None:
        pixels = random.randint(400, 900)
    driver.execute_script(
        f"arguments[0].scrollTop += {pixels};", element
    )
    brief_pause()


# ──────────────────────────────────────────────────────────────
# Wait helpers
# ──────────────────────────────────────────────────────────────

def wait_for_element(
    driver: webdriver.Chrome,
    by: str,
    selector: str,
    timeout: int = 20,
) -> object:
    """
    Wait up to `timeout` seconds for a single element to appear and return it.
    Raises TimeoutException if not found.
    """
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, selector))
    )


def wait_for_elements(
    driver: webdriver.Chrome,
    by: str,
    selector: str,
    timeout: int = 20,
) -> list:
    """
    Wait up to `timeout` seconds for multiple elements to appear and return them.
    """
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_all_elements_located((by, selector))
    )


def wait_and_click(
    driver: webdriver.Chrome,
    by: str,
    selector: str,
    timeout: int = 20,
) -> None:
    """
    Wait for an element to be clickable, then click it after a brief human pause.
    """
    el = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, selector))
    )
    brief_pause()
    el.click()
    brief_pause()


# ──────────────────────────────────────────────────────────────
# Mouse movement simulation
# ──────────────────────────────────────────────────────────────

def human_move_to(driver: webdriver.Chrome, element) -> None:
    """
    Move the mouse to an element in a human-like way using ActionChains.
    Adds slight random offsets to avoid perfectly centred clicks.
    """
    try:
        offset_x = random.randint(-5, 5)
        offset_y = random.randint(-3, 3)
        actions = ActionChains(driver)
        actions.move_to_element_with_offset(element, offset_x, offset_y)
        actions.perform()
        brief_pause()
    except Exception:
        pass  # Non-critical; continue even if mouse simulation fails


# ──────────────────────────────────────────────────────────────
# Misc helpers
# ──────────────────────────────────────────────────────────────

def random_unfollow_delay() -> None:
    """
    Enforce the medium-risk speed: ~15–20 unfollows per hour.
    That means 3–4 minutes between unfollows on average.
    We randomise between 170 and 240 seconds (2m 50s – 4m).
    """
    delay = random.randint(170, 240)
    log.info(f"Waiting {delay}s before next unfollow (medium-risk speed) …")
    time.sleep(delay)


def get_random_user_agent() -> str:
    """Return one of several realistic Chrome user-agent strings."""
    agents = [
        # macOS / Chrome
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36",
        # Windows / Chrome
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36",
        # macOS / Chrome (slightly older)
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Safari/537.36",
    ]
    return random.choice(agents)

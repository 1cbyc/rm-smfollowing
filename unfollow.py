import os
import json
import time
import random
import argparse
from dotenv import load_dotenv
from instagrapi import Client

WHITELIST_FILE = "config/whitelist.json"


def load_whitelist() -> set:
    """Load whitelisted usernames from config/whitelist.json."""
    try:
        with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        usernames = data.get("whitelist", []) if isinstance(data, dict) else data
        whitelist = {u.lower().strip() for u in usernames if u}
        print(f"Loaded {len(whitelist)} whitelisted account(s).")
        return whitelist
    except FileNotFoundError:
        print(f"Warning: {WHITELIST_FILE} not found. No accounts will be whitelisted.")
        return set()
    except (json.JSONDecodeError, Exception) as e:
        print(f"Warning: Could not load whitelist: {e}")
        return set()


def login_via_sessionid(cl: Client, sessionid: str, username: str, session_file: str) -> bool:
    """
    Log in using a browser session ID — the most reliable method.
    No challenge or 2FA popup required.
    """
    try:
        print("Logging in via session ID (browser cookie)...")
        cl.login_by_sessionid(sessionid)
        cl.dump_settings(session_file)
        print("Logged in successfully via session ID.")
        return True
    except Exception as e:
        print(f"[ERROR] Session ID login failed: {e}")
        return False


def login_via_password(cl: Client, username: str, password: str, session_file: str) -> bool:
    """
    Log in using username + password with challenge code support.
    """
    print(f"Attempting password login for @{username}...")
    try:
        cl.login(username, password)
        cl.dump_settings(session_file)
        print("Logged in successfully and session saved.")
        return True
    except Exception as e:
        err_str = str(e)
        print(f"\n[ERROR] Password login failed: {err_str}")
        print("\n=================")
        print("Instagram is blocking the API login with a security challenge.")
        print("")
        print("SOLUTION — use your browser session ID instead:")
        print("  1. Open https://www.instagram.com in Chrome/Safari and log in.")
        print("  2. Open DevTools (F12 or Cmd+Option+I).")
        print("  3. Go to: Application → Cookies → https://www.instagram.com")
        print("  4. Find the cookie named: sessionid")
        print("  5. Copy its value and add it to your .env file:")
        print("       IG_SESSIONID=your_session_id_here")
        print("  6. Run the script again.")
        print("=================\n")
        return False


def main():
    parser = argparse.ArgumentParser(description="Unfollow all Instagram accounts you follow, except those on your whitelist.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without actually unfollowing.")
    args = parser.parse_args()

    load_dotenv()
    username  = os.getenv("IG_USERNAME")
    password  = os.getenv("IG_PASSWORD")
    sessionid = os.getenv("IG_SESSIONID", "").strip()

    if not username:
        print("Error: Please set IG_USERNAME in your .env file.")
        return

    cl = Client()
    cl.delay_range = [1, 3]

    session_file = "session.json"

    # Load saved device settings if available so Instagram recognises the same device UUID
    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            print(f"Device settings loaded from {session_file}.")
        except Exception:
            pass

    logged_in = False

    # ── Try session ID first (most reliable, no challenge) ────
    if sessionid:
        logged_in = login_via_sessionid(cl, sessionid, username, session_file)

    # ── If session cookie in existing session.json is still valid ────
    if not logged_in and cl.cookie_dict.get("sessionid"):
        try:
            print("Checking if saved session is still valid...")
            cl.get_timeline_feed()
            logged_in = True
            print("Saved session is valid.")
        except Exception:
            print("Saved session expired — will re-login.")

    # ── Fall back to password login ───────────────────────────
    if not logged_in and password:
        logged_in = login_via_password(cl, username, password, session_file)

    if not logged_in:
        return

    print("Checking your user ID...")
    user_id = cl.user_id
    if not user_id:
        try:
            user_id = cl.user_id_from_username(username)
        except Exception as e:
            print(f"\nFailed to fetch User ID: {e}")
            print("\n=================")
            print("IMPORTANT: Instagram blocked the request. You likely have a Challenge Checkpoint pending.")
            print("Please open the Instagram app on your phone, tap 'This was me' to approve the new login.")
            print("Then run this script again.")
            print("=================\n")
            return
            
    print(f"User ID configured: {user_id}")

    # Load whitelist before fetching data
    whitelist = load_whitelist()

    try:
        print("Fetching list of users you follow...")
        following = cl.user_following(user_id)
        print(f"You are following {len(following)} users.")
    except Exception as e:
        print(f"\nFailed to fetch following list: {e}")
        print("\n=================")
        print("IMPORTANT: Instagram blocked the request. You likely have a Challenge Checkpoint pending.")
        print("Please open the Instagram app on your phone, tap 'This was me' to approve the new login.")
        print("Then run this script again.")
        print("=================\n")
        return

    # Unfollow everyone except whitelisted accounts
    following_ids = set(following.keys())
    # Map user_id -> username for whitelist filtering
    whitelist_ids = {
        uid for uid, user in following.items()
        if user.username.lower().strip() in whitelist
    }

    targets = following_ids - whitelist_ids
    print(f"\nFound {len(targets)} account(s) to unfollow ({len(whitelist_ids)} whitelisted, skipped).")

    if len(targets) == 0:
        print("Nothing to unfollow.")
        return

    print("\nStarting to process accounts...")

    count = 0
    for target_id in targets:
        try:
            # We need to fetch user info to know if they are private
            user_info = cl.user_info(target_id)
            username_target = user_info.username
            is_private = user_info.is_private

            if is_private:
                print(f"Skipping @{username_target} (Account is private)")
                continue

            if args.dry_run:
                print(f"[DRY-RUN] Would unfollow: @{username_target}")
            else:
                print(f"Unfollowing: @{username_target}...")
                cl.user_unfollow(target_id)
                count += 1
                
                # Random delay between 15 and 45 seconds to avoid rate limiting or action blocks
                delay = random.uniform(15, 45)
                print(f"Sleeping for {delay:.2f} seconds to avoid rate limits...")
                time.sleep(delay)

        except Exception as e:
            print(f"Error processing user ID {target_id}: {e}")
            # Add a longer delay if we hit an error (like a soft block)
            print("Sleeping for 60 seconds due to an error before continuing...")
            time.sleep(60)
            
    if not args.dry_run:
        print(f"\nFinished. Unfollowed {count} account(s).")
    else:
        print("\nFinished dry-run.")

if __name__ == "__main__":
    main()

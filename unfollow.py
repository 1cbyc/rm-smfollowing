import os
import time
import random
import argparse
import hashlib
import uuid
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

def main():
    parser = argparse.ArgumentParser(description="Unfollow Instagram accounts that don't follow you back.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without actually unfollowing.")
    args = parser.parse_args()

    load_dotenv()
    username = os.getenv("IG_USERNAME")
    password = os.getenv("IG_PASSWORD")

    if not username or not password:
        print("Error: Please set IG_USERNAME and IG_PASSWORD in your .env file.")
        return

    cl = Client()
    # Adding a random delay range to requests to avoid quick blocks
    cl.delay_range = [1, 3]

    session_file = "session.json"
    
    # 1. Device identity lock-in: load or save settings BEFORE login so UUIDs persist across runs
    if os.path.exists(session_file):
        print(f"Loading session and device settings from {session_file}...")
        cl.load_settings(session_file)
    else:
        print("Generating new device mapping from scratch...")
        # Tie the Android device ID to the user_id so it's stable and predictable!
        # Instagrapi generates a random Device ID by default if we don't do this, 
        # which immediately triggers a Challenge Checkpoint because Instagram thinks this
        # is a new phone every time the script runs.
        
        # We manually generate a deterministic UUID based on the username
        stable_hash = hashlib.md5(username.encode()).hexdigest()
        device_uuid = str(uuid.UUID(stable_hash))
        
        cl.set_uuids({
            "phone_id": device_uuid,
            "uuid": device_uuid
        })
        cl.set_device({
            "app_version": "269.0.0.18.75",
            "android_version": 26,
            "android_release": "8.0.0",
            "dpi": "480dpi",
            "resolution": "1080x1920",
            "manufacturer": "OnePlus",
            "device": "devitron",
            "model": "6T Dev",
            "cpu": "qcom",
            "version_code": "314665256"
        })
        cl.dump_settings(session_file)

    logged_in = False
    
    # 2. Check if a valid session already exists in the dict
    if cl.cookie_dict.get("sessionid"):
        try:
            print("Checking if existing session is valid...")
            cl.get_timeline_feed()
            logged_in = True
            print("Session is valid.")
        except Exception:
            print("Session is invalid, will need to re-login.")
            logged_in = False

    # 3. If no valid session, try logging in
    if not logged_in:
        print(f"Attempting password login for {username}...")
        try:
            cl.login(username, password)
            cl.dump_settings(session_file)
            print("Logged in successfully and session saved.")
        except Exception as e:
            import traceback
            print(f"\nFailed to login: {e}")
            print("\n=================")
            print("IMPORTANT: Instagram may have served a Challenge Checkpoint.")
            print("Your automatically generated Device ID has been saved to 'session.json'.")
            print("Please open the Instagram app on your phone, tap 'This was me' to approve the new login.")
            print("Then run this script again. It will use the SAME Device ID which is now approved.")
            print("=================\n")
            traceback.print_exc()
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
    
    try:
        print("Fetching list of users you follow...")
        following = cl.user_following(user_id)
        print(f"You are following {len(following)} users.")
        
        print("Fetching list of your followers...")
        followers = cl.user_followers(user_id)
        print(f"You have {len(followers)} followers.")
    except Exception as e:
        print(f"\nFailed to fetch followers/following: {e}")
        print("\n=================")
        print("IMPORTANT: Instagram blocked the request. You likely have a Challenge Checkpoint pending.")
        print("Please open the Instagram app on your phone, tap 'This was me' to approve the new login.")
        print("Then run this script again.")
        print("=================\n")
        return

    following_ids = set(following.keys())
    follower_ids = set(followers.keys())

    non_followers_ids = following_ids - follower_ids
    print(f"\nFound {len(non_followers_ids)} users who don't follow you back.")

    if len(non_followers_ids) == 0:
        print("Everyone you follow follows you back!")
        return

    print("\nStarting to check accounts...")
    
    count = 0
    for target_id in non_followers_ids:
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
        print(f"\nFinished processing. Unfollowed {count} users.")
    else:
        print("\nFinished dry-run.")

if __name__ == "__main__":
    main()

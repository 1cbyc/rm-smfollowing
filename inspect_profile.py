import json
import time

from src.driver_setup import get_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def dump():
    credentials = json.load(open("config/credentials.json"))
    driver = get_driver()
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(5)
    
    # login
    try:
        user_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='username']")))
        pass_input = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
        user_input.send_keys(credentials["username"])
        pass_input.send_keys(credentials["password"])
        pass_input.submit()
        time.sleep(10)
    except Exception as e:
        print("Login err:", e)
        pass
        
    driver.get(f"https://www.instagram.com/{credentials['username']}/")
    time.sleep(10) # wait for React to hydrate the profile header
    
    # Dump HTML
    html = driver.execute_script("return document.querySelector('header') ? document.querySelector('header').outerHTML : 'no-header';")
    with open("profile_header.html", "w") as f:
        f.write(html)
    print("Dumped header HTML inside profile_header.html")
    driver.quit()

if __name__ == "__main__":
    dump()

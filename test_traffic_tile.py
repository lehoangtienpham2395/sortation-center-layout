import sys
import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("console", lambda msg: print(f"[CONSOLE {msg.type}] {msg.text}"))
        
        file_url = "file:///C:/Users/lehoa/.gemini/antigravity/scratch/sortation-center-layout/public/map/index.html"
        print(f"Navigating to {file_url}...")
        page.goto(file_url)
        page.wait_for_timeout(2000)
        
        # Click traffic button
        print("Clicking Traffic button...")
        page.click("#btn-toggle-traffic")
        page.wait_for_timeout(3000)
        
        page.screenshot(path="traffic_test.png")
        print("Saved traffic_test.png")
        
        if errors:
            print("PAGE ERRORS:", errors)
        else:
            print("ZERO PAGE ERRORS!")
            
        browser.close()

if __name__ == "__main__":
    run()

import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("console", lambda msg: print(f"[Console] {msg.type}: {msg.text}") if msg.type in ["error", "warning"] else None)

        file_path = os.path.abspath("public/map/index.html")
        url = f"file:///{file_path.replace('\\', '/')}"
        print(f"Navigating to {url}...")
        
        await page.goto(url)
        await page.wait_for_timeout(3000)
        
        await page.screenshot(path="map_test.png", full_page=True)
        print("Saved map_test.png screenshot.")
        
        if errors:
            print("PAGE ERRORS FOUND:", errors)
        else:
            print("ZERO PAGE ERRORS! Map loaded cleanly.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())

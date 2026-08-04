import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        file_path = os.path.abspath("public/map/index.html")
        url = f"file:///{file_path.replace('\\', '/')}"
        
        await page.goto(url)
        await page.wait_for_timeout(3000)
        
        # Take screenshot of current map
        await page.screenshot(path="map_current.png", full_page=True)
        print("Captured map_current.png")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())

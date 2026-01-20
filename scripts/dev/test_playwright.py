import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        print("Creating context with proxy...")
        try:
            context = await browser.new_context(
                proxy={
                    "server": "http://170.106.118.114:2333",
                    "username": "ub033d0d0583c05dd-zone-custom",
                    "password": "ub033d0d0583c05dd"
                }
            )
            print("Opening page...")
            page = await context.new_page()
            print("Navigating to ipify...")
            await page.goto("https://api.ipify.org?format=json", timeout=30000)
            print("Content:", await page.content())
        except Exception as e:
            print("Error:", e)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test())

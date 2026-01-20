"""Debug script for FireFaucet login testing."""
import asyncio
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DebugTest")

async def test():
    from browser.instance import BrowserManager
    from core.config import BotSettings
    from solvers.captcha import CaptchaSolver
    
    settings = BotSettings()
    bm = BrowserManager(headless=False, block_images=False, block_media=True)
    
    try:
        logger.info("Launching browser...")
        await bm.launch()
        ctx = await bm.create_context()
        page = await bm.new_page(ctx)
        
        logger.info("Navigating to FireFaucet login...")
        await page.goto("https://firefaucet.win/login", wait_until="domcontentloaded", timeout=60000)
        
        logger.info(f"Current URL: {page.url}")
        logger.info(f"Page title: {await page.title()}")
        
        # Wait for form
        logger.info("Waiting for login form...")
        await page.wait_for_selector("#username", timeout=15000)
        logger.info("Login form found!")
        
        # Fill form
        logger.info("Filling username...")
        await page.fill("#username", "blazefoley97@gmail.com")
        await asyncio.sleep(0.5)
        
        logger.info("Filling password...")
        await page.fill("#password", "silverFox420?")
        await asyncio.sleep(0.5)
        
        # Check for captcha iframes
        recaptcha_iframe = await page.query_selector("iframe[src*='recaptcha']")
        hcaptcha_iframe = await page.query_selector("iframe[src*='hcaptcha']")
        logger.info(f"reCAPTCHA iframe present: {recaptcha_iframe is not None}")
        logger.info(f"hCaptcha iframe present: {hcaptcha_iframe is not None}")
        
        # Initialize solver and try to solve
        logger.info("Initializing captcha solver...")
        solver = CaptchaSolver(api_key=settings.twocaptcha_api_key, provider="2captcha")
        logger.info(f"Solver mode: {'auto' if settings.twocaptcha_api_key else 'manual'}")
        
        # Try to solve captcha
        logger.info("Attempting to solve captcha...")
        solved = await solver.solve_captcha(page)
        logger.info(f"Captcha solved: {solved}")
        
        if solved:
            # Click submit
            logger.info("Clicking submit button...")
            submit = page.locator("button.submitbtn")
            await submit.click()
            
            # Wait for result
            logger.info("Waiting for login result...")
            await asyncio.sleep(5)
            
            logger.info(f"Final URL: {page.url}")
            if "/dashboard" in page.url:
                logger.info("SUCCESS - Logged in!")
            else:
                # Take screenshot
                await page.screenshot(path="login_result.png")
                logger.warning(f"Login may have failed. Screenshot saved.")
        
        logger.info("Keeping browser open for 30 seconds for inspection...")
        await asyncio.sleep(30)
        
    except Exception as e:
        import traceback
        logger.error(f"ERROR: {e}")
        traceback.print_exc()
    finally:
        logger.info("Closing browser...")
        await bm.close()

if __name__ == "__main__":
    asyncio.run(test())

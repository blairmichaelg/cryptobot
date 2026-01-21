from .base import FaucetBot, ClaimResult
import logging
from solvers.shortlink import ShortlinkSolver
import asyncio
import random

logger = logging.getLogger(__name__)

class FireFaucetBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "FireFaucet"
        self.base_url = "https://firefaucet.win"

    async def view_ptc_ads(self):
        """
        Views PTC (Paid-To-Click) ads for FireFaucet using updated selectors.
        
        Process:
        1. Navigate to PTC ads page
        2. Detect available ad cards
        3. For each ad (up to limit):
           - Click ad with human-like interaction
           - Detect and solve CAPTCHAs (custom numeric image or Turnstile/hCaptcha)
           - Submit and verify completion
        4. Return to PTC page for next ad
        
        Stealth features:
        - human_like_click() for ad interactions
        - random_delay() between actions
        - CAPTCHA solving with multiple provider support
        
        Raises:
            Exception: Logs errors but doesn't raise to prevent interrupting other tasks
        """
        try:
            logger.info(f"[{self.faucet_name}] Checking PTC Ads...")
            await self.page.goto(f"{self.base_url}/ptc")
            
            # Selector for the first available ad card
            ad_button = self.page.locator(".row > div:nth-child(1) > div > div:nth-child(3) > a")
            
            processed = 0
            limit = 3
            
            while processed < limit:
                if await ad_button.count() == 0:
                    logger.info(f"[{self.faucet_name}] No more PTC ads available (processed {processed}).")
                    break
                
                logger.info(f"[{self.faucet_name}] 🎥 Watching PTC Ad {processed + 1}/{limit}...")
                await self.idle_mouse(duration=random.uniform(0.5, 1.0))
                await ad_button.first.click()
                await self.page.wait_for_load_state()
                logger.debug(f"[{self.faucet_name}] Loaded PTC ad page: {self.page.url}")
                
                # PTC ads use a custom numeric image captcha
                # We'll rely on our generic solver which should detect the image/input
                # or we might need specific logic for #description > img
                captcha_img = self.page.locator("#description > img")
                if await captcha_img.count() > 0:
                    logger.info(f"[{self.faucet_name}] Custom PTC captcha image detected. Solving...")
                    # Basic solving logic (can be expanded with OCR if needed)
                    await self.solver.solve_captcha(self.page)
                    logger.debug(f"[{self.faucet_name}] Custom PTC captcha solved")
                
                # Check for other captchas (Turnstile/hCaptcha)
                if await self.page.query_selector("iframe[src*='turnstile'], iframe[src*='hcaptcha']"):
                    logger.info(f"[{self.faucet_name}] Standard CAPTCHA (Turnstile/hCaptcha) detected on PTC ad")
                    await self.solver.solve_captcha(self.page)
                    logger.debug(f"[{self.faucet_name}] Standard CAPTCHA solved")
                
                # Submit button for PTC
                submit_btn = self.page.locator("#submit-button")
                if await submit_btn.count() > 0:
                    logger.debug(f"[{self.faucet_name}] Clicking PTC submit button")
                    await self.idle_mouse(duration=random.uniform(0.3, 0.8))
                    await self.human_like_click(submit_btn)
                    await self.random_delay(2, 4)
                    logger.info(f"[{self.faucet_name}] ✅ PTC Ad {processed + 1} completed")
                else:
                    logger.warning(f"[{self.faucet_name}] PTC submit button not found")
                
                processed += 1
                logger.debug(f"[{self.faucet_name}] Returning to PTC ads list")
                await self.page.goto(f"{self.base_url}/ptc")
                
        except Exception as e:
            logger.error(f"[{self.faucet_name}] PTC Error: {e}")

    async def login(self) -> bool:
        """
        Authenticate with FireFaucet using credentials from settings.
        
        Implements stealth techniques including:
        - human_type() for text input with random delays
        - idle_mouse() for natural mouse movement
        - CAPTCHA solving with retry logic
        - Multiple verification methods (URL, DOM elements, error messages)
        
        Returns:
            bool: True if login successful, False otherwise
        """
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("fire_faucet")
            
        if not creds: 
            logger.error(f"[{self.faucet_name}] No credentials found")
            return False

        try:
            logger.info(f"[{self.faucet_name}] Navigating to login page...")
            await self.page.goto(f"{self.base_url}/login", wait_until="domcontentloaded", timeout=60000)
            
            # Handle Cloudflare if present
            await self.handle_cloudflare(max_wait_seconds=30)
            
            # Wait for login form to appear
            await self.page.wait_for_selector('#username', timeout=15000)
            
            # Updated selectors (as of 2026-01)
            logger.info(f"[{self.faucet_name}] Filling login form...")
            
            # Use human_type for stealth (avoid bot detection)
            await self.human_type('#username', creds['username'], delay_min=80, delay_max=150)
            await self.idle_mouse(duration=random.uniform(0.5, 1.0))
            await self.random_delay(0.3, 0.7)
            await self.human_type('#password', creds['password'], delay_min=80, delay_max=150)
            await self.idle_mouse(duration=random.uniform(0.5, 1.0))
            await self.random_delay(0.5, 1.0)
            
            # Handle CAPTCHA - site offers reCAPTCHA by default
            logger.info(f"[{self.faucet_name}] Solving login CAPTCHA...")
            await self.idle_mouse(duration=random.uniform(0.8, 1.5))
            captcha_result = await self.solver.solve_captcha(self.page)
            if not captcha_result:
                logger.warning(f"[{self.faucet_name}] Login CAPTCHA solving failed")
            else:
                logger.info(f"[{self.faucet_name}] Login CAPTCHA solved successfully")
            
            # Small delay to let token injection settle
            await self.random_delay(1.0, 2.0)
            
            # Check for button before trying to click
            submit_btn = self.page.locator('button.submitbtn, button[type="submit"]')
            if await submit_btn.count() > 0:
                 logger.info(f"[{self.faucet_name}] Submit button found. Clicking...")
                 # Ensure it's not disabled
                 if await submit_btn.is_disabled():
                     logger.warning(f"[{self.faucet_name}] Submit button is disabled! Waiting...")
                     await self.page.wait_for_function("document.querySelector('button.submitbtn, button[type=\"submit\"]').disabled === false", timeout=5000)

                 await self.human_like_click(submit_btn)
            else:
                 logger.warning(f"[{self.faucet_name}] Submit button NOT found via locator. Trying generic form submit...")
                 await self.page.evaluate("document.forms[0].submit()")

            # Wait for navigation or dashboard elements
            logger.info(f"[{self.faucet_name}] Waiting for post-login state...")
            
            # Poll for success (max 30 seconds)
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < 30:
                try:
                    url = self.page.url
                    # 1. Check URL
                    if "/dashboard" in url:
                        logger.info(f"[{self.faucet_name}] ✅ Login successful (Dashboard URL detected)!")
                        return True
                        
                    # 2. Check elements
                    if await self.page.locator(".user-balance, .level-progress").count() > 0:
                        logger.info(f"[{self.faucet_name}] ✅ Login successful (Dashboard elements detected)!")
                        return True
                        
                    # 3. Check for specific error messages
                    if await self.page.locator('.alert-danger, .error-message, .toast-error').count() > 0:
                        error_text = await self.page.locator('.alert-danger, .error-message, .toast-error').first.text_content()
                        logger.error(f"[{self.faucet_name}] Login error: {error_text}")
                        return False

                    # 4. Check if we are still on login page
                    if "/login" in url and (asyncio.get_event_loop().time() - start_time) > 10:
                         # If stuck on login for 10s, try verify button again
                         logger.debug(f"[{self.faucet_name}] Still on login page...")
                         
                except Exception:
                    pass 
                    
                await asyncio.sleep(1)
            
            logger.warning(f"[{self.faucet_name}] Login verification timed out. URL: {self.page.url}")
            return False

        except Exception as e:
            logger.error(f"FireFaucet login failed: {e}")
            return False


    

    def get_jobs(self):
        """
        Returns FireFaucet-specific jobs including daily bonus and shortlinks.
        """
        from core.orchestrator import Job
        import time
        
        jobs = []
        
        # Job 1: Faucet Claim - Highest Priority
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="claim_wrapper"
        ))
        
        # Job 2: Daily Bonus - High Priority (runs once per day)
        jobs.append(Job(
            priority=2,
            next_run=time.time() + 600,  # Start 10 minutes after first claim
            name=f"{self.faucet_name} Daily Bonus",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="daily_bonus_wrapper"
        ))
        
        # Job 3: PTC Ads - Medium Priority
        jobs.append(Job(
            priority=3,
            next_run=time.time() + 300,
            name=f"{self.faucet_name} PTC",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="ptc_wrapper"
        ))
        
        # Job 4: Shortlinks - Lower Priority
        jobs.append(Job(
            priority=4,
            next_run=time.time() + 1200,  # Start 20 minutes after first claim
            name=f"{self.faucet_name} Shortlinks",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="shortlinks_wrapper"
        ))
        
        # Job 5: Withdraw - Daily Priority
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="withdraw_wrapper"
        ))

        return jobs

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for FireFaucet."""
        try:
            logger.info(f"[{self.faucet_name}] Navigating to withdrawal...")
            await self.page.goto(f"{self.base_url}/withdraw")
            
            # FireFaucet requires selecting a coin. We'll try to withdraw the most common ones (BTC/LTC/DOGE)
            # Find all available coins that meet threshold
            coins = self.page.locator(".card:has(button:has-text('Withdraw'))")
            count = await coins.count()
            
            if count == 0:
                logger.info(f"[{self.faucet_name}] No coins ready for withdrawal.")
                return ClaimResult(success=True, status="No Balance", next_claim_minutes=1440)
            
            # Try to withdraw the first one available
            coin_btn = coins.first.locator("button:has-text('Withdraw')")
            await self.human_like_click(coin_btn)
            await self.page.wait_for_load_state()
            
            # Withdrawal Form
            # Detect processor (FaucetPay is usually best)
            processor = self.page.locator("select[name='processor']")
            if await processor.count() > 0:
                await processor.select_option("faucetpay")
                await asyncio.sleep(1)
            
            # Solve Captcha
            await self.solver.solve_captcha(self.page)
            
            submit = self.page.locator("button:has-text('Withdraw')").last
            await self.human_like_click(submit)
            
            # Check for success message
            success = self.page.locator(".alert-success, .toast-success")
            if await success.count() > 0:
                logger.info(f"[{self.faucet_name}] Withdrawal successful!")
                return ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440)
            
            return ClaimResult(success=False, status="Withdrawal Submitted but no success message", next_claim_minutes=120)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)
    
    async def daily_bonus_wrapper(self, page) -> ClaimResult:
        """Wrapper for daily bonus task."""
        from .base import ClaimResult
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login Failed", next_claim_minutes=30)
        
        try:
            await self.page.goto(f"{self.base_url}/daily")
            unlock = self.page.locator("body > div.row > div.col.s12.m12.l6 > div > center > a > button")
            if await unlock.count() > 0 and await unlock.is_visible():
                logger.info(f"[{self.faucet_name}] Unlocking Daily Bonus...")
                await self.human_like_click(unlock)
                await self.random_delay()
            
            turnstile_opt = self.page.locator("#select-turnstile")
            if await turnstile_opt.count() > 0:
                await turnstile_opt.click()
                await asyncio.sleep(1)
            
            await self.solver.solve_captcha(self.page)
            
            claim_btn = self.page.locator("body > div.row > div.col.s12.m12.l6 > div > center > form > button")
            if await claim_btn.count() > 0:
                await self.human_like_click(claim_btn)
                await self.random_delay(2, 4)
                logger.info(f"[{self.faucet_name}] Daily Bonus claimed!")
                return ClaimResult(success=True, status="Daily Bonus Claimed", next_claim_minutes=1440)  # 24 hours
            
            return ClaimResult(success=False, status="Daily Bonus Not Available", next_claim_minutes=1440)
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Daily Bonus Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=1440)
    
    async def shortlinks_wrapper(self, page) -> ClaimResult:
        """Wrapper for shortlinks task."""
        from .base import ClaimResult
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login Failed", next_claim_minutes=30)
        
        try:
            await self.claim_shortlinks()
            return ClaimResult(success=True, status="Shortlinks Processed", next_claim_minutes=120)  # 2 hours
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Shortlinks Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=120)


    async def claim(self) -> ClaimResult:
        """
        Execute the main faucet claim cycle for FireFaucet.
        
        Process:
        1. Navigate to daily bonus page and attempt to claim
        2. Navigate to faucet page
        3. Extract and validate balance using DataExtractor with fallbacks
        4. Extract and validate timer using DataExtractor with fallbacks
        5. If timer active, return with next_claim_minutes
        6. Solve CAPTCHA with retry logic
        7. Click claim button with stealth techniques
        8. Verify success and extract updated balance
        
        Stealth features:
        - idle_mouse() between interactions
        - human_like_click() for button interactions
        - Random delays for natural behavior
        - CAPTCHA retry on failure
        
        Returns:
            ClaimResult: Contains success status, message, next claim time, amount, and balance
        """
        try:
            # First, check Daily Bonus
            await self.page.goto(f"{self.base_url}/daily")
            
            # Check for "Unlock" button
            unlock = self.page.locator("body > div.row > div.col.s12.m12.l6 > div > center > a > button")
            if await unlock.count() > 0 and await unlock.is_visible():
                logger.info(f"[{self.faucet_name}] Unlocking Daily Bonus...")
                await self.human_like_click(unlock)
                await self.random_delay()

            # Captcha selection (prefer Turnstile)
            turnstile_opt = self.page.locator("#select-turnstile")
            if await turnstile_opt.count() > 0:
                await turnstile_opt.click()
                await asyncio.sleep(1)

            await self.solver.solve_captcha(self.page)
            
            # Daily Bonus Button
            claim_btn = self.page.locator("body > div.row > div.col.s12.m12.l6 > div > center > form > button")
            if await claim_btn.count() > 0:
                await self.human_like_click(claim_btn)
                await self.random_delay(2, 4)
            
            # Now, Faucet Claim
            logger.info(f"[{self.faucet_name}] Navigating to faucet page...")
            await self.page.goto(f"{self.base_url}/faucet")
            
            # Extract balance with fallback selectors
            balance_selectors = [
                ".user-balance",
                ".balance-text",
                "[class*='balance']",
                "#balance",
                ".navbar .balance"
            ]
            balance = await self.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
            logger.info(f"[{self.faucet_name}] Current balance: {balance}")
            
            # Extract timer with fallback selectors
            timer_selectors = [
                ".fa-clock + span",
                "#claim_timer",
                ".timer",
                "[class*='timer']",
                "[class*='countdown']"
            ]
            wait = await self.get_timer(timer_selectors[0], fallback_selectors=timer_selectors[1:])
            logger.info(f"[{self.faucet_name}] Timer status: {wait} minutes")
            
            if wait > 0:
                 logger.info(f"[{self.faucet_name}] Claim not ready, waiting {wait} minutes")
                 return ClaimResult(success=True, status="Timer Active", next_claim_minutes=wait, balance=balance)

            # Add stealth delay before solving CAPTCHA
            await self.idle_mouse(duration=random.uniform(1.0, 2.0))
            logger.info(f"[{self.faucet_name}] Solving CAPTCHA...")
            captcha_result = await self.solver.solve_captcha(self.page)
            if not captcha_result:
                logger.warning(f"[{self.faucet_name}] CAPTCHA solving failed, retrying...")
                await self.random_delay(2, 4)
                captcha_result = await self.solver.solve_captcha(self.page)
                if not captcha_result:
                    logger.error(f"[{self.faucet_name}] CAPTCHA solving failed after retry")
                    return ClaimResult(success=False, status="CAPTCHA Failed", next_claim_minutes=5, balance=balance)
            
            logger.info(f"[{self.faucet_name}] CAPTCHA solved successfully")
            await self.idle_mouse(duration=random.uniform(0.5, 1.5))
            
            # Faucet Claim Button with fallback selectors
            faucet_btn_selectors = [
                "#get_reward_button",
                "#faucet_btn", 
                "button:has-text('Claim')",
                "button[type='submit']",
                ".claim-button"
            ]
            faucet_btn = None
            for selector in faucet_btn_selectors:
                btn = self.page.locator(selector)
                if await btn.count() > 0:
                    faucet_btn = btn
                    logger.debug(f"[{self.faucet_name}] Found claim button with selector: {selector}")
                    break
            
            if faucet_btn and await faucet_btn.count() > 0:
                logger.info(f"[{self.faucet_name}] Clicking faucet reward button...")
                await self.human_like_click(faucet_btn)
                await self.random_delay(3, 5)
                
                # Check for success with multiple selectors
                success_selectors = [".success_msg", ".alert-success", ".toast-success", "[class*='success']"]
                success_found = False
                for sel in success_selectors:
                    if await self.page.locator(sel).count() > 0:
                        success_msg = await self.page.locator(sel).first.text_content()
                        logger.info(f"[{self.faucet_name}] ✅ Faucet claimed successfully: {success_msg}")
                        success_found = True
                        break
                
                if success_found:
                    # Get updated balance
                    new_balance = await self.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
                    logger.info(f"[{self.faucet_name}] New balance: {new_balance}")
                    return ClaimResult(success=True, status="Claimed", next_claim_minutes=30, balance=new_balance)
                
                logger.warning(f"[{self.faucet_name}] Claim verification failed - no success message found")
                await self.page.screenshot(path=f"claim_failed_{self.faucet_name}.png", full_page=True)
            else:
                logger.warning(f"[{self.faucet_name}] Faucet button not found with any selector")
                await self.page.screenshot(path=f"claim_btn_missing_{self.faucet_name}.png", full_page=True)
                
            return ClaimResult(success=False, status="Faucet Ready but Failed", next_claim_minutes=5, balance=balance)
            
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Claim failed with error: {e}", exc_info=True)
            await self.page.screenshot(path=f"error_{self.faucet_name}.png", full_page=True)
            
            # Categorize errors for better next_claim_minutes
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ["timeout", "network", "connection"]):
                logger.warning(f"[{self.faucet_name}] Network error detected, will retry in 5 minutes")
                return ClaimResult(success=False, status=f"Network Error: {str(e)}", next_claim_minutes=5)
            elif "captcha" in error_str:
                logger.warning(f"[{self.faucet_name}] CAPTCHA error detected, will retry in 10 minutes")
                return ClaimResult(success=False, status=f"CAPTCHA Error: {str(e)}", next_claim_minutes=10)
            else:
                logger.error(f"[{self.faucet_name}] Unknown error, will retry in 30 minutes")
                return ClaimResult(success=False, status=f"Error: {str(e)}", next_claim_minutes=30)

    async def claim_shortlinks(self):
        """Attempts to claim available shortlinks on FireFaucet."""
        try:
            logger.info(f"[{self.faucet_name}] Checking Shortlinks...")
            await self.page.goto(f"{self.base_url}/shortlinks")
            
            # FireFaucet Shortlink structure
            # List of links with rewards
            links = self.page.locator("a.btn.btn-primary:has-text('Visit Link')") # or similar
            if await links.count() == 0:
                 # Backup selector
                 links = self.page.locator(".card-body a[href*='/shortlink/']")
            
            count = await links.count()
            if count == 0:
                logger.info(f"[{self.faucet_name}] No shortlinks available.")
                return

            logger.info(f"[{self.faucet_name}] Found {count} shortlinks. Trying top 3...")
            
            blocker = getattr(self.page, "resource_blocker", getattr(self.page.context, "resource_blocker", None))
            solver = ShortlinkSolver(self.page, blocker=blocker, captcha_solver=self.solver)
            
            for i in range(min(3, count)):
                # Re-query
                links = self.page.locator("a.btn.btn-primary:has-text('Visit Link')")
                if await links.count() == 0: links = self.page.locator(".card-body a[href*='/shortlink/']")
                
                if await links.count() <= i: break
                
                # Navigate to the intermediate page
                await links.nth(i).click()
                await self.page.wait_for_load_state()
                
                # FireFaucet often has an intermediate page with a captcha before the actual shortlink
                # Check for "Generate Link" or Captcha
                if await self.page.query_selector("iframe[src*='turnstile'], iframe[src*='recaptcha']"):
                     await self.solver.solve_captcha(self.page)
                
                # Check for buttons to proceed to actual shortlink
                # e.g. "Click here to continue"
                
                # Let the solver take over for the external link
                # We need to detect when we've left FireFaucet or when the actual shortlink starts
                # For now, simplistic approach: call solve on current URL
                if await solver.solve(self.page.url, success_patterns=["firefaucet.win/shortlinks", "/shortlinks"]):
                    logger.info(f"[{self.faucet_name}] Shortlink {i+1} Solved!")
                    await self.page.goto(f"{self.base_url}/shortlinks")
                else:
                    logger.warning(f"[{self.faucet_name}] Shortlink {i+1} Failed.")
                    await self.page.goto(f"{self.base_url}/shortlinks")
                    
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Shortlink error: {e}")

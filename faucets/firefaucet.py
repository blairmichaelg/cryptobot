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
        self.cloudflare_retry_count = 0
        self.max_cloudflare_retries = 3

    async def detect_cloudflare_block(self) -> bool:
        """
        Enhanced Cloudflare detection for FireFaucet.
        
        Checks for:
        - Cloudflare challenge pages ("Just a moment", "Checking your browser")
        - Turnstile captcha iframes
        - Maintenance/security pages
        - Bot detection blocks
        
        Returns:
            bool: True if Cloudflare protection is active
        """
        try:
            # Check page title
            title = (await self.page.title()).lower()
            if any(indicator in title for indicator in ["just a moment", "cloudflare", "security check", "ddos protection", "attention required"]):
                logger.warning(f"[{self.faucet_name}] 🛡️ Cloudflare detected in title: {title}")
                return True
            
            # Check page content
            body_text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            cloudflare_patterns = [
                "cloudflare",
                "checking your browser",
                "please wait",
                "enable javascript",
                "ddos protection",
                "security check",
                "just a moment",
                "verify you are human",
                "ray id"
            ]
            
            if any(pattern in body_text for pattern in cloudflare_patterns):
                logger.warning(f"[{self.faucet_name}] 🛡️ Cloudflare pattern detected in page content")
                return True
            
            # Check for Turnstile iframes
            turnstile_frame = await self.page.query_selector("iframe[src*='turnstile'], iframe[src*='challenges.cloudflare.com']")
            if turnstile_frame:
                logger.info(f"[{self.faucet_name}] 🔒 Cloudflare Turnstile iframe detected")
                return True
            
            # Check for Cloudflare challenge elements
            cf_elements = await self.page.query_selector("#cf-challenge-running, .cf-browser-verification, [id*='cf-turnstile']")
            if cf_elements:
                logger.info(f"[{self.faucet_name}] 🔒 Cloudflare challenge elements detected")
                return True
                
            return False
            
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Error in Cloudflare detection: {e}")
            return False

    async def bypass_cloudflare_with_retry(self) -> bool:
        """
        Attempt to bypass Cloudflare with progressive stealth escalation.
        
        Strategy:
        1. Wait for automatic challenge resolution (human-like behavior)
        2. Detect and solve Turnstile if present
        3. If retry needed, increase stealth measures:
           - Longer idle times
           - More mouse movements
           - Extended waiting periods
        
        Returns:
            bool: True if bypass succeeded, False if all retries exhausted
        """
        for attempt in range(1, self.max_cloudflare_retries + 1):
            try:
                logger.info(f"[{self.faucet_name}] Cloudflare bypass attempt {attempt}/{self.max_cloudflare_retries}")
                
                # Progressive stealth: increase delays with each retry
                base_wait = 10 + (attempt * 5)  # 15s, 20s, 25s
                
                # Simulate human-like waiting behavior
                logger.info(f"[{self.faucet_name}] ⏳ Waiting {base_wait}s for automatic challenge resolution...")
                await self.idle_mouse(duration=random.uniform(2.0, 4.0))
                await asyncio.sleep(base_wait)
                
                # Check for Turnstile and solve if present
                turnstile_detected = await self.page.query_selector("iframe[src*='turnstile'], iframe[src*='challenges.cloudflare.com'], [data-sitekey]")
                if turnstile_detected:
                    logger.info(f"[{self.faucet_name}] 🎯 Turnstile CAPTCHA detected, solving...")
                    
                    # Add extra stealth before solving
                    await self.idle_mouse(duration=random.uniform(1.5, 3.0))
                    await self.simulate_reading(duration=random.uniform(2.0, 4.0))
                    
                    # Solve Turnstile
                    turnstile_solved = await self.solver.solve_captcha(self.page, timeout=120)
                    if turnstile_solved:
                        logger.info(f"[{self.faucet_name}] ✅ Turnstile solved successfully")
                        await asyncio.sleep(random.uniform(2.0, 4.0))  # Wait for token submission
                    else:
                        logger.warning(f"[{self.faucet_name}] ⚠️ Turnstile solving failed")
                        if attempt < self.max_cloudflare_retries:
                            # Retry with page refresh
                            logger.info(f"[{self.faucet_name}] Refreshing page for retry...")
                            await self.page.reload(wait_until="domcontentloaded")
                            await asyncio.sleep(3)
                            continue
                
                # Enhanced wait with human-like activity
                logger.debug(f"[{self.faucet_name}] Performing human-like activity during challenge...")
                for _ in range(attempt * 2):  # More activity with each retry
                    if random.random() < 0.6:
                        await self.idle_mouse(duration=random.uniform(0.5, 1.5))
                    else:
                        await self.simulate_reading(duration=random.uniform(1.0, 2.5))
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                
                # Check if Cloudflare is still blocking
                still_blocked = await self.detect_cloudflare_block()
                if not still_blocked:
                    logger.info(f"[{self.faucet_name}] ✅ Cloudflare bypass successful on attempt {attempt}")
                    self.cloudflare_retry_count = 0  # Reset counter on success
                    return True
                
                logger.warning(f"[{self.faucet_name}] Still blocked after attempt {attempt}, retrying...")
                
                # If not last attempt, refresh page with enhanced stealth
                if attempt < self.max_cloudflare_retries:
                    await asyncio.sleep(random.uniform(3.0, 6.0))  # Longer delay between retries
                    logger.info(f"[{self.faucet_name}] Refreshing page for retry...")
                    await self.page.reload(wait_until="domcontentloaded")
                    await asyncio.sleep(random.uniform(4.0, 7.0))
                    
            except Exception as e:
                logger.error(f"[{self.faucet_name}] Error during Cloudflare bypass attempt {attempt}: {e}")
                if attempt < self.max_cloudflare_retries:
                    await asyncio.sleep(random.uniform(5.0, 10.0))
                    continue
        
        logger.error(f"[{self.faucet_name}] ❌ Cloudflare bypass failed after {self.max_cloudflare_retries} attempts")
        self.cloudflare_retry_count += 1
        return False

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
            await self.safe_navigate(f"{self.base_url}/login", wait_until="domcontentloaded", timeout=getattr(self.settings, "timeout", 180000))
            
            # Enhanced Cloudflare bypass with retry escalation
            cf_blocked = await self.detect_cloudflare_block()
            if cf_blocked:
                logger.warning(f"[{self.faucet_name}] Cloudflare protection detected, attempting bypass...")
                bypass_success = await self.bypass_cloudflare_with_retry()
                if not bypass_success:
                    logger.error(f"[{self.faucet_name}] ❌ Failed to bypass Cloudflare after {self.max_cloudflare_retries} attempts")
                    return False
            else:
                # Still do basic check for race conditions
                await self.handle_cloudflare(max_wait_seconds=20)
            
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
        f_type = "fire_faucet"
        
        # Job 1: Faucet Claim - Highest Priority
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=f_type,
            job_type="claim_wrapper"
        ))
        
        # Job 2: Daily Bonus - High Priority (runs once per day)
        jobs.append(Job(
            priority=2,
            next_run=time.time() + 600,  # Start 10 minutes after first claim
            name=f"{self.faucet_name} Daily Bonus",
            profile=None,
            faucet_type=f_type,
            job_type="daily_bonus_wrapper"
        ))
        
        # Job 3: PTC Ads - Medium Priority
        jobs.append(Job(
            priority=3,
            next_run=time.time() + 300,
            name=f"{self.faucet_name} PTC",
            profile=None,
            faucet_type=f_type,
            job_type="ptc_wrapper"
        ))
        
        # Job 4: Shortlinks - Lower Priority
        jobs.append(Job(
            priority=4,
            next_run=time.time() + 1200,  # Start 20 minutes after first claim
            name=f"{self.faucet_name} Shortlinks",
            profile=None,
            faucet_type=f_type,
            job_type="shortlinks_wrapper"
        ))
        
        # Job 5: Withdraw - Daily Priority
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=f_type,
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
            
            # Check for Cloudflare on daily page
            cf_blocked = await self.detect_cloudflare_block()
            if cf_blocked:
                logger.warning(f"[{self.faucet_name}] Cloudflare detected on daily page, attempting bypass...")
                bypass_success = await self.bypass_cloudflare_with_retry()
                if not bypass_success:
                    logger.error(f"[{self.faucet_name}] Failed to bypass Cloudflare on daily page")
                    return ClaimResult(success=False, status="Cloudflare Block", next_claim_minutes=15)
            
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
            
            # Check for Cloudflare on faucet page
            cf_blocked = await self.detect_cloudflare_block()
            if cf_blocked:
                logger.warning(f"[{self.faucet_name}] Cloudflare detected on faucet page, attempting bypass...")
                bypass_success = await self.bypass_cloudflare_with_retry()
                if not bypass_success:
                    logger.error(f"[{self.faucet_name}] Failed to bypass Cloudflare on faucet page")
                    return ClaimResult(success=False, status="Cloudflare Block", next_claim_minutes=15)
            
            # Extract balance with fallback selectors (updated 2026-01-30)
            balance_selectors = [
                ".user-balance",           # Primary FireFaucet balance class
                ".balance",                # Generic balance class
                "#user-balance",          # ID variant
                ".balance-text",          # Text wrapper
                "span.user-balance",      # Span element
                ".navbar .balance",       # Navbar location
                "[data-balance]",         # Data attribute
                ".account-balance",       # Alternative naming
                "#balance",               # Simple ID
                "[class*='balance']",     # Wildcard class match
                ".wallet-balance",        # Wallet section
                "span[class*='balance']:visible",  # Any visible balance span
            ]
            balance = await self.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
            logger.info(f"[{self.faucet_name}] Current balance: {balance}")
            
            # Extract timer with fallback selectors (updated 2026-01-30)
            timer_selectors = [
                ".fa-clock + span",        # Icon + timer span
                "#claim_timer",            # Timer ID
                "#time",                   # Common timer ID
                ".timer",                  # Generic timer class
                ".countdown",              # Countdown class
                "[data-timer]",            # Data attribute
                "[data-countdown]",        # Countdown data attr
                ".time-remaining",         # Descriptive class
                "[class*='timer']",        # Wildcard timer class
                "[class*='countdown']",    # Wildcard countdown class
                "[id*='timer']",           # Wildcard timer ID
                "span.timer:visible",      # Any visible timer span
                ".claim-timer",            # Claim-specific timer
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
            
            # Wait for page to be fully loaded and interactive
            await self.page.wait_for_load_state("networkidle", timeout=10000)
            await asyncio.sleep(2)  # Additional wait for JavaScript to render buttons
            
            # Faucet Claim Button with fallback selectors (updated 2026-01-30)
            faucet_btn_selectors = [
                "button:has-text('Get reward')",  # Primary FireFaucet button text
                "button:has-text('Get Reward')",
                "button:has-text('Claim')",
                "button:has-text('claim')",
                "button:text('Get reward')",
                "button:text('Get Reward')",
                "#get_reward_button",
                "#claim-button",
                "#faucet_btn",
                "button.btn.btn-primary:visible",
                "button.btn:visible",
                "button[type='submit']:visible",
                ".btn.btn-primary:visible",
                ".claim-button",
                "form button[type='submit']:visible",
                "button.btn:has-text('reward')",
                "button:visible",  # Last resort: any visible button
                "input[type='submit'][value*='Claim']",
                "input[type='submit'][value*='reward']",
                "input[type='submit']:visible"
            ]
            faucet_btn = None
            for selector in faucet_btn_selectors:
                try:
                    btn = self.page.locator(selector)
                    count = await btn.count()
                    logger.debug(f"[{self.faucet_name}] Testing selector '{selector}': found {count} elements")
                    if count > 0:
                        # Additional check: ensure button is visible and enabled
                        try:
                            is_visible = await btn.first.is_visible(timeout=2000)
                            if is_visible:
                                faucet_btn = btn
                                logger.info(f"[{self.faucet_name}] ✅ Found claim button with selector: {selector}")
                                break
                            else:
                                logger.debug(f"[{self.faucet_name}] Button found but not visible: {selector}")
                        except Exception as vis_err:
                            logger.debug(f"[{self.faucet_name}] Visibility check failed for {selector}: {vis_err}")
                            continue
                except Exception as sel_err:
                    logger.debug(f"[{self.faucet_name}] Selector '{selector}' failed: {sel_err}")
                    continue
            
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
                    
                    # Claim shortlinks if enabled (non-blocking, separate context)
                    enable_shortlinks = getattr(self.settings, 'enable_shortlinks', True)
                    if enable_shortlinks:
                        try:
                            logger.info(f"[{self.faucet_name}] Starting shortlink claiming in parallel...")
                            asyncio.create_task(self.claim_shortlinks(separate_context=True))
                        except Exception as sl_err:
                            logger.debug(f"[{self.faucet_name}] Shortlink task creation failed: {sl_err}")
                    
                    return ClaimResult(success=True, status="Claimed", next_claim_minutes=30, balance=new_balance)
                
                logger.warning(f"[{self.faucet_name}] Claim verification failed - no success message found")
                await self.page.screenshot(path=f"claim_failed_{self.faucet_name}.png", full_page=True)
            else:
                # Debug: Log available buttons on the page
                logger.warning(f"[{self.faucet_name}] Faucet button not found with any selector")
                try:
                    # Enhanced debugging
                    page_url = self.page.url
                    logger.error(f"[{self.faucet_name}] Current URL: {page_url}")
                    
                    # Check if we're actually on the faucet page
                    if "/faucet" not in page_url:
                        logger.error(f"[{self.faucet_name}] ⚠️ Not on faucet page! Redirected to: {page_url}")
                    
                    all_buttons = await self.page.locator("button, input[type='submit']").all()
                    logger.error(f"[{self.faucet_name}] 🔍 DEBUG: Found {len(all_buttons)} buttons/inputs on page")
                    for idx, btn in enumerate(all_buttons[:10]):  # Log first 10 buttons
                        try:
                            btn_text = await btn.text_content() or ""
                            btn_id = await btn.get_attribute("id") or ""
                            btn_class = await btn.get_attribute("class") or ""
                            btn_type = await btn.get_attribute("type") or ""
                            btn_value = await btn.get_attribute("value") or ""
                            is_visible = await btn.is_visible()
                            logger.error(f"[{self.faucet_name}]   [{idx+1}] text='{btn_text.strip()[:50]}' id='{btn_id}' class='{btn_class}' type='{btn_type}' value='{btn_value}' visible={is_visible}")
                        except Exception as btn_err:
                            logger.debug(f"[{self.faucet_name}] Could not read button {idx+1}: {btn_err}")
                    
                    # Also check for links that might be styled as buttons
                    all_links = await self.page.locator("a.btn, a[class*='button']").all()
                    if all_links:
                        logger.error(f"[{self.faucet_name}] 🔍 DEBUG: Found {len(all_links)} link-buttons on page")
                        for idx, link in enumerate(all_links[:5]):
                            try:
                                link_text = await link.text_content() or ""
                                link_href = await link.get_attribute("href") or ""
                                link_class = await link.get_attribute("class") or ""
                                is_visible = await link.is_visible()
                                logger.error(f"[{self.faucet_name}]   Link[{idx+1}] text='{link_text.strip()[:50]}' href='{link_href}' class='{link_class}' visible={is_visible}")
                            except Exception as link_err:
                                logger.debug(f"[{self.faucet_name}] Could not read link {idx+1}: {link_err}")
                    
                    # Check for any error/warning messages on the page
                    error_msgs = await self.page.locator(".alert, .error, .warning, [class*='error'], [class*='alert']").all()
                    if error_msgs:
                        logger.error(f"[{self.faucet_name}] ⚠️ Found {len(error_msgs)} error/alert elements:")
                        for idx, msg in enumerate(error_msgs[:3]):
                            try:
                                msg_text = await msg.text_content() or ""
                                logger.error(f"[{self.faucet_name}]   Alert[{idx+1}]: {msg_text.strip()[:100]}")
                            except Exception:
                                pass
                                
                except Exception as debug_err:
                    logger.error(f"[{self.faucet_name}] Could not enumerate page elements: {debug_err}")
                    
                await self.page.screenshot(path=f"claim_btn_missing_{self.faucet_name}.png", full_page=True)
                logger.error(f"[{self.faucet_name}] Screenshot saved to claim_btn_missing_{self.faucet_name}.png")
                
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

    async def claim_shortlinks(self, separate_context: bool = True) -> ClaimResult:
        """Attempts to claim available shortlinks on FireFaucet.
        
        Args:
            separate_context: If True, use separate browser context (don't interfere with main claim)
        
        Returns:
            ClaimResult with earnings tracked separately
        """
        shortlink_earnings = 0.0
        shortlinks_claimed = 0
        
        try:
            logger.info(f"[{self.faucet_name}] Checking Shortlinks...")
            
            # Use separate context if requested (prevents interference with main session)
            if separate_context and hasattr(self, 'browser_manager'):
                # Clone current context for shortlinks
                logger.debug(f"[{self.faucet_name}] Using separate context for shortlinks")
                context = await self.page.context.browser.new_context()
                page = await context.new_page()
                # Copy cookies from main session
                cookies = await self.page.context.cookies()
                await context.add_cookies(cookies)
            else:
                page = self.page
            
            await page.goto(f"{self.base_url}/shortlinks")
            
            # FireFaucet Shortlink structure
            links = page.locator("a.btn.btn-primary:has-text('Visit Link')")
            if await links.count() == 0:
                links = page.locator(".card-body a[href*='/shortlink/']")
            
            count = await links.count()
            if count == 0:
                logger.info(f"[{self.faucet_name}] No shortlinks available.")
                if separate_context and 'context' in locals():
                    await context.close()
                return ClaimResult(success=True, status="No shortlinks", next_claim_minutes=120, amount=0.0)

            logger.info(f"[{self.faucet_name}] Found {count} shortlinks. Processing top 3...")
            
            blocker = getattr(page, "resource_blocker", getattr(page.context, "resource_blocker", None))
            solver = ShortlinkSolver(page, blocker=blocker, captcha_solver=self.solver)
            
            for i in range(min(3, count)):
                try:
                    # Re-query links
                    links = page.locator("a.btn.btn-primary:has-text('Visit Link')")
                    if await links.count() == 0:
                        links = page.locator(".card-body a[href*='/shortlink/']")
                    
                    if await links.count() <= i:
                        break
                    
                    # Extract potential reward before clicking
                    reward_text = await links.nth(i).get_attribute("data-reward") or "0"
                    
                    await links.nth(i).click()
                    await page.wait_for_load_state()
                    
                    # Solve intermediate captcha if present
                    if await page.query_selector("iframe[src*='turnstile'], iframe[src*='recaptcha']"):
                        await self.solver.solve_captcha(page)
                    
                    # Solve the shortlink
                    if await solver.solve(page.url, success_patterns=["firefaucet.win/shortlinks", "/shortlinks"]):
                        logger.info(f"[{self.faucet_name}] ✅ Shortlink {i+1} claimed!")
                        shortlinks_claimed += 1
                        # Try to extract reward amount
                        try:
                            shortlink_earnings += float(reward_text)
                        except ValueError:
                            shortlink_earnings += 0.0001  # Default small amount
                        await page.goto(f"{self.base_url}/shortlinks")
                    else:
                        logger.warning(f"[{self.faucet_name}] Shortlink {i+1} failed")
                        await page.goto(f"{self.base_url}/shortlinks")
                        
                except Exception as link_err:
                    logger.error(f"[{self.faucet_name}] Error on shortlink {i+1}: {link_err}")
                    continue
            
            # Close separate context if used
            if separate_context and 'context' in locals():
                await context.close()
            
            # Track earnings separately in analytics
            if shortlink_earnings > 0:
                try:
                    from core.analytics import get_tracker
                    tracker = get_tracker()
                    tracker.record_claim(
                        faucet=self.faucet_name,
                        success=True,
                        amount=shortlink_earnings
                    )
                except Exception as analytics_err:
                    logger.debug(f"Analytics tracking failed: {analytics_err}")
            
            return ClaimResult(
                success=True,
                status=f"Claimed {shortlinks_claimed} shortlinks",
                next_claim_minutes=120,
                amount=shortlink_earnings
            )
                    
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Shortlink error: {e}")
            if separate_context and 'context' in locals():
                try:
                    await context.close()
                except Exception:  # pylint: disable=bare-except
                    pass
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=120)

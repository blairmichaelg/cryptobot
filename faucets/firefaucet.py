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
            # Check page title for challenge indicators
            title = (await self.page.title()).lower()
            challenge_titles = ["just a moment", "security check", "ddos protection", "attention required", "checking your browser"]
            if any(indicator in title for indicator in challenge_titles):
                logger.warning(f"[{self.faucet_name}] 🛡️ Cloudflare detected in title: {title}")
                return True
            
            # Check page content for CHALLENGE-SPECIFIC patterns (not just "cloudflare" which appears in footers)
            body_text = await self.page.evaluate("() => document.body.innerText.toLowerCase()")
            challenge_patterns = [
                "checking your browser",
                "please wait while we check your browser",
                "just a moment",
                "verify you are human",
                "enable javascript and cookies",
                "this process is automatic"
            ]
            
            # Must match challenge pattern AND have short page text (challenge pages are minimal)
            if any(pattern in body_text for pattern in challenge_patterns):
                # Challenge pages are typically very short (< 1000 chars)
                # Normal pages mention "cloudflare" in footer but have much more content
                if len(body_text) < 1000:
                    logger.warning(f"[{self.faucet_name}] 🛡️ Cloudflare challenge detected in page content (length: {len(body_text)})")
                    return True
                else:
                    logger.debug(f"[{self.faucet_name}] Page mentions Cloudflare but has normal content (length: {len(body_text)}), not a challenge")
            
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
                
                # Simulate human-like waiting behavior with micro-interactions
                logger.info(f"[{self.faucet_name}] ⏳ Waiting {base_wait}s for automatic challenge resolution...")
                await self.idle_mouse(duration=random.uniform(2.0, 4.0))
                await self.human_wait(base_wait, with_interactions=True)
                
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
                            await self.page.reload()
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
                    await self.page.reload()
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
            nav_success = await self.safe_navigate(f"{self.base_url}/login", timeout=getattr(self.settings, "timeout", 180000))
            if not nav_success:
                logger.error(f"[{self.faucet_name}] Failed to navigate to login page")
                return False
            
            # Log current URL for debugging
            current_url = self.page.url
            logger.debug(f"[{self.faucet_name}] Current URL after navigation: {current_url}")
            
            # Check if already logged in (redirected to dashboard)
            if "/dashboard" in current_url or "/home" in current_url:
                logger.info(f"[{self.faucet_name}] ✅ Already logged in (session valid)")
                return True
            
            # Also check for dashboard elements on current page (in case URL doesn't contain /dashboard)
            try:
                if await self.page.locator(".user-balance, .level-progress, .dashboard-content").count() > 0:
                    logger.info(f"[{self.faucet_name}] ✅ Already logged in (dashboard elements detected)")
                    return True
            except Exception:
                pass
            
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
            
            # Check for adblock redirect before looking for login form
            if "/adblock" in self.page.url:
                logger.error(f"[{self.faucet_name}] ❌ Redirected to adblock page. Site blocking us as adblock user.")
                logger.info(f"[{self.faucet_name}] This shouldn't happen with image_bypass enabled. Check config.")
                return False
            
            # Warm up the page to establish organic behavioral baseline
            await self.warm_up_page()
            
            # Wait for login form to appear - reduced timeout for faster failure detection
            try:
                await self.page.wait_for_selector('#username', timeout=20000)
            except Exception as e:
                # Try alternate selectors if #username fails
                logger.warning(f"[{self.faucet_name}] #username not found, trying alternate selectors...")
                alt_selectors = ["input[name='username']", "input[type='text']", "#login-username"]
                found = False
                for sel in alt_selectors:
                    try:
                        if await self.page.locator(sel).count() > 0:
                            logger.info(f"[{self.faucet_name}] Found login field with selector: {sel}")
                            found = True
                            break
                    except:
                        pass
                if not found:
                    # Log page info for debugging
                    try:
                        title = await self.page.title()
                        url = self.page.url
                        logger.error(f"[{self.faucet_name}] Login form not found. Title: {title}, URL: {url}")
                        # Check if we hit adblock page
                        if "/adblock" in url:
                            logger.error(f"[{self.faucet_name}] Site detected us as using adblock!")
                    except:
                        pass
                    raise e
            
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
            
            # Captcha selection (prefer Turnstile) - click label to avoid interception
            turnstile_label = self.page.locator("label[for='select-turnstile']")
            if await turnstile_label.count() > 0:
                logger.debug(f"[{self.faucet_name}] Selecting Turnstile CAPTCHA via label (daily bonus)")
                await turnstile_label.click()
                await asyncio.sleep(1)
            else:
                # Fallback to JavaScript
                turnstile_opt = self.page.locator("#select-turnstile")
                if await turnstile_opt.count() > 0:
                    logger.debug(f"[{self.faucet_name}] Selecting Turnstile CAPTCHA via JavaScript (daily bonus)")
                    await self.page.evaluate("document.getElementById('select-turnstile').checked = true; change_captcha('turnstile');")
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
            
            # Warm up page with natural browsing behavior
            await self.warm_up_page()
            
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
            # Click the label instead of the radio button to avoid interception issues
            turnstile_label = self.page.locator("label[for='select-turnstile']")
            if await turnstile_label.count() > 0:
                logger.debug(f"[{self.faucet_name}] Selecting Turnstile CAPTCHA via label")
                await turnstile_label.click()
                await asyncio.sleep(1)
            else:
                # Fallback to direct radio button selection via JavaScript
                turnstile_opt = self.page.locator("#select-turnstile")
                if await turnstile_opt.count() > 0:
                    logger.debug(f"[{self.faucet_name}] Selecting Turnstile CAPTCHA via JavaScript")
                    await self.page.evaluate("document.getElementById('select-turnstile').checked = true; change_captcha('turnstile');")
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

            # Wait extra time for dynamic content to load
            await self.human_wait(5)

            # Check for Cloudflare on faucet page
            cf_blocked = await self.detect_cloudflare_block()
            if cf_blocked:
                logger.warning(f"[{self.faucet_name}] Cloudflare detected on faucet page, attempting bypass...")
                bypass_success = await self.bypass_cloudflare_with_retry()
                if not bypass_success:
                    logger.error(f"[{self.faucet_name}] Failed to bypass Cloudflare on faucet page")
                    return ClaimResult(success=False, status="Cloudflare Block", next_claim_minutes=15)

            # Wait for faucet content to be present - look specifically for
            # #get_reward_button which is the known FireFaucet claim button
            try:
                logger.info(f"[{self.faucet_name}] Waiting for faucet interface to load...")
                # Try the specific reward button first, then fall back to generic
                try:
                    await self.page.wait_for_selector("#get_reward_button", timeout=15000)
                    logger.info(f"[{self.faucet_name}] Found #get_reward_button")
                except Exception:
                    # Fall back to generic button/submit detection
                    await self.page.wait_for_selector("button, input[type='submit']", timeout=10000)
                logger.info(f"[{self.faucet_name}] Faucet interface loaded")
            except Exception as e:
                logger.warning(f"[{self.faucet_name}] Timeout waiting for faucet interface: {e}")
                # Don't fail yet, continue with a warning
            
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

            # Select Turnstile CAPTCHA if available (cheaper and faster to solve)
            turnstile_label = self.page.locator("label[for='select-turnstile']")
            if await turnstile_label.count() > 0:
                logger.debug(f"[{self.faucet_name}] Selecting Turnstile CAPTCHA via label on faucet page")
                await turnstile_label.click()
                await asyncio.sleep(1)
            else:
                turnstile_opt = self.page.locator("#select-turnstile")
                if await turnstile_opt.count() > 0:
                    logger.debug(f"[{self.faucet_name}] Selecting Turnstile CAPTCHA via JavaScript on faucet page")
                    await self.page.evaluate("document.getElementById('select-turnstile').checked = true; change_captcha('turnstile');")
                    await asyncio.sleep(1)

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
            await asyncio.sleep(1)  # Brief wait for token injection
            
            # Try to manually enable the button by removing disabled attribute
            try:
                await self.page.evaluate("""
                    const btn = document.querySelector('button[type="submit"]');
                    if (btn && btn.disabled) {
                        btn.disabled = false;
                        btn.removeAttribute('disabled');
                        console.log('Button manually enabled');
                    }
                """)
                logger.info(f"[{self.faucet_name}] Manually enabled submit button")
            except Exception as e:
                logger.warning(f"[{self.faucet_name}] Could not manually enable button: {e}")
            
            # Faucet Claim Button with fallback selectors (updated 2026-02)
            # CRITICAL: #get_reward_button is the confirmed FireFaucet button ID.
            # It has a JavaScript countdown timer (9s) that keeps it disabled after page load.
            faucet_btn_selectors = [
                "#get_reward_button",             # Primary - confirmed FireFaucet button ID
                "button:has-text('Get reward')",  # Primary FireFaucet button text
                "button:has-text('Get Reward')",
                "button:has-text('Claim')",
                "button:has-text('claim')",
                "button:text('Get reward')",
                "button:text('Get Reward')",
                "#claim-button",
                "#faucet_btn",
                "button.btn.btn-primary:visible",
                "button.btn:visible",
                "button[type='submit']:visible",
                ".btn.btn-primary:visible",
                ".claim-button",
                "form button[type='submit']:visible",
                "button.btn:has-text('reward')",
                "input[type='submit'][value*='Claim']",
                "input[type='submit'][value*='reward']",
                "input[type='submit']:visible"
            ]
            
            # Debug: Log all buttons and inputs on the page
            all_buttons = await self.page.locator('button').count()
            all_inputs = await self.page.locator('input[type="submit"], input[type="button"]').count()
            logger.info(f"[{self.faucet_name}] Page has {all_buttons} buttons and {all_inputs} submit/button inputs")
            
            if all_buttons > 0:
                logger.info(f"[{self.faucet_name}] Available buttons:")
                for i in range(min(all_buttons, 20)):  # Log first 20 buttons
                    try:
                        btn = self.page.locator('button').nth(i)
                        text = await btn.text_content()
                        id_attr = await btn.get_attribute('id')
                        class_attr = await btn.get_attribute('class')
                        is_visible = await btn.is_visible()
                        is_enabled = await btn.is_enabled()
                        logger.debug(f"  [{i}] text='{text}', id='{id_attr}', class='{class_attr[:50]}', visible={is_visible}, enabled={is_enabled}")
                    except Exception as debug_err:
                        logger.debug(f"  [{i}] Error logging button: {debug_err}")
            
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
                # Check button state before clicking for debugging
                try:
                    btn_text_before = await faucet_btn.first.text_content()
                    is_enabled = await faucet_btn.first.is_enabled()
                    is_disabled_attr = await faucet_btn.first.get_attribute("disabled")
                    logger.info(f"[{self.faucet_name}] Button text before click: '{btn_text_before}'")
                    logger.info(f"[{self.faucet_name}] Button enabled: {is_enabled}, disabled attr: {is_disabled_attr}")

                    # CRITICAL FIX: FireFaucet has a JavaScript countdown timer (typically 9 seconds)
                    # that keeps the button disabled after page load. We must wait for it to complete.
                    if not is_enabled or is_disabled_attr is not None:
                        logger.info(f"[{self.faucet_name}] Button is disabled - waiting for countdown timer to complete...")
                        try:
                            # Wait for the button to become enabled (countdown finishes)
                            # The button text changes from "Please Wait (N)" to "Get Reward" when ready
                            await self.page.wait_for_function(
                                """() => {
                                    const btn = document.getElementById('get_reward_button') ||
                                                document.querySelector('button[type="submit"]');
                                    if (!btn) return false;
                                    return !btn.disabled && !btn.hasAttribute('disabled');
                                }""",
                                timeout=30000  # 30s max wait for countdown
                            )
                            logger.info(f"[{self.faucet_name}] Countdown timer completed - button enabled")
                            await asyncio.sleep(1)  # Brief pause after enable
                        except Exception as wait_err:
                            logger.warning(f"[{self.faucet_name}] Countdown wait timeout: {wait_err}")
                            # Try to force-enable the button as last resort
                            try:
                                await self.page.evaluate("""
                                    const btn = document.getElementById('get_reward_button') ||
                                                document.querySelector('button[type="submit"]');
                                    if (btn) {
                                        btn.disabled = false;
                                        btn.removeAttribute('disabled');
                                    }
                                """)
                                logger.info(f"[{self.faucet_name}] Force-enabled button after timeout")
                            except Exception:
                                pass

                        # Re-check button state
                        is_enabled_after = await faucet_btn.first.is_enabled()
                        btn_text_after_wait = await faucet_btn.first.text_content()
                        logger.info(f"[{self.faucet_name}] Button after wait: enabled={is_enabled_after}, text='{btn_text_after_wait}'")
                except Exception as btn_check_err:
                    logger.warning(f"[{self.faucet_name}] Could not check button state: {btn_check_err}")
                
                logger.info(f"[{self.faucet_name}] Clicking faucet reward button...")
                await self.human_like_click(faucet_btn)
                await asyncio.sleep(1)
                
                # Check if button text changed - if not, try JavaScript click
                try:
                    btn_text_after = await faucet_btn.first.text_content()
                    logger.info(f"[{self.faucet_name}] Button text after click: '{btn_text_after}'")
                    
                    # If button text hasn't changed to "Please Wait", try JavaScript click
                    if "please wait" not in btn_text_after.lower():
                        logger.warning(f"[{self.faucet_name}] Button text didn't change, trying JavaScript click...")
                        await self.page.evaluate("document.querySelector('button[type=\"submit\"]').click()")
                        await asyncio.sleep(2)
                        btn_text_js = await faucet_btn.first.text_content()
                        logger.info(f"[{self.faucet_name}] Button text after JS click: '{btn_text_js}'")
                except Exception as btn_check_err:
                    logger.warning(f"[{self.faucet_name}] Could not check button text after click: {btn_check_err}")
                
                await self.random_delay(1, 2)
                
                # Wait for "Please Wait" countdown timer to complete
                # FireFaucet shows a countdown like "Please Wait (5)" after clicking
                logger.info(f"[{self.faucet_name}] Waiting for claim processing...")
                try:
                    # Wait for button text to change from "Please Wait" to something else
                    await self.page.wait_for_function(
                        """() => {
                            const btn = document.querySelector('button[type="submit"]');
                            return btn && !btn.textContent.includes('Please Wait');
                        }""",
                        timeout=15000
                    )
                    logger.info(f"[{self.faucet_name}] Claim processing timer completed")
                    
                    # Check final button text
                    final_btn_text = await self.page.locator("button[type='submit']").first.text_content()
                    logger.info(f"[{self.faucet_name}] Button text after processing: '{final_btn_text}'")
                except Exception as wait_err:
                    logger.debug(f"[{self.faucet_name}] Wait for timer error: {wait_err}")
                
                # Additional wait for page to fully update
                await self.human_wait(3)
                
                # Enhanced debugging: Capture page state after claim
                logger.info(f"[{self.faucet_name}] Checking claim result...")
                current_url = self.page.url
                page_title = await self.page.title()
                logger.info(f"[{self.faucet_name}] Current URL: {current_url}")
                logger.info(f"[{self.faucet_name}] Page title: {page_title}")
                
                # Check page HTML for success indicators in text content
                try:
                    page_text = await self.page.evaluate("() => document.body.innerText")
                    page_text_lower = page_text.lower()
                    
                    # Look for success phrases in page text
                    success_phrases = ['claimed successfully', 'reward received', 'congratulations', 
                                      'success', 'you got', 'you earned', 'you received',
                                      'claim successful', 'reward added', 'balance updated']
                    
                    for phrase in success_phrases:
                        if phrase in page_text_lower:
                            logger.info(f"[{self.faucet_name}] ✅ Success phrase found in page: '{phrase}'")
                            # Extract amount if visible in text
                            import re
                            amount_match = re.search(r'(\d+\.?\d*)\s*(satoshi|sat|btc)', page_text_lower)
                            if amount_match:
                                amount = amount_match.group(1)
                                logger.info(f"[{self.faucet_name}] ✅ Amount detected: {amount}")
                            
                            # Get updated balance
                            new_balance = await self.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
                            return ClaimResult(success=True, status="Claimed", next_claim_minutes=30, 
                                             amount=amount if amount_match else "unknown", balance=new_balance)
                except Exception as text_err:
                    logger.debug(f"[{self.faucet_name}] Page text check error: {text_err}")
                
                # Check for success with multiple selectors (expanded for FireFaucet)
                success_selectors = [
                    ".success_msg", 
                    ".alert-success", 
                    ".toast-success", 
                    "[class*='success']",
                    ".claim-success",
                    ".reward-success",
                    ".swal2-success",  # SweetAlert success popup
                    ".swal2-popup:has(.swal2-success-ring)",  # SweetAlert with success icon
                    ".swal2-popup",  # Any SweetAlert popup
                    ".modal:visible",  # Any visible modal might indicate success
                    "[class*='claimed']",
                    "[class*='reward']",
                    ".toast:visible",  # Any toast notification
                    ".notification:visible",
                    "div:has-text('success')",
                    "div:has-text('claimed')",
                    "div:has-text('reward')",
                ]
                success_found = False
                success_msg_text = ""
                
                for sel in success_selectors:
                    try:
                        locator = self.page.locator(sel)
                        if await locator.count() > 0:
                            for i in range(await locator.count()):
                                elem = locator.nth(i)
                                if await elem.is_visible():
                                    success_msg = await elem.text_content() or ""
                                    # Check if message looks like success (not error)
                                    if success_msg and not any(err in success_msg.lower() for err in ['error', 'fail', 'wait', 'timer', 'please try']):
                                        logger.info(f"[{self.faucet_name}] ✅ Success message found via {sel}: {success_msg[:150]}")
                                        success_found = True
                                        success_msg_text = success_msg
                                        break
                        if success_found:
                            break
                    except Exception as e:
                        logger.debug(f"[{self.faucet_name}] Success selector {sel} error: {e}")
                        continue
                
                # Also check if balance changed (alternative success indicator)
                if not success_found:
                    try:
                        logger.info(f"[{self.faucet_name}] No success message found, checking balance change...")
                        await asyncio.sleep(2)  # Wait for balance update
                        new_balance_check = await self.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
                        logger.info(f"[{self.faucet_name}] Old balance: {balance}, New balance: {new_balance_check}")
                        
                        if new_balance_check and new_balance_check != "0" and new_balance_check != balance:
                            logger.info(f"[{self.faucet_name}] ✅ Claim success detected via balance change: {balance} -> {new_balance_check}")
                            success_found = True
                            balance = new_balance_check
                    except Exception as bal_err:
                        logger.debug(f"[{self.faucet_name}] Balance check error: {bal_err}")
                
                # Check for URL change indicating success
                if not success_found:
                    if any(indicator in current_url.lower() for indicator in ['success', 'claimed', 'dashboard']):
                        logger.info(f"[{self.faucet_name}] ✅ Claim success detected via URL: {current_url}")
                        success_found = True
                
                # Check if button disappeared (claim consumed)
                if not success_found:
                    try:
                        button_still_present = await self.page.locator("button:has-text('Get reward')").count() > 0
                        if not button_still_present:
                            logger.info(f"[{self.faucet_name}] ✅ Claim button disappeared - assuming success")
                            success_found = True
                    except:
                        pass
                
                if success_found:
                    # Get updated balance
                    new_balance = await self.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
                    logger.info(f"[{self.faucet_name}] Final balance: {new_balance}")
                    
                    # Extract amount from success message if available
                    amount = "unknown"
                    if success_msg_text:
                        import re
                        amount_match = re.search(r'(\d+\.?\d*)\s*(satoshi|sat|btc)', success_msg_text.lower())
                        if amount_match:
                            amount = amount_match.group(1)
                    
                    # Claim shortlinks if enabled (non-blocking, separate context)
                    enable_shortlinks = getattr(self.settings, 'enable_shortlinks', True)
                    if enable_shortlinks:
                        try:
                            logger.info(f"[{self.faucet_name}] Starting shortlink claiming in parallel...")
                            asyncio.create_task(self.claim_shortlinks(separate_context=True))
                        except Exception as sl_err:
                            logger.debug(f"[{self.faucet_name}] Shortlink task creation failed: {sl_err}")
                    
                    return ClaimResult(success=True, status="Claimed", next_claim_minutes=30, 
                                     amount=amount, balance=new_balance)
                
                # If still not found, take screenshot and log page content for debugging
                logger.warning(f"[{self.faucet_name}] Claim verification failed - no success indicator found")
                
                # Log visible text for debugging
                try:
                    visible_text = await self.page.evaluate("() => document.body.innerText")
                    logger.info(f"[{self.faucet_name}] Page visible text (first 500 chars): {visible_text[:500]}")
                except:
                    pass
                
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

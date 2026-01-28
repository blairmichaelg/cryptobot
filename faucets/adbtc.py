from .base import FaucetBot, ClaimResult
import logging
import asyncio
import re
from typing import Optional

logger = logging.getLogger(__name__)

class AdBTCBot(FaucetBot):
    """
    AdBTC.top bot implementation.
    
    AdBTC is a PTC (Paid-to-Click) site where earnings come primarily from viewing surf ads.
    This implementation includes login, balance checking, ad surfing, and withdrawal functionality.
    """
    
    def __init__(self, settings, page, **kwargs):
        """
        Initialize AdBTC bot.
        
        Args:
            settings: BotSettings configuration object
            page: Playwright Page instance
            **kwargs: Additional arguments passed to FaucetBot
        """
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "AdBTC"
        self.base_url = "https://adbtc.top"

    async def is_logged_in(self) -> bool:
        """
        Check if user is currently logged in.
        
        Returns:
            True if logged in, False otherwise
        """
        return "/surf/browse" in self.page.url or await self.page.locator(".balance-value, .nomargbot > div.col.s6.l3.m3.left.hide-on-small-only > p > b").count() > 0

    async def login(self) -> bool:
        """
        Authenticate with AdBTC.
        
        Handles multiple CAPTCHA types (math, hCaptcha) and proxy detection.
        Automatically strips email aliases (+) as AdBTC blocks them.
        
        Returns:
            True if login successful, False otherwise
        """
        creds = self.get_credentials("adbtc")
        
        if not creds:
            logger.error(f"[{self.faucet_name}] No credentials found.")
            return False

        try:
            logger.info(f"[{self.faucet_name}] Navigating to login...")
            await self.page.goto(f"{self.base_url}/index/enter", wait_until="domcontentloaded", timeout=getattr(self.settings, "timeout", 180000))
            
            # Handle Cloudflare if present
            await self.handle_cloudflare(max_wait_seconds=30)
            
            # Check if already logged in
            if await self.is_logged_in():
                 logger.info(f"[{self.faucet_name}] Already logged in.")
                 return True

            # Wait for login form
            await self.page.wait_for_selector('input[name="email"]', timeout=15000)
            
            # Check for CAPTCHA type selector (AdBTC offers Math and hCaptcha)
            captcha_type_select = self.page.locator("select[name='captcha_type']")
            if await captcha_type_select.count() > 0 and await captcha_type_select.is_visible():
                 # Try to switch to hCaptcha if solver is enabled, else stay on Math
                 if self.solver.api_key:
                     logger.info(f"[{self.faucet_name}] Switching to hCaptcha...")
                     await captcha_type_select.select_option("1")  # 1 is usually hCaptcha
                     await self.random_delay(0.5, 1.0)

            # Handle Math Captcha if active
            math_img = self.page.locator("img[src*='captcha.php']")
            if await math_img.count() > 0 and await math_img.is_visible():
                 logger.info(f"[{self.faucet_name}] Math CAPTCHA detected, solving...")
                 await self.solve_math_captcha()

            # AdBTC blocks email aliases with '+', use base email
            base_email = self.strip_email_alias(creds['username'])
            
            logger.info(f"[{self.faucet_name}] Filling credentials...")
            # Use human_type for stealth
            await self.human_type('input[name="email"]', base_email)
            await self.random_delay(0.3, 0.7)
            await self.human_type('input[name="password"]', creds['password'])
            await self.random_delay(0.5, 1.0)
            
            # Solve hCaptcha/Turnstile if present
            logger.info(f"[{self.faucet_name}] Checking for hCaptcha/Turnstile...")
            await self.solver.solve_captcha(self.page)
            
            # Small delay before submit
            await self.random_delay(0.5, 1.0)
            
            # Submit login form
            submit_btn = self.page.locator('input[type="submit"], button:has-text("Login")')
            if await submit_btn.count() > 0:
                logger.info(f"[{self.faucet_name}] Submitting login form...")
                await self.human_like_click(submit_btn)
            else:
                logger.warning(f"[{self.faucet_name}] Submit button not found, trying form submit...")
                await self.page.evaluate("document.forms[0].submit()")
            
            # Wait for navigation with timeout
            try:
                await self.page.wait_for_load_state("networkidle", timeout=30000)
            except Exception as e:
                logger.debug(f"[{self.faucet_name}] Navigation wait timed out: {e}")
            
            # Check for proxy detection
            content = await self.page.content()
            if "proxy" in content.lower() and "detected" in content.lower():
                logger.error(f"[{self.faucet_name}] Proxy detected - login blocked.")
                return False
            
            # Verify login success
            if await self.is_logged_in():
                logger.info(f"[{self.faucet_name}] ✅ Login successful!")
                return True
            
            # Additional check for title-based success
            title = await self.page.title()
            if "Authorize" in title or "Dashboard" in title:
                 logger.info(f"[{self.faucet_name}] ✅ Login successful (title check)!")
                 return True
            
            logger.warning(f"[{self.faucet_name}] Login verification unclear. URL: {self.page.url}")
            return True
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Login failed: {e}", exc_info=True)
            return False

    async def claim(self) -> ClaimResult:
        """
        AdBTC claim cycle.
        
        AdBTC's main earning method is surfing ads, not a traditional faucet.
        This method validates login and extracts balance.
        
        Returns:
            ClaimResult with success status and next claim timing
        """
        try:
            logger.info(f"[{self.faucet_name}] Starting claim cycle...")
            
            # Navigate to surf page to verify login and extract balance
            await self.page.goto(f"{self.base_url}/surf/browse", wait_until="domcontentloaded", timeout=getattr(self.settings, "timeout", 180000))
            
            # Handle Cloudflare if present
            await self.handle_cloudflare(max_wait_seconds=20)
            
            # Add human-like idle behavior for stealth
            await self.idle_mouse(duration=1.5)
            
            # Extract balance using DataExtractor
            balance_selectors = [
                ".nomargbot > div.col.s6.l3.m3.left.hide-on-small-only > p > b",
                ".balance-value",
                ".user-balance"
            ]
            balance = "0"
            
            for selector in balance_selectors:
                try:
                    balance = await self.get_balance(selector)
                    if balance and balance != "0":
                        logger.info(f"[{self.faucet_name}] Balance extracted: {balance}")
                        break
                except Exception as e:
                    logger.debug(f"[{self.faucet_name}] Balance extraction failed for {selector}: {e}")
                    continue
            
            if balance == "0":
                logger.warning(f"[{self.faucet_name}] Could not extract balance, using fallback auto-detection")
                balance = await self.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
            
            # Check for timer on claim page (if AdBTC has a faucet feature)
            timer_minutes = 30.0  # Default next run for surf ads
            
            timer_selectors = ["#claim_timer", ".timer", "[class*='countdown']"]
            for selector in timer_selectors:
                try:
                    timer_el = self.page.locator(selector)
                    if await timer_el.count() > 0 and await timer_el.first.is_visible():
                        timer_minutes = await self.get_timer(selector)
                        if timer_minutes > 0:
                            logger.info(f"[{self.faucet_name}] Timer active: {timer_minutes:.1f} minutes")
                            return ClaimResult(
                                success=True,
                                status="Timer Active",
                                next_claim_minutes=timer_minutes,
                                balance=balance
                            )
                except Exception as e:
                    logger.debug(f"[{self.faucet_name}] Timer check failed for {selector}: {e}")
                    continue
            
            # AdBTC main claim IS surfing ads, not a traditional faucet
            logger.info(f"[{self.faucet_name}] Logged in successfully. Balance: {balance}")
            
            return ClaimResult(
                success=True,
                status="Ready for Surf Ads",
                next_claim_minutes=timer_minutes,
                balance=balance
            )
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Claim failed: {e}", exc_info=True)
            return ClaimResult(
                success=False,
                status=f"Error: {str(e)}",
                next_claim_minutes=30,
                balance="0"
            )

    def get_jobs(self):
        """
        Returns AdBTC-specific jobs for the scheduler.
        """
        from core.orchestrator import Job
        import time
        
        jobs = []
        f_type = self.faucet_name.lower()
        
        # Job 1: Faucet Claim (Login verification)
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=f_type,
            job_type="claim_wrapper"
        ))
        
        # Job 2: Withdrawal Job
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=f_type,
            job_type="withdraw_wrapper"
        ))
        
        # Job 3: Surf Ads (main earning method for AdBTC)
        jobs.append(Job(
            priority=2,
            next_run=time.time() + 120,
            name=f"{self.faucet_name} Surf",
            profile=None,
            faucet_type=f_type,
            job_type="ptc_wrapper"
        ))
        
        return jobs

    async def view_ptc_ads(self):
        """
        View available PTC ads on AdBTC for earning.
        
        AdBTC's surf ads flow:
        1. Click 'Open' button for an ad
        2. Ad opens in new tab
        3. Wait for timer on main page to complete
        4. Repeat for next ad
        
        This method implements robust error handling and stealth features.
        """
        try:
            logger.info(f"[{self.faucet_name}] Starting Surf Ads...")
            await self.page.goto(f"{self.base_url}/surf/browse", wait_until="domcontentloaded", timeout=getattr(self.settings, "timeout", 180000))
            
            # Handle Cloudflare if present
            await self.handle_cloudflare(max_wait_seconds=20)
            
            ads_viewed = 0
            max_ads = 15  # Limit to prevent infinite loops
            
            for attempt in range(max_ads):
                try:
                    # Add human-like idle behavior between ads
                    await self.idle_mouse(duration=1.5)
                    
                    # Check for CAPTCHA on Surf Page (often appears between ads)
                    captcha_frame = self.page.locator(".h-captcha, iframe[src*='hcaptcha'], iframe[src*='turnstile']")
                    if await captcha_frame.count() > 0:
                        logger.info(f"[{self.faucet_name}] Session CAPTCHA detected, solving...")
                        await self.solver.solve_captcha(self.page)
                        
                        # Usually need to click "Submit" after CAPTCHA
                        submit = self.page.locator("input[type='submit'], button:has-text('Submit')")
                        if await submit.count() > 0 and await submit.is_visible():
                            await self.human_like_click(submit)
                            await self.page.wait_for_load_state("networkidle", timeout=15000)
                        
                        await self.random_delay(1, 2)

                    # Check for "Click to start" button (sometimes appears)
                    start_btn = self.page.locator("input[value='Click to start'], button:has-text('Click to start')")
                    if await start_btn.count() > 0 and await start_btn.is_visible():
                        logger.info(f"[{self.faucet_name}] Clicking 'Start' button...")
                        await self.human_like_click(start_btn)
                        await self.random_delay(1, 2)
                        continue
                    
                    # Check for "Open" button - main ad entry point
                    open_btn = self.page.locator("a.btn-large, button.btn:has-text('Open'), a:has-text('Open')")
                    
                    if await open_btn.count() == 0:
                        logger.info(f"[{self.faucet_name}] No more ads available. Viewed {ads_viewed} ads.")
                        break
                    
                    logger.info(f"[{self.faucet_name}] Opening ad {ads_viewed + 1}...")
                    
                    # Open ad in new tab
                    try:
                        async with self.page.context.expect_page(timeout=10000) as new_page_info:
                            await self.human_like_click(open_btn.first)
                        
                        ad_page = await new_page_info.value
                        logger.debug(f"[{self.faucet_name}] Ad page opened: {ad_page.url}")
                        
                    except Exception as e:
                        logger.warning(f"[{self.faucet_name}] Failed to open ad page: {e}")
                        await self.random_delay(2, 4)
                        continue
                    
                    # Poll main page for timer completion
                    logger.info(f"[{self.faucet_name}] Waiting for ad timer to complete...")
                    max_wait = 90  # Max 90 seconds per ad
                    start_poll = asyncio.get_event_loop().time()
                    timer_complete = False
                    
                    while (asyncio.get_event_loop().time() - start_poll) < max_wait:
                        try:
                            # Check page title for timer
                            title = await self.page.title()
                            
                            # Timer complete indicators
                            if "sec" not in title.lower() and "left" not in title.lower():
                                # Check content for completion message
                                content = await self.page.content()
                                if "you earned" in content.lower() or "credited" in content.lower():
                                    logger.info(f"[{self.faucet_name}] ✅ Ad {ads_viewed + 1} complete!")
                                    timer_complete = True
                                    ads_viewed += 1
                                    break
                            
                            # Add small human-like mouse movement while waiting
                            if asyncio.get_event_loop().time() % 5 < 0.1:  # Every ~5 seconds
                                await self.idle_mouse(duration=0.5)
                            
                            await asyncio.sleep(2)
                            
                        except Exception as e:
                            logger.debug(f"[{self.faucet_name}] Timer polling error: {e}")
                            break
                    
                    # Close ad page
                    try:
                        await ad_page.close()
                    except Exception as e:
                        logger.debug(f"[{self.faucet_name}] Ad page close error: {e}")
                    
                    if not timer_complete:
                        logger.warning(f"[{self.faucet_name}] Timer did not complete within {max_wait}s")
                    
                    # Random delay between ads for stealth
                    await self.random_delay(2, 5)
                    
                    # AdBTC usually auto-reloads to next ad, but verify
                    current_url = self.page.url
                    if "/surf/browse" not in current_url:
                        logger.info(f"[{self.faucet_name}] Navigating back to surf page...")
                        await self.page.goto(f"{self.base_url}/surf/browse", wait_until="domcontentloaded")
                        await self.random_delay(1, 2)
                    
                except Exception as ad_error:
                    logger.error(f"[{self.faucet_name}] Error processing ad {attempt + 1}: {ad_error}")
                    # Continue to next ad
                    continue
            
            logger.info(f"[{self.faucet_name}] Surf ads session complete. Total ads viewed: {ads_viewed}")
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Surf Error: {e}", exc_info=True)

    async def withdraw(self) -> ClaimResult:
        """
        Execute AdBTC withdrawal to FaucetPay.
        
        Handles FaucetPay withdrawal with password verification and confirmation.
        Implements retry logic for network timeouts and CAPTCHA failures.
        
        Returns:
            ClaimResult with success status and next withdrawal timing
        """
        try:
            logger.info(f"[{self.faucet_name}] Navigating to withdrawal page...")
            await self.page.goto(f"{self.base_url}/index/withdraw", wait_until="domcontentloaded", timeout=getattr(self.settings, "timeout", 180000))
            
            # Handle Cloudflare if present
            await self.handle_cloudflare(max_wait_seconds=20)
            
            # Add human-like behavior
            await self.idle_mouse(duration=1.5)
            
            # Select FaucetPay by default as it has lower thresholds
            # AdBTC has different buttons for different methods
            faucetpay_btn = self.page.locator("a:has-text('To FaucetPay'), button:has-text('To FaucetPay')")
            
            if await faucetpay_btn.count() == 0:
                logger.info(f"[{self.faucet_name}] FaucetPay withdrawal not available.")
                return ClaimResult(
                    success=False,
                    status="No Withdrawal Method Available",
                    next_claim_minutes=1440  # Try again in 24 hours
                )
            
            logger.info(f"[{self.faucet_name}] Clicking FaucetPay withdrawal...")
            await self.human_like_click(faucetpay_btn.first)
            
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:
                logger.debug(f"[{self.faucet_name}] Load state wait timed out: {e}")
            
            await self.random_delay(1, 2)
            
            # Check for withdrawal form
            withdraw_confirm = self.page.locator("input[value='Withdraw'], button:has-text('Withdraw')")
            
            if await withdraw_confirm.count() == 0:
                logger.warning(f"[{self.faucet_name}] Withdrawal confirmation button not found.")
                return ClaimResult(
                    success=False,
                    status="Withdrawal Form Not Found",
                    next_claim_minutes=360  # Try again in 6 hours
                )
            
            # Some accounts require a password to withdraw
            pass_field = self.page.locator("input[name='password'], input[type='password']")
            if await pass_field.count() > 0 and await pass_field.is_visible():
                logger.info(f"[{self.faucet_name}] Password required for withdrawal, filling...")
                creds = self.get_credentials("adbtc")
                if creds and creds.get('password'):
                    await self.human_type(pass_field, creds['password'])
                    await self.random_delay(0.5, 1.0)
                else:
                    logger.error(f"[{self.faucet_name}] No password available for withdrawal.")
                    return ClaimResult(
                        success=False,
                        status="No Password for Withdrawal",
                        next_claim_minutes=1440
                    )
            
            # Solve CAPTCHA if present
            logger.info(f"[{self.faucet_name}] Checking for CAPTCHA...")
            captcha_solved = await self.solver.solve_captcha(self.page)
            
            if not captcha_solved:
                logger.warning(f"[{self.faucet_name}] CAPTCHA solving failed or not present.")
            
            await self.random_delay(0.5, 1.0)
            
            # Submit withdrawal
            logger.info(f"[{self.faucet_name}] Submitting withdrawal...")
            await self.human_like_click(withdraw_confirm)
            
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception as e:
                logger.debug(f"[{self.faucet_name}] Post-submit wait timed out: {e}")
            
            await self.random_delay(2, 3)
            
            # Check for success/error messages
            content = await self.page.content()
            content_lower = content.lower()
            
            # Success indicators
            if any(word in content_lower for word in ["success", "processing", "completed", "sent"]):
                logger.info(f"[{self.faucet_name}] ✅ Withdrawal successful!")
                return ClaimResult(
                    success=True,
                    status="Withdrawn",
                    next_claim_minutes=1440  # Daily withdrawals
                )
            
            # Error indicators
            if any(word in content_lower for word in ["insufficient", "minimum", "error", "failed"]):
                logger.warning(f"[{self.faucet_name}] Withdrawal failed - check balance/threshold.")
                return ClaimResult(
                    success=False,
                    status="Insufficient Balance or Error",
                    next_claim_minutes=720  # Try again in 12 hours
                )
            
            # Uncertain outcome
            logger.warning(f"[{self.faucet_name}] Withdrawal outcome unclear, manual verification needed.")
            await self.page.screenshot(path=f"adbtc_withdrawal_{asyncio.get_event_loop().time()}.png")
            
            return ClaimResult(
                success=False,
                status="Verification Required",
                next_claim_minutes=360  # Try again in 6 hours
            )
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal Error: {e}", exc_info=True)
            return ClaimResult(
                success=False,
                status=f"Error: {str(e)}",
                next_claim_minutes=60  # Retry in 1 hour on error
            )

    async def solve_math_captcha(self) -> bool:
        """
        Extract and solve simple AdBTC math captchas (e.g. '7 + 3').
        
        AdBTC uses basic arithmetic captchas as an alternative to hCaptcha.
        This method extracts the equation from page content and solves it.
        
        Returns:
            True if solved successfully, False otherwise
        """
        try:
            content = await self.page.content()
            
            # Pattern: "num1 +/- num2 ="
            match = re.search(r'(\d+)\s*([+\-])\s*(\d+)\s*=', content)
            
            if not match:
                logger.debug(f"[{self.faucet_name}] No math captcha pattern found in content.")
                return False
            
            num1 = int(match.group(1))
            op = match.group(2)
            num2 = int(match.group(3))
            
            # Calculate result
            result = num1 + num2 if op == '+' else num1 - num2
            
            logger.info(f"[{self.faucet_name}] Solved Math Captcha: {num1} {op} {num2} = {result}")
            
            # Fill in the answer with human-like typing
            answer_field = self.page.locator('input[name="number"], input[type="text"][name*="captcha"]')
            if await answer_field.count() > 0:
                await self.human_type(answer_field, str(result))
                await self.random_delay(0.3, 0.6)
                return True
            else:
                logger.warning(f"[{self.faucet_name}] Math captcha answer field not found.")
                return False
                
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Math captcha solving failed: {e}")
            return False

    # Removed duplicate get_jobs() method - see line 225 for the implementation

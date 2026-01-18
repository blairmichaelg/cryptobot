from .base import FaucetBot, ClaimResult
import logging
from solvers.shortlink import ShortlinkSolver
import asyncio

logger = logging.getLogger(__name__)

class FireFaucetBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "FireFaucet"
        self.base_url = "https://firefaucet.win"

    async def view_ptc_ads(self):
        """
        Views PTC ads for FireFaucet using updated selectors.
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
                    logger.info(f"[{self.faucet_name}] No more PTC ads available.")
                    break
                
                logger.info(f"[{self.faucet_name}] Watching PTC Ad {processed + 1}...")
                await ad_button.first.click()
                await self.page.wait_for_load_state()
                
                # PTC ads use a custom numeric image captcha
                # We'll rely on our generic solver which should detect the image/input
                # or we might need specific logic for #description > img
                captcha_img = self.page.locator("#description > img")
                if await captcha_img.count() > 0:
                    logger.info(f"[{self.faucet_name}] Custom PTC captcha detected. Solving...")
                    # Basic solving logic (can be expanded with OCR if needed)
                    await self.solver.solve_captcha(self.page)
                
                # Check for other captchas (Turnstile/hCaptcha)
                if await self.page.query_selector("iframe[src*='turnstile'], iframe[src*='hcaptcha']"):
                    await self.solver.solve_captcha(self.page)
                
                # Submit button for PTC
                submit_btn = self.page.locator("#submit-button")
                if await submit_btn.count() > 0:
                    await self.human_like_click(submit_btn)
                    await self.random_delay(2, 4)
                
                processed += 1
                await self.page.goto(f"{self.base_url}/ptc")
                
        except Exception as e:
            logger.error(f"[{self.faucet_name}] PTC Error: {e}")

    async def login(self) -> bool:
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
            
            # Use fill() for speed during testing, then human delay
            await self.page.fill('#username', creds['username'])
            await self.random_delay(0.3, 0.7)
            await self.page.fill('#password', creds['password'])
            await self.random_delay(0.5, 1.0)
            
            # Handle CAPTCHA - site offers reCAPTCHA by default
            logger.info(f"[{self.faucet_name}] Solving CAPTCHA...")
            await self.solver.solve_captcha(self.page)
            
            # Small delay to let token injection settle
            await self.random_delay(0.5, 1.0)
            
            # Submit form via JavaScript (bypasses overlay blockers)
            logger.info(f"[{self.faucet_name}] Submitting form...")
            await self.page.evaluate("""() => {
                const submitBtn = document.querySelector('button.submitbtn');
                if (submitBtn) submitBtn.click();
                // Also try submitting the form directly
                const form = document.querySelector('form');
                if (form) form.submit();
            }""")


            
            
            # Wait for dashboard elements instead of URL change
            try:
                logger.info(f"[{self.faucet_name}] Waiting for dashboard elements...")
                
                # Poll for success (max 30 seconds)
                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < 30:
                    try:
                        # 1. Check URL
                        if "/dashboard" in self.page.url:
                            logger.info(f"[{self.faucet_name}] ✅ Login successful (Dashboard URL detected)!")
                            return True
                            
                        # 2. Check elements
                        if await self.page.locator(".user-balance, .level-progress").count() > 0:
                            logger.info(f"[{self.faucet_name}] ✅ Login successful (Dashboard elements detected)!")
                            return True
                            
                        # 3. Check text
                        if await self.page.locator("a[href*='logout']").count() > 0:
                            logger.info(f"[{self.faucet_name}] ✅ Login successful (Logout link detected)!")
                            return True
                            
                        # Check for errors periodically
                        if await self.page.locator('.alert-danger, .error-message, .toast-error').count() > 0:
                            error_text = await self.page.locator('.alert-danger, .error-message, .toast-error').first.text_content()
                            logger.error(f"[{self.faucet_name}] Login error: {error_text}")
                            return False
                            
                    except Exception:
                        pass # Ignore transient errors during polling
                        
                    await asyncio.sleep(1)
                
                logger.warning(f"[{self.faucet_name}] Login verification timed out. URL: {self.page.url}")
                await self.page.screenshot(path=f"login_check_failed_{self.faucet_name}.png", full_page=True)
                return False
            finally:
                pass
                
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
        Daily Bonus and Faucet Claim.
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
            await self.page.goto(f"{self.base_url}/faucet")
            
            balance = await self.get_balance(".user-balance, .balance-text")
            wait = await self.get_timer(".fa-clock + span, #claim_timer, .timer")
            if wait > 0:
                 return ClaimResult(success=True, status="Timer Active", next_claim_minutes=wait, balance=balance)

            await self.solver.solve_captcha(self.page)
            
            # Faucet Claim Button
            faucet_btn = self.page.locator("#get_reward_button, #faucet_btn")
            if await faucet_btn.count() > 0:
                logger.info(f"[{self.faucet_name}] Clicking faucet reward button...")
                await self.human_like_click(faucet_btn)
                await self.random_delay(3, 5)
                
                if await self.page.locator(".success_msg, .alert-success").count() > 0:
                    logger.info("FireFaucet faucet claimed successfully.")
                    return ClaimResult(success=True, status="Claimed", next_claim_minutes=30)
                
                logger.warning(f"[{self.faucet_name}] Claim verification failed.")
                await self.page.screenshot(path=f"claim_failed_{self.faucet_name}.png", full_page=True)
            else:
                logger.warning(f"[{self.faucet_name}] Faucet button not found.")
                await self.page.screenshot(path=f"claim_btn_missing_{self.faucet_name}.png", full_page=True)
                
            return ClaimResult(success=False, status="Faucet Ready but Failed", next_claim_minutes=5)
            
            
        except Exception as e:
            logger.error(f"FireFaucet claim failed: {e}")
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
                if await solver.solve(self.page.url):
                    logger.info(f"[{self.faucet_name}] Shortlink {i+1} Solved!")
                    await self.page.goto(f"{self.base_url}/shortlinks")
                else:
                    logger.warning(f"[{self.faucet_name}] Shortlink {i+1} Failed.")
                    await self.page.goto(f"{self.base_url}/shortlinks")
                    
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Shortlink error: {e}")

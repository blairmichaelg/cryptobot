from .base import FaucetBot, ClaimResult
import logging
import asyncio
import re

logger = logging.getLogger(__name__)

class AdBTCBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "AdBTC"
        self.base_url = "https://adbtc.top"

    async def is_logged_in(self) -> bool:
        return "/surf/browse" in self.page.url or await self.page.locator(".balance-value, .nomargbot > div.col.s6.l3.m3.left.hide-on-small-only > p > b").count() > 0

    async def login(self) -> bool:
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("adbtc")
        
        if not creds:
            logger.error(f"[{self.faucet_name}] No credentials found.")
            return False

        try:
            logger.info(f"[{self.faucet_name}] Navigating to login...")
            await self.page.goto(f"{self.base_url}/index/enter")
            await self.handle_cloudflare()
            
            # Check if logged in
            if "/surf/browse" in self.page.url or "balance" in await self.page.content():
                 logger.info(f"[{self.faucet_name}] Already logged in.")
                 return True

            await self.page.goto(f"{self.base_url}/index/enter")
            
            # Check for generic captcha options (AdBTC has 'Math' and 'hCaptcha')
            # They often use a custom selector to switch between them
            captcha_type_select = self.page.locator("select[name='captcha_type']")
            if await captcha_type_select.is_visible():
                 # Try to switch to hCaptcha if solver is enabled, else stay on Math
                 if self.solver.api_key:
                     await captcha_type_select.select_option("1") # 1 is usually hCaptcha
                     await self.random_delay()

            # Handle Math Captcha if active
            if await self.page.locator("img[src*='captcha.php']").is_visible():
                 await self.solve_math_captcha()

            # AdBTC blocks email aliases with '+', use base email
            base_email = self.strip_email_alias(creds['username'])
            await self.page.fill('input[name="email"]', base_email)
            await self.page.fill('input[name="password"]', creds['password'])
            
            await self.solver.solve_captcha(self.page)
            
            await self.human_like_click(self.page.locator('input[type="submit"], button:has-text("Login")'))
            
            await self.page.wait_for_load_state("networkidle")
            
            # Check for proxy detection
            content = await self.page.content()
            if "proxy" in content.lower() and "detected" in content.lower():
                logger.error(f"[{self.faucet_name}] Proxy detected - login blocked.")
                return False
            
            # Additional check for 2FA or success
            if "Authorize" in await self.page.title():
                 logger.info(f"[{self.faucet_name}] Login Successful (redirected).")
                 return True
                 
            return True
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Login failed: {e}")
            return False

    async def claim(self) -> ClaimResult:
        # Updated balance selector from research
        balance = await self.get_balance(".nomargbot > div.col.s6.l3.m3.left.hide-on-small-only > p > b, .balance-value, .user-balance")
        # AdBTC main claim IS surfing ads.
        return ClaimResult(success=True, status="Logged In", next_claim_minutes=30, balance=balance)

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
        try:
            logger.info(f"[{self.faucet_name}] Starting Surf Ads...")
            await self.page.goto(f"{self.base_url}/surf/browse")
            
            for _ in range(15): # Limit loops
                # Check for Captcha on Surf Page (often appears between ads)
                if await self.page.locator(".h-captcha").count() > 0:
                     logger.info(f"[{self.faucet_name}] Solving session captcha...")
                     await self.solver.solve_captcha(self.page)
                     # Usually need to click "Submit" after
                     submit = self.page.locator("input[type='submit']")
                     if await submit.is_visible():
                         await self.human_like_click(submit)
                         await self.page.wait_for_load_state("networkidle")

                # Check for "Open" button
                # AdBTC Surf Ads flow: Click 'Open' -> New Tab -> Main Tab timer
                open_btn = self.page.locator("a.btn-large, button.btn:has-text('Open'), a:has-text('Open')")
                if await open_btn.count() == 0:
                    # Maybe it's a "Click to surf" button or captcha
                    if await self.page.locator("input[value='Click to start']").is_visible():
                         await self.page.click("input[value='Click to start']")
                         continue
                    
                    logger.info(f"[{self.faucet_name}] No more ads to open.")
                    break
                
                logger.info(f"[{self.faucet_name}] Clicking 'Open' for ad...")
                async with self.page.context.expect_page() as new_page_info:
                    await self.human_like_click(open_btn.first)
                
                ad_page = await new_page_info.value
                
                # Polling loop for timer on MAIN page
                logger.info(f"[{self.faucet_name}] Waiting for timer on main page...")
                max_wait = 90
                start_poll = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_poll) < max_wait:
                    title = await self.page.title()
                    if "sec" not in title.lower() and "left" not in title.lower():
                        # Check content for "You earned"
                        if "you earned" in (await self.page.content()).lower():
                             logger.info(f"[{self.faucet_name}] Ad complete (earned).")
                             break
                    await asyncio.sleep(2)
                
                await ad_page.close()
                await self.random_delay(2, 5)
                
                # Check if we need to reload or if it auto-reloads
                # AdBTC usually auto-reloads to next ad.
                
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Surf Error: {e}")

    async def withdraw(self) -> ClaimResult:
        """AdBTC withdrawal logic."""
        try:
            logger.info(f"[{self.faucet_name}] Navigating to withdrawal page...")
            await self.page.goto(f"{self.base_url}/index/withdraw")
            await self.handle_cloudflare()
            
            # Select FaucetPay by default as it has lower thresholds
            # AdBTC has different buttons for different methods
            faucetpay_btn = self.page.locator("a:has-text('To FaucetPay'), button:has-text('To FaucetPay')")
            
            if await faucetpay_btn.count() > 0:
                logger.info(f"[{self.faucet_name}] Clicking FaucetPay withdrawal...")
                await self.human_like_click(faucetpay_btn.first)
                await self.page.wait_for_load_state("networkidle")
                
                # Check for "Withdraw" confirmation button
                # Usually it asks for password or just a 'Withdraw' button
                withdraw_confirm = self.page.locator("input[value='Withdraw'], button:has-text('Withdraw')")
                if await withdraw_confirm.count() > 0:
                    # Some accounts require a password to withdraw
                    pass_field = self.page.locator("input[name='password']")
                    if await pass_field.is_visible():
                        creds = self.get_credentials("adbtc")
                        await self.human_type(pass_field, creds['password'])
                    
                    await self.human_like_click(withdraw_confirm)
                    await self.page.wait_for_load_state()
                    
                    # Check for success message
                    content = await self.page.content()
                    if "success" in content.lower() or "processing" in content.lower():
                        logger.info(f"[{self.faucet_name}] Withdrawal successful!")
                        return ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440)
                    else:
                        logger.warning(f"[{self.faucet_name}] Withdrawal might have failed or needs manual check.")
                        return ClaimResult(success=False, status="Verification Required", next_claim_minutes=360)
                
            return ClaimResult(success=False, status="No Withdrawal Method Available", next_claim_minutes=1440)
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)

    async def solve_math_captcha(self):
        """
        Extracts and solves simple AdBTC math captchas (e.g. '7 + 3').
        """
        try:
            content = await self.page.content()
            match = re.search(r'(\d+)\s*([+\-])\s*(\d+)\s*=', content)
            if match:
                num1 = int(match.group(1))
                op = match.group(2)
                num2 = int(match.group(3))
                result = num1 + num2 if op == '+' else num1 - num2
                logger.info(f"[{self.faucet_name}] Solved Math Captcha: {num1} {op} {num2} = {result}")
                await self.page.fill('input[name="number"]', str(result))
                return True
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Math solving failed: {e}")
        return False

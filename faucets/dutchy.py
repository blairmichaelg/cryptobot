from .base import FaucetBot, ClaimResult
import logging
import asyncio
from solvers.shortlink import ShortlinkSolver

logger = logging.getLogger(__name__)

class DutchyBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "DutchyCorp"
        self.base_url = "https://autofaucet.dutchycorp.space"

    async def is_logged_in(self) -> bool:
        return await self.page.query_selector("a[href*='logout']") is not None
    
    def get_jobs(self):
        """
        Returns DutchyCorp-specific jobs including rolls, shortlinks and withdrawals.
        """
        from core.orchestrator import Job
        import time
        
        jobs = []
        
        # Job 1: Main Claim (Rolls) - Hourly
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="claim_wrapper"
        ))

        # Job 2: Withdraw - Daily
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="withdraw_wrapper"
        ))
        
        return jobs

    async def login(self) -> bool:
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("dutchy")
            
        if not creds: 
            return False

        try:
            logger.info(f"[{self.faucet_name}] Navigating to login...")
            await self.page.goto(f"{self.base_url}/login.php")
            
            # Check for Proxy Detection
            content = await self.page.content()
            if "Proxy Detected" in content:
                logger.error(f"[{self.faucet_name}] Proxy Detection active! Site is blocking this IP.")
                return False
            
            # Check if already logged in
            if await self.page.query_selector("a[href*='logout']"):
                 logger.info(f"[{self.faucet_name}] Already logged in.")
                 return True

            await self.page.fill('input[name="username"]', creds['username'])
            await self.page.fill('input[name="password"]', creds['password'])
            
            # "Keep me logged in" checkbox often helps
            remember = self.page.locator('input[name="remember_me"]')
            if await remember.count() > 0:
                await remember.check()
            
            await self.solver.solve_captcha(self.page)
            await self._try_click_checkbox_captcha()
            
            submit = self.page.locator('button[type="submit"]')
            await self.human_like_click(submit)
            
            await self.page.wait_for_url("**/dashboard.php", timeout=20000)
            logger.info(f"[{self.faucet_name}] Login Successful.")
            return True
        except Exception as e:
            logger.error(f"DutchyCorp login failed: {e}")
            return False

    async def _try_click_checkbox_captcha(self) -> None:
        """Fallback click for checkbox-style captchas (reCAPTCHA/hCaptcha)."""
        try:
            # Give captcha iframe time to render
            await asyncio.sleep(2)
            for frame in self.page.frames:
                try:
                    checkbox = frame.locator("input[type='checkbox'], div[role='checkbox']")
                    if await checkbox.count() > 0 and await checkbox.first.is_visible():
                        await checkbox.first.click()
                        await asyncio.sleep(1)
                        break
                except Exception:
                    continue
        except Exception:
            pass

    async def claim(self) -> ClaimResult:
        try:
            balance = await self.get_balance(".user-balance, .balance-text")
            # 1. Dutchy Roll
            await self._do_roll("roll.php", "Dutchy Roll")
            
            # 2. Coin Roll
            await self._do_roll("coin_roll.php", "Coin Roll")
            
            # 3. Shortlinks
            await self.claim_shortlinks()
            
            return ClaimResult(success=True, status="Dutchy cycle complete", next_claim_minutes=30, balance=balance)
        except Exception as e:
            logger.error(f"DutchyCorp claim cycle failed: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=15)

    async def claim_shortlinks(self):
        """Attempts to claim available shortlinks."""
        try:
            logger.info(f"[{self.faucet_name}] Checking Shortlinks...")
            await self.page.goto(f"{self.base_url}/shortlinks-wall.php")
            
            # Find available links
            # Updated to include .transparent-btn.tooltipped
            links = self.page.locator(".transparent-btn.tooltipped, a.btn.btn-primary:has-text('Claim')")
            count = await links.count()
            
            if count == 0:
                logger.info(f"[{self.faucet_name}] No shortlinks available.")
                return

            logger.info(f"[{self.faucet_name}] Found {count} shortlinks. Trying top 3...")
            
            # Attempt to find the blocker on page or context
            blocker = getattr(self.page, "resource_blocker", getattr(self.page.context, "resource_blocker", None))
            solver = ShortlinkSolver(self.page, blocker=blocker, captcha_solver=self.solver)
            
            for i in range(min(3, count)):
                # Re-query because DOM changes
                links = self.page.locator("a.btn.btn-primary:has-text('Claim')")
                if await links.count() <= i: break
                
                # Click 'Claim' to start
                # This usually redirects or opens a modal
                await links.nth(i).click()
                await asyncio.sleep(2)
                
                # Loop through the shortlink flow
                if await solver.solve(self.page.url):
                    logger.info(f"[{self.faucet_name}] Shortlink {i+1} Solved!")
                    await self.page.goto(f"{self.base_url}/shortlinks-wall.php")
                else:
                    logger.warning(f"[{self.faucet_name}] Shortlink {i+1} Failed.")
                    # Ensure we are back on wall
                    if "shortlinks-wall" not in self.page.url:
                        await self.page.goto(f"{self.base_url}/shortlinks-wall.php")
                        
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Shortlink error: {e}")

    async def _do_roll(self, page_slug, roll_name):
        try:
            logger.info(f"[{self.faucet_name}] Checking {roll_name}...")
            await self.page.goto(f"{self.base_url}/{page_slug}")
            await self.close_popups()
            
            # Check for timer / cooldown
            wait_min = await self.get_timer("#timer, .count_down_timer, .timer")
            if wait_min > 0:
                  logger.info(f"[{self.faucet_name}] {roll_name} is on cooldown: {wait_min}m")
                  return
            
            # Dutchy has an "Unlock" button sometimes
            unlock = self.page.locator("#unlockbutton")
            if await unlock.count() > 0 and await unlock.is_visible():
                logger.info(f"[{self.faucet_name}] Unlocking {roll_name}...")
                await self.human_like_click(unlock)
                await asyncio.sleep(2)

            # Dutchy has a "Boost" system before rolling sometimes
            boost = self.page.locator("#claim_boosted, button:has-text('Boost')")
            if await boost.count() > 0 and await boost.is_visible():
                 logger.info(f"[{self.faucet_name}] Applying boost for {roll_name}...")
                 await self.human_like_click(boost)
                 await self.random_delay()

            # Solve Captcha
            # Dutchy allows choosing Recaptcha/hCaptcha/Turnstile
            await self.handle_cloudflare()
            await self.solver.solve_captcha(self.page)

            # Roll Button - multiple potential selectors
            roll_btn = self.page.locator("#claim_boosted, button:has-text('Roll'), #roll_button, .roll-button")
            if await roll_btn.count() > 0:
                await self.human_like_click(roll_btn.first)
                await self.random_delay(3, 5)
                
                # Check for success message
                success = self.page.locator(".alert-success, .toast-success, text=/You received/")
                if await success.count() > 0:
                    logger.info(f"[{self.faucet_name}] {roll_name} claimed successfully!")
                else:
                    logger.info(f"[{self.faucet_name}] {roll_name} roll clicked.")
            else:
                logger.warning(f"[{self.faucet_name}] {roll_name} button not found.")
                
        except Exception as e:
            logger.error(f"[{self.faucet_name}] {roll_name} error: {e}")
    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for DutchyCorp."""
        try:
            logger.info(f"[{self.faucet_name}] Navigating to Balance/Withdrawal page...")
            await self.page.goto(f"{self.base_url}/balance.php")
            
            # DutchyCorp lists many coins. Find those with a 'Withdraw' button enabled.
            # Usually: button.btn-success:has-text('Withdraw')
            withdraw_btns = self.page.locator("a.btn.btn-success:has-text('Withdraw'), button:has-text('Withdraw')")
            count = await withdraw_btns.count()
            
            if count == 0:
                logger.info(f"[{self.faucet_name}] No balances ready for withdrawal.")
                return ClaimResult(success=True, status="No Balance", next_claim_minutes=1440)
            
            # Try to withdraw the first coin that meets threshold (or just the first one)
            # For Dutchy, we often want to withdraw LTC or DOGE to FaucetPay
            target_btn = None
            for i in range(count):
                btn = withdraw_btns.nth(i)
                parent_row = self.page.locator(f"tr:has(button:has-text('Withdraw')):nth-child({i+1})")
                # Try to extract balance from the row if possible, else just try the click
                await self.human_like_click(btn)
                await self.page.wait_for_load_state()
                target_btn = btn
                break

            if not target_btn:
                return ClaimResult(success=False, status="No Withdraw Button Found", next_claim_minutes=60)

            # Withdrawal Confirmation Page
            # 1. Select Method (FaucetPay is usually preferred)
            method_select = self.page.locator("select[name='method'], #withdrawal_method")
            if await method_select.count() > 0:
                # Try FaucetPay (value 1 or text)
                await method_select.select_option(label="FaucetPay")
                await asyncio.sleep(1)

            # 2. Solve Captcha
            await self.solver.solve_captcha(self.page)
            
            # 3. Final Confirm
            submit = self.page.locator("button:has-text('Withdraw'), #withdraw_button").last
            await self.human_like_click(submit)
            
            await self.random_delay(2, 4)
            
            # Check for success
            success = self.page.locator(".alert-success, .toast-success, :text-contains('Withdrawal has been sent')")
            if await success.count() > 0:
                logger.info(f"[{self.faucet_name}] Withdrawal successful!")
                return ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440)
            
            return ClaimResult(success=False, status="Withdrawal confirm failed or message not found", next_claim_minutes=120)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)

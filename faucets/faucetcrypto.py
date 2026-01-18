from .base import FaucetBot, ClaimResult
import logging
import asyncio

logger = logging.getLogger(__name__)

class FaucetCryptoBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "FaucetCrypto"
        self.base_url = "https://faucetcrypto.com"

    async def is_logged_in(self) -> bool:
        return "dashboard" in self.page.url

    async def login(self) -> bool:
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("faucetcrypto")
        
        if not creds:
            logger.error(f"[{self.faucet_name}] No credentials found.")
            return False

        try:
            logger.info(f"[{self.faucet_name}] Navigating to login...")
            # v4.0+ uses /login (not /login.php)
            await self.page.goto(f"{self.base_url}/login")
            await self.handle_cloudflare()
            
            if "dashboard" in self.page.url:
                logger.info(f"[{self.faucet_name}] Already logged in.")
                return True

            # v4.0+ may use different input names - try multiple selectors
            email_input = self.page.locator('input[name="email"], input[type="email"], #email')
            password_input = self.page.locator('input[name="password"], input[type="password"], #password')
            
            await email_input.first.fill(creds['username'])
            await password_input.first.fill(creds['password'])
            
            logger.info(f"[{self.faucet_name}] Solving login captcha...")
            await self.solver.solve_captcha(self.page)
            
            # v4.0+ button selectors
            login_btn = self.page.locator('button:has-text("Login"), button:has-text("Sign In"), input[type="submit"]')
            await self.human_like_click(login_btn.first)
            await self.page.wait_for_url("**/dashboard", timeout=15000)
            return True
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Login failed: {e}")
            return False

    async def claim(self) -> ClaimResult:
        try:
            balance = await self.get_balance(".user-balance, .balance-text")
            claim_btn = self.page.locator("button:has-text('Ready To Claim')")
            if await claim_btn.count() == 0:
                 # Check timer
                 wait_min = await self.get_timer(".fa-clock, .timer-text")
                 return ClaimResult(success=True, status="Timer Active", next_claim_minutes=wait_min or 20, balance=balance)
            
            # Click Claim
            await self.human_like_click(claim_btn)
            
            # Wait for internal timer (usually 10s)
            logger.info(f"[{self.faucet_name}] Waiting for timer...")
            await asyncio.sleep(15) 
            
            # Click "Get Reward"
            reward_btn = self.page.locator("button:has-text('Get Reward')")
            if await reward_btn.is_visible():
                await self.human_like_click(reward_btn)
                logger.info(f"[{self.faucet_name}] Claimed successfully.")
                return ClaimResult(success=True, status="Claimed", next_claim_minutes=30, balance=balance)
            
            return ClaimResult(success=False, status="Reward Button Not Found", next_claim_minutes=5, balance=balance)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Claim Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=30)

    def get_jobs(self):
        """
        Returns FaucetCrypto-specific jobs for the scheduler.
        """
        from core.orchestrator import Job
        import time
        
        jobs = []
        f_type = self.faucet_name.lower()
        
        # Job 1: Faucet Claim
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
        
        # Job 3: PTC Ads
        jobs.append(Job(
            priority=3,
            next_run=time.time() + 300,
            name=f"{self.faucet_name} PTC",
            profile=None,
            faucet_type=f_type,
            job_type="ptc_wrapper"
        ))
        
        return jobs

    async def view_ptc_ads(self):
        try:
            logger.info(f"[{self.faucet_name}] Checking PTC Ads...")
            await self.page.goto(f"{self.base_url}/ptc/list")
            
            # Find "Watch" buttons
            # Selector for available PTC ads
            ad_cards = self.page.locator(".ptc-card:not(.viewed), .card:has(button:has-text('Watch'))")
            count = await ad_cards.count()
            logger.info(f"[{self.faucet_name}] Found {count} potential PTC ads.")
            
            limit = 10
            processed = 0
            
            for i in range(count):
                if processed >= limit: break
                
                # Intermediate buttons on list page
                watch_btn = self.page.locator("button:has-text('Watch')").first
                if not await watch_btn.is_visible(): break
                
                logger.info(f"[{self.faucet_name}] Opening Ad {processed+1}...")
                await self.human_like_click(watch_btn)
                
                # 1. Intermediate Page (Step 1)
                # FaucetCrypto usually shows a 10s timer before "Get Reward"
                try:
                    await self.page.wait_for_selector("button:has-text('Get Reward')", timeout=20000)
                    reward_btn = self.page.locator("button:has-text('Get Reward')")
                    
                    # Sometimes there is an antibot check (select symbols in order)
                    # We look for turnstile/recaptcha first
                    await self.solver.solve_captcha(self.page)
                    
                    await self.human_like_click(reward_btn)
                except Exception as e:
                    logger.warning(f"[{self.faucet_name}] Intermediate page failed: {e}")
                    await self.page.goto(f"{self.base_url}/ptc/list")
                    continue

            # 2. Main Ad Page (Step 2)
            # Ad opens (usually in current tab or new tab depending on ad type)
            # Real internal PTCs open in current tab with a top bar timer
            logger.info(f"[{self.faucet_name}] Watching Ad timer...")
            
            # Poll for the "Continue" button on the top bar
            try:
                # Wait for the top bar timer to finish and "Continue" button to appear
                # v4.0+: Button often has a .success class when ready
                continue_btn = self.page.locator("#continue-button, button:has-text('Continue'), .btn-success:has-text('Continue')")
                await continue_btn.wait_for(state="visible", timeout=60000)
                await self.human_like_click(continue_btn)
                
                logger.info(f"[{self.faucet_name}] Ad {processed+1} completed.")
                processed += 1
            except Exception as e:
                logger.warning(f"[{self.faucet_name}] Failed to find Continue button: {e}")
                
                # Return to list
                await self.page.goto(f"{self.base_url}/ptc/list")
                await self.random_delay(2, 5)
                
            logger.info(f"[{self.faucet_name}] PTC session complete. Watched {processed} ads.")
                
        except Exception as e:
             logger.error(f"[{self.faucet_name}] PTC Error: {e}")

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for FaucetCrypto.
        
        FaucetCrypto uses a multi-step modal withdrawal process:
        1. Select cryptocurrency from withdrawal list
        2. Step I: Select Network
        3. Step II: Fill Info (amount + address)
        4. Step III: Review & Submit
        """
        try:
            logger.info(f"[{self.faucet_name}] Navigating to withdrawal page...")
            await self.page.goto(f"{self.base_url}/withdraw")
            await self.handle_cloudflare()
            
            # Get current balance
            balance = await self.get_balance(".user-balance, .balance-text")
            
            # Find available cryptocurrencies with withdraw buttons
            crypto_rows = self.page.locator(".crypto-row:has(button.withdraw-btn), .card:has(button:has-text('Withdraw'))")
            if await crypto_rows.count() == 0:
                logger.info(f"[{self.faucet_name}] No withdrawable balances found.")
                return ClaimResult(success=True, status="No Balance", next_claim_minutes=1440)
            
            # Click first available withdraw button
            withdraw_btn = crypto_rows.first.locator("button.withdraw-btn, button:has-text('Withdraw')")
            await self.human_like_click(withdraw_btn)
            await self.random_delay(2, 4)
            
            # Step I: Select Network (usually pre-selected or simple confirmation)
            next_btn = self.page.locator("button:has-text('Next Step'), button.next-step")
            if await next_btn.is_visible():
                await self.human_like_click(next_btn)
                await self.random_delay(1, 2)
            
            # Step II: Fill Info
            amount_field = self.page.locator("input[name='amount'], #amount")
            address_field = self.page.locator("input[name='address'], #wallet-address")
            
            # Use max available
            max_btn = self.page.locator("button:has-text('Max'), .max-btn")
            if await max_btn.is_visible():
                await self.human_like_click(max_btn)
            
            # Get withdrawal address (prioritize FaucetPay for lower thresholds)
            coin = "BTC"  # FaucetCrypto primarily uses BTC
            address = self.get_withdrawal_address(coin)
            if not address:
                logger.error(f"[{self.faucet_name}] No withdrawal address configured")
                return ClaimResult(success=False, status="No Address", next_claim_minutes=1440)
            
            await self.human_type(address_field, address)
            
            # Click Next Step to proceed to review
            next_btn = self.page.locator("button:has-text('Next Step'), button.next-step")
            if await next_btn.is_visible():
                await self.human_like_click(next_btn)
                await self.random_delay(1, 2)
            
            # Step III: Review & Submit
            # Look for confirmation switch if present
            confirm_switch = self.page.locator("input[type='checkbox'].confirm-switch, .confirm-checkbox")
            if await confirm_switch.is_visible():
                await confirm_switch.click()
            
            # Submit withdrawal
            submit_btn = self.page.locator("button:has-text('Submit Withdrawal'), button.submit-btn")
            await self.human_like_click(submit_btn)
            
            await self.random_delay(3, 5)
            
            # Check for success
            success_msg = self.page.locator(".alert-success, .toast-success, :has-text('Withdrawal submitted')")
            if await success_msg.count() > 0:
                logger.info(f"🚀 [{self.faucet_name}] Withdrawal submitted successfully!")
                return ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440)
            
            return ClaimResult(success=False, status="Withdrawal may be pending", next_claim_minutes=360)
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)

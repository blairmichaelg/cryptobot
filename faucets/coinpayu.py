from .base import FaucetBot, ClaimResult
import logging
import asyncio
import re

logger = logging.getLogger(__name__)

class CoinPayUBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "CoinPayU"
        self.base_url = "https://www.coinpayu.com"

    async def is_logged_in(self) -> bool:
        return "dashboard" in self.page.url or await self.page.query_selector("a[href*='logout']") is not None

    async def login(self) -> bool:
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("coinpayu")
        
        if not creds:
            logger.error(f"[{self.faucet_name}] No credentials found.")
            return False

        try:
            logger.info(f"[{self.faucet_name}] Navigating to login...")
            await self.page.goto(f"{self.base_url}/login")
            
            if "dashboard" in self.page.url:
                logger.info(f"[{self.faucet_name}] Already logged in.")
                return True

            # Accept cookies if present
            try: await self.page.click(".cookie-btn", timeout=2000)
            except: pass

            logger.info(f"[{self.faucet_name}] Filling credentials...")
            # CoinPayU blocks email aliases with '+', use base email
            base_email = self.strip_email_alias(creds['username'])
            await self.page.fill('input[placeholder="Email"]', base_email)
            await self.page.fill('input[placeholder="Password"]', creds['password'])
            
            # Check for Cloudflare Turnstile explicitly
            if await self.page.locator("#turnstile-container, .cf-turnstile").count() > 0:
                logger.info(f"[{self.faucet_name}] Cloudflare Turnstile detected.")

            await self.solver.solve_captcha(self.page)
            
            # Click Login
            await self.human_like_click(self.page.locator("button.btn-primary:has-text('Login')"))
            
            # Check for "Proxy detected" error
            error_msg = self.page.locator(".alert-div.alert-red")
            if await error_msg.count() > 0 and await error_msg.is_visible():
                text = await error_msg.inner_text()
                if "Proxy" in text:
                    logger.error(f"[{self.faucet_name}] Login Blocked: {text}")
                    return False

            await self.page.wait_for_url("**/dashboard", timeout=15000)
            logger.info(f"[{self.faucet_name}] Login successful.")
            return True
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Login failed: {e}")
            return False

    async def claim(self) -> ClaimResult:
        """
        Faucet claim for multiple coins (up to 4 per hour).
        """
        try:
            # Main dashboard balance
            description_card = self.page.locator(".v2-dashboard-card-value").first
            balance = await self.get_balance(".user-balance, .balance-text") if await description_card.count() == 0 else await description_card.inner_text()

            await self.page.goto(f"{self.base_url}/dashboard/faucet")
            
            # Target top 4 coins (logic can be expanded to be configurable)
            # Find all claim buttons
            claim_btns = self.page.locator(".btn-primary:has-text('Claim')")
            count = await claim_btns.count()
            
            claimed = 0
            for i in range(count):
                if claimed >= 4: break
                
                # Re-query list
                claim_btns = self.page.locator(".btn-primary:has-text('Claim')")
                await self.human_like_click(claim_btns.nth(i))
                await self.page.wait_for_load_state()

                # Secondary claim page
                final_btn = self.page.locator("#claim-now, .btn-primary:has-text('Claim Now')")
                if await final_btn.count() > 0:
                    await self.human_like_click(final_btn)
                    await self.random_delay(2, 4)
                    
                    # Watch for timer or captcha
                    await self.solver.solve_captcha(self.page)
                    
                    # Final "Claim Now" button after timer (sometimes appears)
                    confirm_btn = self.page.locator(".btn-primary:has-text('Claim Now')")
                    if await confirm_btn.count() > 0:
                         await self.human_like_click(confirm_btn)
                         await self.random_delay(2, 4)
                         claimed += 1
                
                # Go back to faucet list
                await self.page.goto(f"{self.base_url}/dashboard/faucet")
            
            return ClaimResult(success=claimed > 0, status=f"Claimed {claimed} coins", next_claim_minutes=60, balance=balance)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Claim Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)

    def get_jobs(self):
        """
        Returns CoinPayU-specific jobs for the scheduler.
        """
        from core.orchestrator import Job
        import time
        
        jobs = []
        
        # 1. Faucet Claim (Hourly)
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            func=self.claim_wrapper,
            faucet_type=self.faucet_name.lower()
        ))
        
        # 2. PTC/Surf Ads (Periodically)
        jobs.append(Job(
            priority=3,
            next_run=time.time() + 300,
            name=f"{self.faucet_name} PTC",
            profile=None,
            func=self.ptc_wrapper,
            faucet_type=self.faucet_name.lower()
        ))

        # 3. Consolidation Job (Faucet -> Main)
        jobs.append(Job(
            priority=4,
            next_run=time.time() + 7200, # Every 2 hours
            name=f"{self.faucet_name} Consolidate",
            profile=None,
            func=self.consolidate_wrapper,
            faucet_type=self.faucet_name.lower()
        ))

        # 4. Withdraw Job (Daily)
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            func=self.withdraw_wrapper,
            faucet_type=self.faucet_name.lower()
        ))
        
        return jobs

    async def consolidate_wrapper(self, page) -> ClaimResult:
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login/Access Failed", next_claim_minutes=30)
        return await self.transfer_faucet_to_main()

    async def transfer_faucet_to_main(self) -> ClaimResult:
        """Moves funds from the faucet balances to the main withdrawal balance."""
        try:
            logger.info(f"[{self.faucet_name}] Starting Faucet -> Main transfer...")
            await self.page.goto(f"{self.base_url}/dashboard/faucet")
            
            # Find all Transfer buttons
            transfer_btns = self.page.locator("button:has-text('Transfer')")
            count = await transfer_btns.count()
            
            transferred = 0
            for i in range(count):
                transfer_btns = self.page.locator("button:has-text('Transfer')")
                btn = transfer_btns.nth(i)
                
                # Check if specific coin balance is enough (usually 100-500 satoshi equivalent)
                # For simplicity, we try the click and check for error/success
                await self.human_like_click(btn)
                await self.page.wait_for_load_state()
                
                # Transfer Modal or Page
                confirm = self.page.locator("button.btn-primary:has-text('Transfer'), #transfer-btn")
                amount_input = self.page.locator("input[name='amount'], #transfer-amount")
                
                if await confirm.count() > 0:
                    # Max amount is usually the default, if not, fill it
                    val = await amount_input.get_attribute("placeholder") or "0"
                    if "min" in val.lower():
                         # Need to extract actual balance to see if we meet min
                         pass 
                    
                    await self.human_like_click(confirm)
                    await asyncio.sleep(2)
                    transferred += 1
                
                await self.page.goto(f"{self.base_url}/dashboard/faucet")

            return ClaimResult(success=True, status=f"Transferred {transferred} coins", next_claim_minutes=120)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Transfer Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)

    async def withdraw(self) -> ClaimResult:
        """Main balance withdrawal."""
        try:
            logger.info(f"[{self.faucet_name}] Executing Main Balance withdrawal...")
            await self.page.goto(f"{self.base_url}/dashboard/withdraw")
            
            # 1. Select Method (Research identified: //div[contains(@class, 'select-method')])
            method_dropdown = self.page.locator(".select-method, input[placeholder='Select Method']")
            await self.human_like_click(method_dropdown)
            await asyncio.sleep(1)
            
            # Select first available (usually BTC or FaucetPay if configured)
            # This is site-dependent, assuming first option for now
            await self.page.keyboard.press("Enter")
            
            # 2. Confirm Amount (usually auto-filled with Max)
            confirm_btn = self.page.locator("button.btn-primary:has-text('Confirm')")
            if await confirm_btn.count() > 0:
                await self.human_like_click(confirm_btn)
                await self.random_delay(2, 4)
                
                # Check for 2FA or Captcha
                await self.solver.solve_captcha(self.page)
                
                # Check for 2FA field (if user has it enabled)
                otp_field = self.page.locator("input[name='google_code'], input[placeholder*='2FA']")
                if await otp_field.count() > 0:
                     logger.warning(f"[{self.faucet_name}] 2FA required for withdrawal. Bot paused.")
                     return ClaimResult(success=False, status="2FA Required", next_claim_minutes=1440)
                
                # Final Final Confirm
                final_btn = self.page.locator("button.btn-primary:has-text('Confirm')").last
                await self.human_like_click(final_btn)
                
                logger.info(f"[{self.faucet_name}] Withdrawal request submitted!")
                return ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440)

            return ClaimResult(success=False, status="Withdrawal Button Not Found", next_claim_minutes=60)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal Error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)

    async def view_ptc_ads(self):
        """
        CoinPayU Surf Ads logic.
        """
        try:
            logger.info(f"[{self.faucet_name}] Checking Surf Ads...")
            await self.page.goto(f"{self.base_url}/dashboard/ads_surf") # Updated URL
            
            # Wait for list or no-ads message
            try:
                await self.page.wait_for_selector(".ags-list-box, .no-ads", timeout=10000)
            except: pass
            
            # Ads that are NOT grayed out (unclicked)
            ad_items = self.page.locator(".clearfix.ags-list-box:not(.gray-all)")
            count = await ad_items.count()
            logger.info(f"[{self.faucet_name}] Found {count} unclicked Surf Ads.")
            
            processed = 0
            limit = 10
            
            while processed < limit:
                # Always target the first unclicked ad
                ad_items = self.page.locator(".clearfix.ags-list-box:not(.gray-all)")
                if await ad_items.count() == 0: break
                
                item = ad_items.first
                
                # Extract duration
                duration_text = await item.locator(".ags-detail-time span").first.inner_text()
                match = re.search(r'(\d+)', duration_text)
                duration = int(match.group(1)) if match else 15

                logger.info(f"[{self.faucet_name}] Clicking Surf Ad {processed+1} ({duration}s)...")
                
                async with self.page.context.expect_page() as new_page_info:
                    # Click the title span
                    await self.human_like_click(item.locator(".text-overflow.ags-description > span, a.title").first)
                
                ad_page = await new_page_info.value
                
                # SURF ADS: Timer is on the MAIN tab. Ad tab just needs to exist.
                # We can stay on the main page and monitor the timer or just wait.
                await asyncio.sleep(duration + 5)
                
                await ad_page.close()
                await self.random_delay(2, 4)
                
                # Check for interruption captcha on main page
                if await self.page.locator("#turnstile-container, .cf-turnstile, .captcha-container").count() > 0:
                     logger.info(f"[{self.faucet_name}] Captcha detected during Surf Ads.")
                     await self.solver.solve_captcha(self.page)
                     await self.random_delay()
                
                processed += 1
            
            logger.info(f"[{self.faucet_name}] Surf Ads session complete. Watched {processed} ads.")
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] PTC Error: {e}")

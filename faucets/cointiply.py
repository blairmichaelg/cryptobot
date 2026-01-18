from .base import FaucetBot, ClaimResult
import logging
import asyncio

logger = logging.getLogger(__name__)

class CointiplyBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "Cointiply"
        self.base_url = "https://cointiply.com"

    async def is_logged_in(self) -> bool:
        return "dashboard" in self.page.url or await self.page.locator(".user-balance-coins, .user-balance").is_visible()

    async def get_current_balance(self) -> str:
        # Priority: .user-balance-coins, fallback: .user-balance
        balance = await self.get_balance(".user-balance-coins")
        if balance == "0":
            balance = await self.get_balance(".user-balance")
        return balance

    async def view_ptc_ads(self):
        """
        Views PTC ads with focused-tab management.
        """
        try:
            logger.info(f"[{self.faucet_name}] Checking PTC Ads...")
            await self.page.goto(f"{self.base_url}/ptc")
            
            # 1. Update selector for PTC View Button
            ads = self.page.locator("button.view-ad-button, .btn-success:has-text('View')")
            count = await ads.count()
            if count == 0:
                logger.info(f"[{self.faucet_name}] No PTC ads available.")
                return

            limit = 5
            logger.info(f"[{self.faucet_name}] Found {count} PTC Ads. Watching top {limit}...")
            
            for i in range(limit):
                ads = self.page.locator("button.view-ad-button, .btn-success:has-text('View')")
                if await ads.count() == 0: break
                
                async with self.page.context.expect_page() as new_page_info:
                    await self.human_like_click(ads.first)
                
                ad_page = await new_page_info.value
                await ad_page.wait_for_load_state("domcontentloaded")
                
                # Cointiply PTC requires active focus for the timer to count
                await ad_page.bring_to_front()
                
                # Dynamic duration extraction (usually 10-30s)
                # For safety, wait 35s
                await asyncio.sleep(35)
                
                # Switch back to resolve any verification if needed
                await self.page.bring_to_front()
                await ad_page.close()
                await self.random_delay(2, 4)
                
                # Check for "Unique Image" Verification
                verify_container = self.page.locator("#captcha-images, .ptc-verify-container")
                if await verify_container.is_visible():
                     logger.info(f"[{self.faucet_name}] Multi-image verification detected.")
                     # Generic solver should attempt to find the unique one
                     await self.solver.solve_captcha(self.page)
                
        except Exception as e:
            logger.error(f"[{self.faucet_name}] PTC Error: {e}")

    async def login(self) -> bool:
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("cointiply")
            
        if not creds: 
            return False

        try:
            await self.page.goto(f"{self.base_url}/login")
            await self.page.fill('input[name="email"]', creds['username'])
            await self.page.fill('input[name="password"]', creds['password'])
            
            await self.solver.solve_captcha(self.page)
            
            submit = self.page.locator('button:has_text("Login")')
            await self.human_like_click(submit)
            
            await self.page.wait_for_url("**/home", timeout=15000)
            return True
        except Exception as e:
            logger.error(f"Cointiply login failed: {e}")
            return False

    async def parse_claim_timer(self) -> float:
        try:
            # Check for "Claims are available" or timer
            # Cointiply usually shows "Next Claim In: 59m 59s" or similar
            # Or just doesn't show the roll button
            return 0.0 # Placeholder, Cointiply logic is trickier without logging in
        except:
            pass
        return 0.0

    async def claim(self) -> ClaimResult:
        try:
            await self.page.goto(f"{self.base_url}/faucet")
            
            balance = await self.get_current_balance()
            
            # Check for Roll Button
            roll = self.page.locator("#claim_button, button.faucet-claim-btn, button:has-text('Roll & Win')")
            if await roll.count() > 0 and await roll.is_visible():
                # Check for "Ready" or text indicators
                timer_text = await self.page.locator(".timer_display, #timer_display").first.inner_text() if await self.page.locator(".timer_display, #timer_display").count() > 0 else ""
                
                if "Ready" in timer_text or not any(char.isdigit() for char in timer_text):
                    await self.solver.solve_captcha(self.page)
                    await self.human_like_click(roll)
                    
                    # Check for Success/Snackbars
                    await asyncio.sleep(3)
                    if await self.page.locator(".md-snackbar-content, .toast-success").count() > 0:
                         logger.info("Cointiply rolled successfully.")
                         return ClaimResult(success=True, status="Claimed", next_claim_minutes=60, balance=balance)
                    
                    return ClaimResult(success=True, status="Rolled", next_claim_minutes=60, balance=balance)
            
            # Check Timer fallback
            wait_min = await self.get_timer(".timer_display, #timer_display, .timer-text")
            if wait_min > 0:
                 return ClaimResult(success=True, status="Timer Active", next_claim_minutes=wait_min, balance=balance)

            return ClaimResult(success=False, status="Roll Not Available", next_claim_minutes=15, balance=balance)
            
        except Exception as e:
            logger.error(f"Cointiply claim failed: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=30)

    def get_jobs(self):
        """Returns Cointiply-specific jobs for the scheduler."""
        from core.orchestrator import Job
        import time
        
        return [
            Job(
                priority=1,
                next_run=time.time(),
                name=f"{self.faucet_name} Claim",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="claim_wrapper"
            ),
            Job(
                priority=5,
                next_run=time.time() + 7200,  # Check withdrawal every 2 hours
                name=f"{self.faucet_name} Withdraw",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="withdraw_wrapper"
            ),
            Job(
                priority=3,
                next_run=time.time() + 600,
                name=f"{self.faucet_name} PTC",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="ptc_wrapper"
            )
        ]

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for Cointiply.
        
        Supports BTC, LTC, DOGE, DASH with varying thresholds:
        - BTC: 50,000 coins minimum
        - LTC/DOGE/DASH: 30,000 coins minimum
        """
        try:
            logger.info(f"[{self.faucet_name}] Navigating to withdrawal page...")
            await self.page.goto(f"{self.base_url}/withdraw")
            await self.handle_cloudflare()
            
            # Get current balance in coins
            balance = await self.get_current_balance()
            balance_coins = float(balance) if balance else 0
            
            # Check minimum thresholds
            min_btc = 50000
            min_other = 30000
            
            if balance_coins < min_other:
                logger.info(f"[{self.faucet_name}] Balance {balance_coins} below minimum threshold")
                return ClaimResult(success=True, status="Low Balance", next_claim_minutes=1440)
            
            # Select cryptocurrency based on balance and configured wallets
            coin = None
            if balance_coins >= min_btc:
                coin = "BTC"
            else:
                for c in ["LTC", "DOGE", "DASH"]:
                    addr = self.get_withdrawal_address(c)
                    if addr:
                        coin = c
                        break
            
            if not coin:
                logger.warning(f"[{self.faucet_name}] No suitable withdrawal option")
                return ClaimResult(success=False, status="No Suitable Option", next_claim_minutes=1440)
            
            # Click on the coin tab/button
            coin_selector = self.page.locator(f"button:has-text('{coin}'), .crypto-tab:has-text('{coin}')")
            if await coin_selector.is_visible():
                await self.human_like_click(coin_selector)
                await self.random_delay(1, 2)
            
            # Fill wallet address
            address_field = self.page.locator("input[name='address'], input.wallet-address, #address")
            address = self.get_withdrawal_address(coin)
            await self.human_type(address_field, address)
            
            # Solve captcha if present
            await self.solver.solve_captcha(self.page)
            
            # Click withdraw
            withdraw_btn = self.page.locator("button:has-text('Withdraw'), button.withdraw-btn")
            await self.human_like_click(withdraw_btn)
            
            await self.random_delay(3, 5)
            
            # Check result
            content = await self.page.content()
            if "success" in content.lower() or "email" in content.lower():
                logger.info(f"🚀 [{self.faucet_name}] Withdrawal request submitted! Check email for confirmation.")
                return ClaimResult(success=True, status="Withdrawn (Pending Email)", next_claim_minutes=1440)
            
            return ClaimResult(success=False, status="Unknown Result", next_claim_minutes=360)
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)

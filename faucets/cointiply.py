from .base import FaucetBot, ClaimResult
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class CointiplyBot(FaucetBot):
    """
    Cointiply faucet bot implementation.
    
    Supports:
    - Faucet claims with timer-based scheduling
    - PTC ad viewing for bonus earnings
    - Automated withdrawals to multiple cryptocurrencies
    """
    
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "Cointiply"
        self.base_url = "https://cointiply.com"

    async def is_logged_in(self) -> bool:
        return "dashboard" in self.page.url or await self.page.locator(".user-balance-coins, .user-balance").is_visible()

    async def get_current_balance(self) -> str:
        """
        Get current balance from Cointiply dashboard.
        
        Returns:
            Balance as string. Returns "0" if extraction fails.
        """
        # Priority: .user-balance-coins, fallback: .user-balance
        balance = await self.get_balance(
            ".user-balance-coins", 
            fallback_selectors=[".user-balance"]
        )
        logger.debug(f"[{self.faucet_name}] Current balance: {balance}")
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
        """
        Authenticate with Cointiply using credentials.
        
        Returns:
            True if login successful, False otherwise.
        """
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("cointiply")
            
        if not creds: 
            logger.warning(f"[{self.faucet_name}] No credentials configured")
            return False

        try:
            logger.info(f"[{self.faucet_name}] Starting login process")
            nav_timeout = getattr(self.settings, "timeout", 180000)
            try:
                await self.page.goto(f"{self.base_url}/login", wait_until="domcontentloaded", timeout=nav_timeout)
            except Exception as e:
                logger.warning(f"[{self.faucet_name}] Login navigation retry with commit: {e}")
                await self.page.goto(f"{self.base_url}/login", wait_until="commit", timeout=nav_timeout)
            await self.handle_cloudflare()
            
            # Use human_type for stealth
            email_input = self.page.locator('input[name="email"]')
            await self.human_type(email_input, creds['username'])
            await self.random_delay(0.5, 1.5)
            
            password_input = self.page.locator('input[name="password"]')
            await self.human_type(password_input, creds['password'])
            await self.random_delay(0.5, 1.5)
            
            # Solve CAPTCHA if present
            logger.debug(f"[{self.faucet_name}] Attempting CAPTCHA solve")
            captcha_solved = await self.solver.solve_captcha(self.page)
            if not captcha_solved:
                logger.warning(f"[{self.faucet_name}] CAPTCHA solving failed or not present")
            
            # Simulate human behavior before submitting
            await self.idle_mouse(1.0)
            
            submit = self.page.locator('button:has-text("Login")')
            await self.human_like_click(submit)
            
            # Wait for navigation with timeout
            await self.page.wait_for_url("**/home", timeout=30000)
            logger.info(f"[{self.faucet_name}] ✅ Login successful")
            return True
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] ❌ Login failed: {e}")
            return False

    async def claim(self) -> ClaimResult:
        """
        Execute faucet claim with robust error handling and timer extraction.
        
        Returns:
            ClaimResult with success status, next claim time, and balance.
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"[{self.faucet_name}] Starting claim process (attempt {retry_count + 1}/{max_retries})")
                
                nav_timeout = getattr(self.settings, "timeout", 180000)
                try:
                    await self.page.goto(f"{self.base_url}/faucet", wait_until="domcontentloaded", timeout=nav_timeout)
                except Exception as e:
                    logger.warning(f"[{self.faucet_name}] Faucet navigation retry with commit: {e}")
                    await self.page.goto(f"{self.base_url}/faucet", wait_until="commit", timeout=nav_timeout)
                await self.handle_cloudflare()
                
                # Extract current balance
                balance = await self.get_current_balance()
                logger.debug(f"[{self.faucet_name}] Balance before claim: {balance}")
                
                # Check for Roll Button
                roll = self.page.locator("#claim_button, button.faucet-claim-btn, button:has-text('Roll & Win')")
                roll_count = await roll.count()
                
                if roll_count > 0 and await roll.is_visible():
                    logger.debug(f"[{self.faucet_name}] Roll button found and visible")
                    
                    # Extract timer using DataExtractor
                    timer_selectors = [".timer_display", "#timer_display", ".timer-text"]
                    timer_mins = await self.get_timer(
                        timer_selectors[0], 
                        fallback_selectors=timer_selectors[1:]
                    )
                    
                    logger.debug(f"[{self.faucet_name}] Timer extracted: {timer_mins} minutes")
                    
                    # Check if timer is ready (0 or very close to 0)
                    if timer_mins < 1.0:
                        logger.info(f"[{self.faucet_name}] Timer ready, proceeding with claim")
                        
                        # Simulate human behavior before solving CAPTCHA
                        await self.idle_mouse(1.5)
                        
                        # Solve CAPTCHA
                        logger.debug(f"[{self.faucet_name}] Attempting CAPTCHA solve")
                        captcha_solved = await self.solver.solve_captcha(self.page)
                        
                        if not captcha_solved:
                            logger.warning(f"[{self.faucet_name}] CAPTCHA solving failed")
                            retry_count += 1
                            if retry_count >= max_retries:
                                return ClaimResult(
                                    success=False,
                                    status="CAPTCHA failed after retries",
                                    next_claim_minutes=30,
                                    balance=balance
                                )
                            await asyncio.sleep(5)
                            continue
                        
                        # Click roll button with human-like behavior
                        await self.random_delay(0.5, 1.5)
                        await self.human_like_click(roll)
                        
                        # Wait for result
                        await asyncio.sleep(3)
                        
                        # Check for success indicators
                        success_selectors = [".md-snackbar-content", ".toast-success", ".alert-success"]
                        success_found = False
                        
                        for sel in success_selectors:
                            if await self.page.locator(sel).count() > 0:
                                success_found = True
                                logger.info(f"[{self.faucet_name}] ✅ Claim successful")
                                break
                        
                        # Get updated balance
                        new_balance = await self.get_current_balance()
                        
                        if success_found:
                            # Typical Cointiply claim interval is 60 minutes
                            return ClaimResult(
                                success=True, 
                                status="Claimed", 
                                next_claim_minutes=60, 
                                balance=new_balance
                            )
                        else:
                            logger.info(f"[{self.faucet_name}] Roll completed (success uncertain)")
                            return ClaimResult(
                                success=True, 
                                status="Rolled", 
                                next_claim_minutes=60, 
                                balance=new_balance
                            )
                    else:
                        logger.info(f"[{self.faucet_name}] Timer active: {timer_mins:.1f} minutes remaining")
                        return ClaimResult(
                            success=True, 
                            status="Timer Active", 
                            next_claim_minutes=timer_mins, 
                            balance=balance
                        )
                else:
                    logger.warning(f"[{self.faucet_name}] Roll button not found or not visible")
                    # Default wait time if roll button is missing
                    return ClaimResult(
                        success=False, 
                        status="Roll Not Available", 
                        next_claim_minutes=15, 
                        balance=balance
                    )
                    
            except asyncio.TimeoutError as e:
                logger.warning(f"[{self.faucet_name}] Timeout error (attempt {retry_count + 1}): {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    return ClaimResult(
                        success=False, 
                        status="Timeout after retries", 
                        next_claim_minutes=30
                    )
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"[{self.faucet_name}] ❌ Claim failed: {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    return ClaimResult(
                        success=False, 
                        status=f"Error: {str(e)[:50]}", 
                        next_claim_minutes=30
                    )
                await asyncio.sleep(5)

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

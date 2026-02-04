from .base import FaucetBot, ClaimResult
import logging
import asyncio
import random

logger = logging.getLogger(__name__)

class FaucetCryptoBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "FaucetCrypto"
        self.base_url = "https://faucetcrypto.com"

    async def is_logged_in(self) -> bool:
        return "dashboard" in self.page.url

    async def login(self) -> bool:
        """
        Login to FaucetCrypto with enhanced stealth and error handling.
        
        Returns:
            True if login successful, False otherwise
        """
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("faucetcrypto")
        
        if not creds:
            logger.error(f"[{self.faucet_name}] No credentials found.")
            return False
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                logger.info(f"[{self.faucet_name}] Navigating to login page (attempt {attempt + 1}/{max_retries})...")
                # v4.0+ uses /login (not /login.php)
                nav_timeout = max(getattr(self.settings, "timeout", 180000), 120000)  # At least 120s
                try:
                    await self.page.goto(f"{self.base_url}/login", wait_until="domcontentloaded", timeout=nav_timeout)
                except Exception as e:
                    error_str = str(e)
                    if "Timeout" in error_str:
                        logger.warning(f"[{self.faucet_name}] domcontentloaded timeout, trying networkidle...")
                        await self.page.goto(f"{self.base_url}/login", wait_until="networkidle", timeout=nav_timeout)
                    else:
                        logger.warning(f"[{self.faucet_name}] Login navigation retry with commit: {e}")
                        await self.page.goto(f"{self.base_url}/login", wait_until="commit", timeout=nav_timeout)
                await self.handle_cloudflare()
                await self.random_delay(1, 2)
                
                # Check if already logged in
                if "dashboard" in self.page.url:
                    logger.info(f"[{self.faucet_name}] ✅ Already logged in.")
                    return True

                # Simulate human behavior before interacting
                await self.idle_mouse(duration=random.uniform(0.5, 1.5))
                
                # v4.0+ may use different input names - try multiple selectors
                email_input = self.page.locator('input[name="email"], input[type="email"], #email')
                password_input = self.page.locator('input[name="password"], input[type="password"], #password')
                
                # Use human_type for stealth instead of fill
                logger.info(f"[{self.faucet_name}] Entering credentials...")
                await self.human_type(email_input.first, creds['username'])
                await self.random_delay(0.5, 1.0)
                await self.human_type(password_input.first, creds['password'])
                await self.random_delay(0.5, 1.0)
                
                # Solve CAPTCHA if present
                logger.info(f"[{self.faucet_name}] Checking for login CAPTCHA...")
                captcha_solved = await self.solver.solve_captcha(self.page)
                if captcha_solved:
                    logger.info(f"[{self.faucet_name}] Login CAPTCHA solved successfully")
                    await self.random_delay(1, 2)
                
                # Click login button with human-like behavior
                logger.info(f"[{self.faucet_name}] Clicking login button...")
                login_btn = self.page.locator('button:has-text("Login"), button:has-text("Sign In"), input[type="submit"]')
                await self.human_like_click(login_btn.first)
                
                # Wait for navigation to dashboard
                await self.page.wait_for_url("**/dashboard", timeout=30000)
                logger.info(f"[{self.faucet_name}] ✅ Login successful!")
                return True
                
            except TimeoutError as e:
                logger.warning(f"[{self.faucet_name}] Login timeout (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
            except Exception as e:
                logger.error(f"[{self.faucet_name}] Login failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
        
        logger.error(f"[{self.faucet_name}] ❌ Login failed after {max_retries} attempts")
        return False

    async def claim(self) -> ClaimResult:
        """
        Claim from FaucetCrypto with optimized stealth, robustness, and profitability.
        
        Returns:
            ClaimResult with success status, next claim time, and balance
        """
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                # Navigate to faucet page if not already there
                if "faucet" not in self.page.url.lower():
                    logger.info(f"[{self.faucet_name}] Navigating to faucet page...")
                    nav_timeout = getattr(self.settings, "timeout", 180000)
                    try:
                        await self.page.goto(f"{self.base_url}/faucet", wait_until="domcontentloaded", timeout=nav_timeout)
                    except Exception as e:
                        logger.warning(f"[{self.faucet_name}] Faucet navigation retry with commit: {e}")
                        await self.page.goto(f"{self.base_url}/faucet", wait_until="commit", timeout=nav_timeout)
                    await self.handle_cloudflare()
                    await self.random_delay(1, 3)
                
                # Simulate human reading behavior
                await self.idle_mouse(duration=random.uniform(1.0, 2.0))
                
                # Extract balance with fallback selectors
                balance = await self.get_balance(
                    ".user-balance",
                    fallback_selectors=[".balance-text", "[class*='balance']", "#balance"]
                )
                logger.info(f"[{self.faucet_name}] Current balance: {balance}")
                
                # Check if claim button is available
                claim_btn = self.page.locator("button:has-text('Ready To Claim'), button:has-text('Claim Now'), .claim-button")
                if await claim_btn.count() == 0:
                    # Timer is active - extract actual wait time
                    logger.info(f"[{self.faucet_name}] Claim button not ready, checking timer...")
                    wait_min = await self.get_timer(
                        ".timer-text",
                        fallback_selectors=[".fa-clock", "[class*='timer']", "[class*='countdown']", "#timer"]
                    )
                    if wait_min == 0.0:
                        wait_min = 20.0  # Default fallback
                    logger.info(f"[{self.faucet_name}] Timer active: {wait_min:.1f} minutes remaining")
                    return ClaimResult(
                        success=True, 
                        status="Timer Active", 
                        next_claim_minutes=wait_min, 
                        balance=balance
                    )
                
                # Click claim button
                logger.info(f"[{self.faucet_name}] Clicking claim button...")
                await self.human_like_click(claim_btn.first)
                
                # Wait for internal countdown timer (10-15s typically)
                # Use random delay for stealth
                logger.info(f"[{self.faucet_name}] Waiting for internal timer...")
                await self.random_delay(12, 18)
                
                # Simulate user activity while waiting
                await self.idle_mouse(duration=random.uniform(0.5, 1.5))
                
                # Solve CAPTCHA if present
                logger.info(f"[{self.faucet_name}] Checking for CAPTCHA...")
                captcha_solved = await self.solver.solve_captcha(self.page)
                if captcha_solved:
                    logger.info(f"[{self.faucet_name}] CAPTCHA solved successfully")
                    await self.random_delay(1, 2)
                
                # Click "Get Reward" button
                reward_btn = self.page.locator("button:has-text('Get Reward'), button:has-text('Collect'), .reward-button")
                if await reward_btn.is_visible(timeout=5000):
                    logger.info(f"[{self.faucet_name}] Clicking reward button...")
                    await self.human_like_click(reward_btn.first)
                    await self.random_delay(2, 4)
                    
                    # Extract updated balance
                    new_balance = await self.get_balance(
                        ".user-balance",
                        fallback_selectors=[".balance-text", "[class*='balance']", "#balance"]
                    )
                    
                    # Extract next claim timer for accurate scheduling
                    next_claim_min = await self.get_timer(
                        ".timer-text",
                        fallback_selectors=[".fa-clock", "[class*='timer']", "[class*='countdown']", "#timer"]
                    )
                    if next_claim_min == 0.0:
                        next_claim_min = 30.0  # Default to 30 min if extraction fails
                    
                    logger.info(f"[{self.faucet_name}] ✅ Claim successful! Balance: {new_balance}, Next claim: {next_claim_min:.1f}min")
                    return ClaimResult(
                        success=True, 
                        status="Claimed", 
                        next_claim_minutes=next_claim_min,
                        amount="claimed",  # Could extract specific amount if visible
                        balance=new_balance
                    )
                
                logger.warning(f"[{self.faucet_name}] Reward button not found after timer")
                return ClaimResult(
                    success=False, 
                    status="Reward Button Not Found", 
                    next_claim_minutes=5, 
                    balance=balance
                )
            
            except TimeoutError as e:
                logger.warning(f"[{self.faucet_name}] Timeout error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return ClaimResult(
                    success=False, 
                    status=f"Timeout after {max_retries} attempts", 
                    next_claim_minutes=15
                )
            
            except Exception as e:
                logger.error(f"[{self.faucet_name}] Claim error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return ClaimResult(
                    success=False, 
                    status=f"Error: {e}", 
                    next_claim_minutes=30
                )
        
        # Should never reach here, but just in case
        return ClaimResult(
            success=False, 
            status="Max retries exceeded", 
            next_claim_minutes=30
        )

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

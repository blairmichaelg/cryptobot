import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional, Union
from playwright.async_api import Page, Locator
from solvers.captcha import CaptchaSolver
from core.config import BotSettings

from core.extractor import DataExtractor
from core.analytics import get_tracker

logger = logging.getLogger(__name__)

@dataclass
class ClaimResult:
    success: bool
    status: str
    next_claim_minutes: float = 0
    amount: str = "0"
    balance: str = "0"

class FaucetBot:
    """Base class for Faucet Bots."""
    
    def __init__(self, settings: BotSettings, page: Page, action_lock: asyncio.Lock = None):
        """
        Initialize the FaucetBot.

        Args:
            settings: Configuration settings for the bot.
            page: The Playwright Page instance to control.
            action_lock: An asyncio.Lock to prevent simultaneous actions across multiple bot instances.
        """
        self.settings = settings
        self.page = page
        self.action_lock = action_lock
        # Initialize solver
        provider = settings.captcha_provider.lower()
        key = settings.capsolver_api_key if provider == "capsolver" else settings.twocaptcha_api_key
        self.solver = CaptchaSolver(api_key=key, provider=provider)
            
        self.faucet_name = "Generic"
        self.base_url = ""
        self.base_url = ""
        self.settings_account_override = None # Allow manual injection of credentials

    def set_proxy(self, proxy_string: str):
        """Pass the proxy string to the underlying solver."""
        if self.solver:
            self.solver.set_proxy(proxy_string)

    @staticmethod
    def strip_email_alias(email: Optional[str]) -> Optional[str]:
        """
        Strip email alias (plus addressing) from email address.
        
        Converts 'user+alias@example.com' to 'user@example.com'.
        Some faucets (CoinPayU, AdBTC) block email aliases with '+'.
        
        Args:
            email: The email address that may contain a '+' alias.
                   Can be None or empty string.
        
        Returns:
            The base email address without the alias.
            Returns the input unchanged if it's None, empty, or doesn't contain '@'.
        """
        if email is None or not email or '@' not in email:
            return email
        
        local_part, domain = email.rsplit('@', 1)
        if '+' in local_part:
            base_local = local_part.split('+')[0]
            return f"{base_local}@{domain}"
        
        return email

    def get_credentials(self, faucet_name: str):
        """
        Centralized credential retrieval with override support.
        
        Args:
            faucet_name: The name of the faucet to get credentials for.
        
        Returns:
            Credentials dict or None if not found.
        """
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            return self.settings_account_override
        return self.settings.get_account(faucet_name)

    def get_withdrawal_address(self, coin: str) -> Optional[str]:
        """
        Get the appropriate withdrawal address based on configuration.
        
        Checks settings.use_faucetpay first, falls back to direct wallet.
        Priority: FaucetPay → Direct Wallet → wallet_addresses dict
        
        Args:
            coin: Cryptocurrency symbol (BTC, LTC, DOGE, TRX, ETH, etc.)
            
        Returns:
            Withdrawal address string, or None if not configured
        """
        coin = coin.upper()
        
        # Normalize coin name variations
        coin_map = {
            "LITE": "LTC",
            "TRON": "TRX",
            "POLYGON": "MATIC",
            "BINANCE": "BNB"
        }
        coin = coin_map.get(coin, coin)
        
        # 1. FaucetPay mode (preferred for micro-earnings)
        if self.settings.use_faucetpay:
            fp_attr = f"faucetpay_{coin.lower()}_address"
            fp_address = getattr(self.settings, fp_attr, None)
            if fp_address:
                logger.debug(f"[{self.faucet_name}] Using FaucetPay address for {coin}")
                return fp_address
        
        # 2. Direct wallet mode
        direct_attr = f"{coin.lower()}_withdrawal_address"
        direct_address = getattr(self.settings, direct_attr, None)
        if direct_address:
            logger.debug(f"[{self.faucet_name}] Using direct wallet address for {coin}")
            return direct_address
        
        # 3. Fallback to wallet_addresses dict
        if hasattr(self.settings, 'wallet_addresses'):
            dict_address = self.settings.wallet_addresses.get(coin)
            if dict_address:
                logger.debug(f"[{self.faucet_name}] Using wallet_addresses dict for {coin}")
                return dict_address
        
        logger.warning(f"[{self.faucet_name}] No withdrawal address configured for {coin}")
        return None


    async def random_delay(self, min_s=2, max_s=5):
        """
        Wait for a random amount of time to mimic human behavior.

        Args:
            min_s: Minimum wait time in seconds.
            max_s: Maximum wait time in seconds.
        """
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def human_like_click(self, locator: Locator):
        """
        Simulate a human-like click with Bézier-curve style movement,
        randomized delays, scrolling, and offset clicks.
        """
        if await locator.is_visible():
            await locator.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.2, 0.6))
            
            # Remove blocking overlays
            await self.remove_overlays()

            box = await locator.bounding_box()
            if not box:
                await locator.click(delay=random.randint(100, 250))
                return

            # Target point within the button (randomized)
            target_x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
            target_y = box['y'] + box['height'] * random.uniform(0.2, 0.8)

            # Move mouse in 'human' way (multiple small steps)
            # This is a simplified version of Bézier pathing
            await self.page.mouse.move(target_x, target_y, steps=random.randint(5, 12))
            await asyncio.sleep(random.uniform(0.1, 0.3))

            # Action synchronizer
            if self.action_lock:
                async with self.action_lock:
                    await self.page.mouse.click(target_x, target_y, delay=random.randint(80, 200))
            else:
                await self.page.mouse.click(target_x, target_y, delay=random.randint(80, 200))

    async def remove_overlays(self):
        """
        Removes transparent or semi-transparent divs that often layer 
        over buttons to trigger pop-unders.
        """
        await self.page.evaluate("""() => {
            const overlays = Array.from(document.querySelectorAll('div, ins, iframe')).filter(el => {
                const style = window.getComputedStyle(el);
                return (style.position === 'absolute' || style.position === 'fixed') && 
                       (style.zIndex > 100 || style.width === '100vw' || style.height === '100vh') &&
                       (parseFloat(style.opacity) < 0.1 || style.backgroundColor === 'transparent');
            });
            overlays.forEach(el => el.remove());
        }""")

    async def human_type(self, selector: Union[str, Locator], text: str, delay_min=50, delay_max=150):
        """
        Type text into a field with human-like delays between keystrokes.
        
        Args:
            selector: CSS selector or Playwright Locator
            text: Text to type
            delay_min: Minimum delay in ms
            delay_max: Maximum delay in ms
        """
        locator = self.page.locator(selector) if isinstance(selector, str) else selector
        
        await self.human_like_click(locator)
        
        # Clear existing text if any (optional, context dependent)
        await locator.fill("") 
        
        for char in text:
            await locator.press(char) # press sends keydown/keyup events
            await asyncio.sleep(random.randint(delay_min, delay_max) / 1000)

    async def idle_mouse(self, duration: float = 2.0):
        """
        Move mouse randomly to simulate user reading/thinking.
        
        Args:
            duration: Approximate duration in seconds
        """
        start = time.time()
        while time.time() - start < duration:
            # Get current viewport size
            vp = self.page.viewport_size
            if not vp: return
            
            w, h = vp['width'], vp['height']
            
            # Random destination
            x = random.randint(0, w)
            y = random.randint(0, h)
            
            # Move in short burst
            await self.page.mouse.move(x, y, steps=random.randint(5, 20))
            await asyncio.sleep(random.uniform(0.1, 0.5))

    async def simulate_reading(self, duration: float = 2.0):
        """
        Simulate a user reading content with natural scrolling behavior.
        
        Combines idle mouse movement with randomized scrolling to mimic
        real user interaction patterns while consuming content.
        
        Args:
            duration: Approximate duration in seconds to simulate reading
        """
        start = time.time()
        while time.time() - start < duration:
            # Small random scrolls (mostly down, sometimes up)
            direction = random.choice([1, 1, 1, -1])  # 75% down, 25% up
            delta = random.randint(30, 100) * direction
            await self.page.mouse.wheel(0, delta)
            
            # Natural pause between scrolls
            await asyncio.sleep(random.uniform(0.4, 1.2))
            
            # Occasional small mouse movement
            if random.random() < 0.3:
                vp = self.page.viewport_size
                if vp:
                    x = random.randint(int(vp['width'] * 0.2), int(vp['width'] * 0.8))
                    y = random.randint(int(vp['height'] * 0.3), int(vp['height'] * 0.7))
                    await self.page.mouse.move(x, y, steps=random.randint(3, 8))

    async def random_focus_blur(self):
        """
        Simulate tab switching/focus events to appear more human.
        
        Dispatches blur/focus events with realistic timing to mimic
        a user switching between tabs or windows.
        """
        await self.page.evaluate("""() => {
            // Dispatch blur event (user switched away)
            document.dispatchEvent(new Event('blur'));
            window.dispatchEvent(new FocusEvent('blur'));
            
            // Schedule focus event after random delay (user came back)
            const delay = Math.random() * 2000 + 500;  // 0.5-2.5 seconds
            setTimeout(() => {
                document.dispatchEvent(new Event('focus'));
                window.dispatchEvent(new FocusEvent('focus'));
            }, delay);
        }""")

    async def handle_cloudflare(self, max_wait_seconds: int = 60) -> bool:
        """
        Detects and waits for Cloudflare challenges including:
        - 'Just a moment' interstitial
        - Turnstile CAPTCHA challenges  
        - Waiting room queues
        - DDoS protection pages
        
        Args:
            max_wait_seconds: Maximum time to wait for challenge resolution
            
        Returns:
            True if challenge resolved, False if stuck/timed out
        """
        cloudflare_indicators = [
            "just a moment",
            "cloudflare",
            "checking your browser",
            "please wait",
            "ddos protection",
            "security check"
        ]
        
        cloudflare_selectors = [
            "#cf-challenge-running",
            ".cf-turnstile", 
            "[id*='cf-turnstile']",
            "#challenge-running",
            ".challenge-body",
            "#trk_jschal_js"
        ]
        
        start_time = time.time()
        checks = 0
        
        while (time.time() - start_time) < max_wait_seconds:
            checks += 1
            
            try:
                # Check for page crash/unresponsiveness
                if not await self.detect_page_crash():
                    logger.warning(f"[{self.faucet_name}] Page unresponsive during CF check. Refreshing...")
                    await self.page.reload()
                    await asyncio.sleep(5)
                    continue

                # Check page title for Cloudflare indicators
                title = (await self.page.title()).lower()
                title_detected = any(indicator in title for indicator in cloudflare_indicators)
                
                # Check page content for challenge elements
                element_detected = False
                for selector in cloudflare_selectors:
                    try:
                        locator = self.page.locator(selector)
                        if await locator.is_visible(timeout=500):
                            element_detected = True
                            
                            # INTERACTION: Try to click Turnstile checkbox if visible
                            if "turnstile" in selector:
                                try:
                                    # Find the checkbox iframe or element
                                    # Turnstile usually has a checkbox in an iframe
                                    if await locator.count() > 0:
                                        # Random delay and movement before interaction
                                        await self.idle_mouse(random.uniform(0.5, 1.5))
                                        # Use human_like_click on the locator
                                        await self.human_like_click(locator)
                                        logger.info(f"[{self.faucet_name}] 🖱️ Clicked Turnstile checkbox")
                                except Exception as click_err:
                                    logger.debug(f"Failed to click Turnstile: {click_err}")
                                    
                            break
                    except Exception:
                        continue
                
                if title_detected or element_detected:
                    if checks == 1:
                        logger.info(f"[{self.faucet_name}] ⏳ Cloudflare/Turnstile challenge detected, waiting...")
                    
                    # Simulate human-like behavior while waiting
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                    
                    # Occasionally move mouse or scroll to appear active
                    if checks % 3 == 0:
                        try:
                            if random.random() < 0.5:
                                await self.idle_mouse(0.8)
                            else:
                                await self.simulate_reading(1.0)
                        except Exception:
                            pass
                else:
                    # Challenge appears resolved
                    if checks > 1:
                        elapsed = time.time() - start_time
                        logger.info(f"[{self.faucet_name}] ✅ Cloudflare challenge resolved in {elapsed:.1f}s")
                    return True
                    
            except Exception as e:
                # Page might have crashed or navigated
                logger.warning(f"[{self.faucet_name}] Cloudflare check error (recoverable): {e}")
                await asyncio.sleep(2)
                
        logger.error(f"[{self.faucet_name}] ❌ Cloudflare challenge timed out after {max_wait_seconds}s")
        return False

    async def detect_page_crash(self) -> bool:
        """
        Detect if the page has crashed or become unresponsive.
        
        Returns:
            True if page appears healthy, False if crashed/unresponsive
        """
        try:
            # Try a simple evaluation to check page responsiveness
            await asyncio.wait_for(
                self.page.evaluate("() => document.readyState"),
                timeout=5.0
            )
            return True
        except asyncio.TimeoutError:
            logger.error(f"[{self.faucet_name}] Page appears unresponsive (timeout)")
            return False
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Page crash detected: {e}")
            return False


    async def close_popups(self):
        """
        Generic handler for common crypto-site popups, cookie consents, 
        and notification requests that block view or interaction.
        """
        selectors = [
            ".cc-btn.cc-dismiss",         # Cookie Consent
            ".pushpad_deny_button",       # Notification Permission
            ".close-reveal-modal",        # Reveal Modals
            "div[title='Close']",         # Generic Title-based close
            "#multitab_comm_close",       # Common in Freebitco.in
            ".modal-header .close",       # Bootstrap modals
            "button:has-text('Accept All')", 
            "button:has-text('Got it!')",
            ".fc-cta-consent"             # Google Consent
        ]
        
        if not self.page:
            return
        
        for sel in selectors:
            try:
                el = self.page.locator(sel)
                if await el.count() > 0 and await el.first.is_visible():
                    logger.debug(f"[{self.faucet_name}] Closing popup: {sel}")
                    await el.first.click(timeout=1000)
                    await asyncio.sleep(0.5)
            except asyncio.TimeoutError:
                continue  # Expected for popups that don't exist
            except Exception as e:
                logger.debug(f"[{self.faucet_name}] Popup close failed for {sel}: {e}")
                continue
    
    async def login(self) -> bool:
        """
        Perform the login process for the faucet.

        Returns:
            True if login was successful, False otherwise.
        """
        raise NotImplementedError

    async def claim(self) -> Union[bool, ClaimResult]:
        """
        Execute the claim process.

        Returns:
            True/False or ClaimResult object.
        """
        raise NotImplementedError
        
    async def get_timer(self, selector: str) -> float:
        """
        Extract timer value from a selector and convert to minutes.
        """
        try:
            el = self.page.locator(selector)
            if await el.count() > 0 and await el.first.is_visible():
                text = await el.first.text_content()
                return DataExtractor.parse_timer_to_minutes(text)
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Timer extraction failed: {e}")
        return 0.0

    async def get_balance(self, selector: str) -> str:
        """
        Extract balance from a selector.
        """
        try:
            el = self.page.locator(selector)
            if await el.count() > 0 and await el.first.is_visible():
                text = await el.first.text_content()
                return DataExtractor.extract_balance(text)
        except Exception as e:
            logger.debug(f"[{self.faucet_name}] Balance extraction failed: {e}")
        return "0"
        
    async def is_logged_in(self) -> bool:
        """
        Check if the session is still active. 
        Subclasses should override this with specific checks.
        """
        return False

    async def check_failure_states(self) -> Optional[str]:
        """
        Check for common failure states like IP ban, proxy detection, or maintenance.
        Returns a string describing the state if failure detected, else None.
        """
        content = (await self.page.content()).lower()
        url = self.page.url.lower()
        
        # Proxy/VPN Detection Patterns
        proxy_patterns = [
            "proxy detected",
            "vpn detected",
            "suspicious activity",
            "datacenter ip",
            "hosting provider",
            "please disable your proxy",
            "please disable your vpn",
            "access denied",
            "forbidden",
            "your ip has been flagged",
            "unusual traffic"
        ]
        
        for pattern in proxy_patterns:
            if pattern in content:
                logger.warning(f"[{self.faucet_name}] Proxy detection pattern found: '{pattern}'")
                return "Proxy Detected"
        
        # Account Ban/Suspension Patterns
        ban_patterns = [
            "account banned",
            "account suspended",
            "account disabled",
            "account locked",
            "permanently banned",
            "violation of terms"
        ]
        
        for pattern in ban_patterns:
            if pattern in content:
                logger.error(f"[{self.faucet_name}] Account ban pattern found: '{pattern}'")
                return "Account Banned"
        
        # Site Maintenance/Cloudflare Patterns
        maintenance_patterns = [
            "maintenance",
            "under maintenance",
            "temporarily unavailable",
            "checking your browser",
            "cloudflare",
            "ddos protection",
            "security check"
        ]
        
        for pattern in maintenance_patterns:
            if pattern in content:
                logger.info(f"[{self.faucet_name}] Maintenance/security pattern found: '{pattern}'")
                return "Site Maintenance / Blocked"
        
        # Check for error pages in URL
        if any(err in url for err in ["error", "403", "404", "500", "banned"]):
            logger.warning(f"[{self.faucet_name}] Error page detected in URL: {url}")
            return "Error Page"
        
        return None

    async def login_wrapper(self) -> bool:
        """
        Ensure we are logged in, with failure state checking.
        """
        failure = await self.check_failure_states()
        if failure:
            logger.error(f"[{self.faucet_name}] Failure state detected: {failure}")
            return False
            
        if await self.is_logged_in():
            return True
            
        return await self.login()

    async def view_ptc_ads(self):
        """
        Generic PTC Ad viewing logic.
        1. Finds ad links (selector provided by subclass)
        2. Clicks and handles new tab
        3. Waits for timer (time provided by subclass or element)
        4. Solves captcha if needed
        """
        logger.warning(f"[{self.faucet_name}] PTC logic not fully implemented in subclass.")
        await asyncio.sleep(1)

    def get_earning_tasks(self):
        """
        Returns a list of async methods (tasks) to execute for earnings.
        """
        tasks = []
        # Claim is usually the primary task
        tasks.append({"func": self.claim, "name": "Faucet Claim"})
        
        # Add PTC if available
        # Note: We now define view_ptc_ads in base, so we check if subclass overrides or configured
        if hasattr(self, "ptc_ads_selector") or self.faucet_name in ["CoinPayU", "AdBTC"]:
             tasks.append({"func": self.view_ptc_ads, "name": "PTC Ads"})
        
        return tasks
             
    async def withdraw(self) -> ClaimResult:
        """
        Generic withdrawal logic. Subclasses should override this with site-specific
        navigation and button clicking.
        """
        logger.warning(f"[{self.faucet_name}] Withdrawal not implemented for this faucet.")
        return ClaimResult(success=False, status="Not Implemented", next_claim_minutes=1440)

    def get_jobs(self):
        """
        Returns a list of Job objects for the scheduler.
        """
        from core.orchestrator import Job
        import time
        
        jobs = []
        f_type = self.faucet_name.lower().replace(" ", "_")
        
        # 1. Primary claim job - highest priority
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=f_type,
            job_type="claim_wrapper"
        ))
        
        # 2. Withdrawal job - scheduled once per day
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600, 
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=f_type,
            job_type="withdraw_wrapper"
        ))
        
        # 3. PTC job if available
        if hasattr(self, "view_ptc_ads"):
            jobs.append(Job(
                priority=3,
                next_run=time.time() + 300,
                name=f"{self.faucet_name} PTC",
                profile=None,
                faucet_type=f_type,
                job_type="ptc_wrapper"
            ))
        
        return jobs

    async def withdraw_wrapper(self, page: Page) -> ClaimResult:
        """Wrapper for withdrawal with threshold checking and analytics tracking."""
        from core.withdrawal_analytics import get_analytics
        
        self.page = page
        
        # 1. Ensure logged in
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login/Access Failed", next_claim_minutes=30)
        
        # 2. Check balance against threshold
        current_balance = await self.get_balance(getattr(self, 'balance_selector', '.balance'))
        balance_before = 0.0
        try:
            balance_before = float(current_balance.replace(',', ''))
            threshold = getattr(self.settings, f"{self.faucet_name.lower()}_min_withdraw", 1000)
            if balance_before < threshold:
                logger.info(f"[{self.faucet_name}] Balance {balance_before} below threshold {threshold}. Skipping.")
                return ClaimResult(success=True, status="Below Threshold", next_claim_minutes=1440)
        except (ValueError, AttributeError) as e:
            logger.debug(f"[{self.faucet_name}] Balance parsing failed: {e}. Proceeding with withdrawal.")
            pass  # Continue if parsing fails
        
        # 3. Execute withdrawal
        result = await self.withdraw()
        
        # 4. Track withdrawal in analytics (if successful)
        if result.success:
            try:
                # Get balance after withdrawal
                balance_after_str = result.balance if result.balance != "0" else await self.get_balance(getattr(self, 'balance_selector', '.balance'))
                balance_after = 0.0
                try:
                    balance_after = float(balance_after_str.replace(',', ''))
                except (ValueError, AttributeError):
                    pass
                
                # Calculate withdrawn amount
                amount_withdrawn = float(result.amount.replace(',', '')) if result.amount != "0" else (balance_before - balance_after)
                
                # Determine cryptocurrency from faucet name or settings
                crypto = self._get_cryptocurrency_for_faucet()
                
                # Record withdrawal (fees are typically platform-side for faucets)
                analytics = get_analytics()
                analytics.record_withdrawal(
                    faucet=self.faucet_name,
                    cryptocurrency=crypto,
                    amount=amount_withdrawn,
                    network_fee=0.0,  # Most faucets don't charge network fees
                    platform_fee=0.0,  # Can be updated by subclass if known
                    withdrawal_method="faucetpay" if self.settings.use_faucetpay else "direct",
                    status="success",
                    balance_before=balance_before,
                    balance_after=balance_after,
                    notes=result.status
                )
            except Exception as e:
                logger.warning(f"[{self.faucet_name}] Failed to record withdrawal analytics: {e}")
        
        return result
    
    def _get_cryptocurrency_for_faucet(self) -> str:
        """
        Determine the cryptocurrency for this faucet.
        Subclasses can override this method.
        """
        # Try to infer from faucet name
        name_lower = self.faucet_name.lower()
        if "btc" in name_lower or "bitcoin" in name_lower:
            return "BTC"
        elif "ltc" in name_lower or "lite" in name_lower:
            return "LTC"
        elif "doge" in name_lower:
            return "DOGE"
        elif "trx" in name_lower or "tron" in name_lower:
            return "TRX"
        elif "eth" in name_lower:
            return "ETH"
        elif "bnb" in name_lower or "bin" in name_lower:
            return "BNB"
        elif "sol" in name_lower:
            return "SOL"
        elif "ton" in name_lower:
            return "TON"
        elif "matic" in name_lower or "polygon" in name_lower:
            return "MATIC"
        elif "dash" in name_lower:
            return "DASH"
        elif "bch" in name_lower:
            return "BCH"
        elif "usdt" in name_lower or "usd" in name_lower:
            return "USDT"
        else:
            return "UNKNOWN"
             
    async def claim_wrapper(self, page: Page) -> ClaimResult:
        self.page = page
        # Ensure logged in with new wrapper
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login/Access Failed", next_claim_minutes=30)
        return await self.claim()

    async def ptc_wrapper(self, page: Page) -> ClaimResult:
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(success=False, status="Login/Access Failed", next_claim_minutes=30)
        
        await self.view_ptc_ads()
        return ClaimResult(success=True, status="PTC Done", next_claim_minutes=self.settings.exploration_frequency_minutes)

    async def _record_analytics(self, result: ClaimResult):
        """Helper to record analytics for a result."""
        try:
            tracker = get_tracker()
            amount = float(result.amount) if result.amount else 0.0
            tracker.record_claim(
                faucet=self.faucet_name,
                success=result.success,
                amount=amount,
                currency=getattr(self, 'coin', 'unknown'),
                balance_after=float(result.balance) if result.balance else 0.0
            )
        except Exception as analytics_err:
            logger.warning(f"Analytics tracking failed: {analytics_err}")

    async def run(self) -> ClaimResult:
        """
        Main execution flow. 
        Returns the ClaimResult from the primary 'claim' task (or a default failure one)
        to determine the next schedule time.
        """
        logger.info(f"[{self.faucet_name}] Starting run...")
        
        # Default result in case everything fails
        final_result = ClaimResult(success=False, status="Run Failed", next_claim_minutes=5)
        
        try:
            if not await self.login():
                logger.error(f"[{self.faucet_name}] Login Failed")
                res = ClaimResult(success=False, status="Login Failed", next_claim_minutes=30)
                await self._record_analytics(res)
                return res
            
            await self.close_popups()
            
            # Note: WebRTC/Canvas stealth is handled at context creation in browser/instance.py
            await self.random_delay()
            
            # Execute all defined tasks
            tasks = self.get_earning_tasks()
            
            for task_info in tasks:
                func = task_info["func"]
                name = task_info["name"]
                
                try:
                    logger.info(f"[{self.faucet_name}] Executing: {name}")
                    res = await func()
                    
                    # If this was the main claim, capture the result for scheduling
                    if isinstance(res, ClaimResult):
                        final_result = res
                        logger.info(f"[{self.faucet_name}] {name} Result: {res.status} (Wait: {res.next_claim_minutes}m)")
                        await self._record_analytics(res)
                            
                    elif res:
                        logger.info(f"[{self.faucet_name}] {name} Successful")
                    else:
                        logger.warning(f"[{self.faucet_name}] {name} Completed with no result/fail")
                        
                    await self.random_delay()
                    
                except Exception as e:
                     error_msg = f"Task '{name}' Error: {e}"
                     logger.error(f"[{self.faucet_name}] {error_msg}")
                     
                     # If the primary claim fails with an exception, update final_result
                     if name == "Faucet Claim":
                         final_result = ClaimResult(success=False, status=error_msg, next_claim_minutes=15)
                         await self._record_analytics(final_result)
                     
                     # We continue to the next task even if this one failed!
            
            return final_result

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Runtime Fatal Error: {e}")
            final_result = ClaimResult(success=False, status=f"Fatal: {e}", next_claim_minutes=10)
            await self._record_analytics(final_result)
            return final_result
        finally:
            await self.solver.close()

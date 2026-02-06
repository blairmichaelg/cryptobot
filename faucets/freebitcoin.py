from .base import FaucetBot, ClaimResult
from core.extractor import DataExtractor
import logging
import asyncio
import time

logger = logging.getLogger(__name__)

class FreeBitcoinBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "FreeBitcoin"
        self.base_url = "https://freebitco.in"

    async def is_logged_in(self) -> bool:
        balance_selectors = [
            "#balance_small",
            "#balance_small span",
            ".balanceli",
            "#balance",
            ".balance",
            "[data-balance]",
            ".user-balance",
            "span.balance",
            "#balance_small",
            ".balance-amount",
            "a[href*='logout']",
            "a:has-text('Logout')",
            "a:has-text('Sign out')",
            "a[href*='logout.php']",
            "#logout",
            ".logout",
            ".account-balance",
            "[data-testid='logout']",
        ]
        for selector in balance_selectors:
            try:
                if await self.page.locator(selector).is_visible(timeout=3000):
                    return True
            except Exception:
                continue
        return False

    async def _find_selector(self, selectors: list, element_name: str = "element", timeout: int = 5000, include_frames: bool = True):
        """
        Try multiple selectors and return the first one that exists and is visible.
        
        Args:
            selectors: List of CSS selectors to try
            element_name: Name of element for logging
            timeout: Total timeout in milliseconds
            
        Returns:
            Locator if found, None otherwise
        """
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                # is_visible() already checks existence internally
                if await locator.is_visible(timeout=timeout):
                    logger.debug(f"[FreeBitcoin] Found {element_name} with selector: {selector}")
                    return locator
            except Exception:
                continue

        if include_frames:
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                for selector in selectors:
                    try:
                        locator = frame.locator(selector).first
                        if await locator.is_visible(timeout=timeout):
                            logger.debug(f"[FreeBitcoin] Found {element_name} in frame with selector: {selector}")
                            return locator
                    except Exception:
                        continue
        
        logger.warning(f"[FreeBitcoin] Could not find {element_name}. Tried selectors: {selectors}")
        return None

    async def _find_selector_any_frame(self, selectors: list, element_name: str = "element", timeout: int = 5000):
        """
        Try multiple selectors across the main page and iframes.

        Returns:
            Locator if found, None otherwise
        """
        locator = await self._find_selector(selectors, element_name=element_name, timeout=timeout)
        if locator:
            return locator

        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            for selector in selectors:
                try:
                    candidate = frame.locator(selector).first
                    if await candidate.is_visible(timeout=timeout):
                        logger.debug(f"[FreeBitcoin] Found {element_name} in iframe with selector: {selector}")
                        return candidate
                except Exception:
                    continue

        logger.warning(f"[FreeBitcoin] Could not find {element_name} in any frame. Tried selectors: {selectors}")
        return None

    async def _is_signup_form_field(self, locator) -> bool:
        """
        Detect whether a locator belongs to a signup/registration form.

        Returns:
            bool: True if the field appears to be part of a signup form.
        """
        if not locator:
            return False
        try:
            info = await locator.evaluate(
                """
                (el) => {
                    const form = el.closest('form');
                    return {
                        id: el.id || '',
                        name: el.name || '',
                        formId: form ? (form.id || '') : '',
                        formName: form ? (form.name || '') : '',
                        formAction: form ? (form.action || '') : ''
                    };
                }
                """
            )
            haystack = " ".join(
                [
                    str(info.get("id", "")),
                    str(info.get("name", "")),
                    str(info.get("formId", "")),
                    str(info.get("formName", "")),
                    str(info.get("formAction", "")),
                ]
            ).lower()
            return any(token in haystack for token in ["signup", "register", "registration"])
        except Exception:
            return False

    async def _wait_for_captcha_token(self, timeout: int = 15000) -> bool:
        """Wait for a captcha token to be injected into the page."""
        try:
            await self.page.wait_for_function(
                """
                () => {
                    const selectors = [
                        'textarea[name="g-recaptcha-response"]',
                        'textarea[name="h-captcha-response"]',
                        'input[name="cf-turnstile-response"]',
                        'textarea[name="cf-turnstile-response"]'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.value && el.value.trim().length > 0) {
                            return true;
                        }
                    }
                    return false;
                }
                """,
                timeout=timeout
            )
            return True
        except Exception:
            return False



    async def _has_session_cookie(self) -> bool:
        try:
            cookies = await self.page.context.cookies(self.base_url)
        except Exception:
            return False
        names = {cookie.get("name") for cookie in cookies}
        return "fbtc_session" in names or "fbtc_userid" in names



    async def _log_login_diagnostics(self, context: str) -> None:
        """Log login page diagnostics to identify captcha/input elements."""
        try:
            inputs = await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('input')).map(el => ({
                    type: el.type || null,
                    name: el.name || null,
                    id: el.id || null,
                    placeholder: el.placeholder || null,
                    className: el.className || null
                }))
                """
            )
        except Exception:
            inputs = None

        try:
            textareas = await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('textarea')).map(el => ({
                    name: el.name || null,
                    id: el.id || null,
                    className: el.className || null
                }))
                """
            )
        except Exception:
            textareas = None

        try:
            iframes = await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('iframe')).map(el => ({
                    src: el.src || null,
                    name: el.name || null,
                    id: el.id || null,
                    title: el.title || null,
                    className: el.className || null
                }))
                """
            )
        except Exception:
            iframes = None

        try:
            captcha_nodes = await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('*')).filter(el => {
                    const id = (el.id || '').toLowerCase();
                    const cls = (el.className || '').toString().toLowerCase();
                    return id.includes('captcha') || cls.includes('captcha');
                }).slice(0, 50).map(el => ({
                    tag: el.tagName,
                    id: el.id || null,
                    className: el.className || null
                }))
                """
            )
        except Exception:
            captcha_nodes = None

        try:
            form_summaries = await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('form')).map(form => ({
                    id: form.id || null,
                    name: form.name || null,
                    action: form.action || null,
                    method: form.method || null,
                    inputs: Array.from(form.querySelectorAll('input')).map(el => ({
                        type: el.type || null,
                        name: el.name || null,
                        id: el.id || null,
                        placeholder: el.placeholder || null
                    }))
                }))
                """
            )
        except Exception:
            form_summaries = None

        try:
            int_captcha_html = await self.page.evaluate(
                """
                () => {
                    const el = document.querySelector('#int_page_captchas');
                    if (!el) return null;
                    const html = el.innerHTML || '';
                    return html.length > 2000 ? html.slice(0, 2000) + '...<truncated>' : html;
                }
                """
            )
        except Exception:
            int_captcha_html = None

        try:
            login_form_html = await self.page.evaluate(
                """
                () => {
                    const el = document.querySelector('#login_form');
                    if (!el) return null;
                    const html = el.innerHTML || '';
                    return html.length > 2000 ? html.slice(0, 2000) + '...<truncated>' : html;
                }
                """
            )
        except Exception:
            login_form_html = None

        try:
            captcha_state = await self.page.evaluate(
                """
                () => ({
                    captcha_type: typeof captcha_type !== 'undefined' ? captcha_type : null,
                    has_turnstile: typeof turnstile !== 'undefined',
                    has_hcaptcha: typeof hcaptcha !== 'undefined',
                    has_grecaptcha: typeof grecaptcha !== 'undefined',
                    int_page_captchas_children: (() => {
                        const el = document.querySelector('#int_page_captchas');
                        return el ? el.children.length : null;
                    })(),
                    login_button_exists: !!document.querySelector('#login_button'),
                    login_button_onclick: (() => {
                        const btn = document.querySelector('#login_button');
                        return btn ? btn.getAttribute('onclick') : null;
                    })(),
                    has_do_login: typeof do_login !== 'undefined',
                    has_login_function: typeof login !== 'undefined',
                    login_button_form: (() => {
                        const btn = document.querySelector('#login_button');
                        return btn && btn.form ? btn.form.id || btn.form.name || null : null;
                    })()
                })
                """
            )
        except Exception:
            captcha_state = None

        try:
            login_nodes = await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('*')).filter(el => {
                    const id = (el.id || '').toLowerCase();
                    const cls = (el.className || '').toString().toLowerCase();
                    return id.includes('login') || cls.includes('login');
                }).slice(0, 50).map(el => ({
                    tag: el.tagName,
                    id: el.id || null,
                    className: el.className || null
                }))
                """
            )
        except Exception:
            login_nodes = None

        try:
            login_input_forms = await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('input[id^="login_form"]')).map(el => ({
                    id: el.id || null,
                    name: el.name || null,
                    form: el.form ? (el.form.id || el.form.name || null) : null
                }))
                """
            )
        except Exception:
            login_input_forms = None

        try:
            script_sources = await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('script[src]')).map(el => el.src).slice(0, 50)
                """
            )
        except Exception:
            script_sources = None

        try:
            js_state = await self.page.evaluate(
                """
                () => ({
                    has_jquery: typeof window.jQuery !== 'undefined',
                    has_$: typeof window.$ !== 'undefined',
                    has_login_form_submit: (() => {
                        const el = document.querySelector('#login_form');
                        return !!(el && el.tagName === 'FORM');
                    })()
                })
                """
            )
        except Exception:
            js_state = None

        logger.info("[FreeBitcoin] Login diagnostics (%s): inputs=%s", context, inputs)
        logger.info("[FreeBitcoin] Login diagnostics (%s): textareas=%s", context, textareas)
        logger.info("[FreeBitcoin] Login diagnostics (%s): iframes=%s", context, iframes)
        logger.info("[FreeBitcoin] Login diagnostics (%s): captcha_nodes=%s", context, captcha_nodes)
        logger.info("[FreeBitcoin] Login diagnostics (%s): forms=%s", context, form_summaries)
        logger.info("[FreeBitcoin] Login diagnostics (%s): int_page_captchas_html=%s", context, int_captcha_html)
        logger.info("[FreeBitcoin] Login diagnostics (%s): login_form_html=%s", context, login_form_html)
        logger.info("[FreeBitcoin] Login diagnostics (%s): captcha_state=%s", context, captcha_state)
        logger.info("[FreeBitcoin] Login diagnostics (%s): login_nodes=%s", context, login_nodes)
        logger.info("[FreeBitcoin] Login diagnostics (%s): login_input_forms=%s", context, login_input_forms)
        logger.info("[FreeBitcoin] Login diagnostics (%s): script_sources=%s", context, script_sources)
        logger.info("[FreeBitcoin] Login diagnostics (%s): js_state=%s", context, js_state)

    async def login(self) -> bool:
        """
        Simplified login flow for FreeBitcoin with retry logic and enhanced error logging.
        
        Changes from original:
        - Removed complex fallback methods (_submit_login_via_request/ajax/fetch/form)
        - Reduced selectors from 16+ to 4 most reliable
        - Added retry logic with exponential backoff
        - Enhanced error logging with screenshots and diagnostics
        - Single, clean browser-based login flow
        """
        # Check for override (Multi-Account Loop)
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("freebitcoin")
            
        if not creds: 
            logger.error("[FreeBitcoin] Credentials missing - set FREEBITCOIN_USERNAME and FREEBITCOIN_PASSWORD")
            return False

        # Extract credentials
        login_id = creds.get("username") or creds.get("email")
        if not login_id:
            logger.error("[FreeBitcoin] Credentials missing username/email")
            return False
        login_id = self.strip_email_alias(login_id)
        if not login_id:
            logger.error("[FreeBitcoin] Invalid username/email after processing")
            return False
        password = creds.get("password")
        if not password:
            logger.error("[FreeBitcoin] Credentials missing password")
            return False

        # Updated selectors based on diagnostic script findings (Feb 2026)
        # The login form uses specific IDs that are now confirmed
        email_selectors = [
            "#login_form_btc_address",  # Confirmed working (hidden until trigger clicked)
            "input[name='btc_address']",  # FreeBitcoin specific field name
            "input[type='text'][name='btc_address']",
            "#email"
        ]
        
        password_selectors = [
            "#login_form_password",  # Confirmed working (hidden until trigger clicked)
            "input[name='password']",
            "input[type='password']",
            "#password"
        ]
        
        submit_selectors = [
            "#login_button",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Login')"
        ]

        # Retry logic with exponential backoff
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    backoff_seconds = 5 * attempt  # 5s, 10s, 15s
                    logger.info(f"[FreeBitcoin] Login attempt {attempt + 1}/{max_attempts} after {backoff_seconds}s backoff")
                    await asyncio.sleep(backoff_seconds)
                else:
                    logger.info(f"[FreeBitcoin] Login attempt {attempt + 1}/{max_attempts}")

                # Navigate to base URL (not login URL - site redirects to signup)
                logger.info(f"[FreeBitcoin] Navigating to: {self.base_url}")
                
                # Use safe_navigate from base class for proxy error handling
                if not await self.safe_navigate(self.base_url, wait_until="domcontentloaded"):
                    logger.warning(f"[FreeBitcoin] Navigation failed on attempt {attempt + 1}")
                    continue
                
                await self.random_delay(1, 2)
                
                # Handle Cloudflare and popups
                try:
                    await self.handle_cloudflare(max_wait_seconds=60)
                except Exception as cf_err:
                    logger.debug(f"[FreeBitcoin] Cloudflare handling: {cf_err}")
                
                await self.close_popups()
                await asyncio.sleep(1)
                
                # Log current state
                current_url = self.page.url
                page_title = await self.page.title()
                logger.info(f"[FreeBitcoin] Current page - URL: {current_url}, Title: {page_title}")
                
                # Check if already logged in
                if await self.is_logged_in():
                    logger.info("✅ [FreeBitcoin] Session already active")
                    return True
                
                # CRITICAL: Click login trigger to show hidden login form
                # The login form is hidden by default - need to click "LOGIN" link/button first
                login_trigger_selectors = [
                    "a:has-text('LOGIN')",
                    "a:has-text('Log In')",
                    "button:has-text('LOGIN')",
                    "a[href*='login']",
                    "a[href*='op=login']",
                    ".login-link",
                    "#login_link"
                ]
                
                login_trigger_clicked = False
                for selector in login_trigger_selectors:
                    try:
                        locator = self.page.locator(selector).first
                        if await locator.is_visible(timeout=3000):
                            logger.info(f"[FreeBitcoin] Clicking login trigger: {selector}")
                            await self.human_like_click(locator)
                            await asyncio.sleep(3)  # Wait longer for form to appear
                            login_trigger_clicked = True
                            break
                    except Exception:
                        continue
                
                if not login_trigger_clicked:
                    logger.warning(f"[FreeBitcoin] No login trigger found - form may already be visible or URL changed")
                
                # Wait for login form to be fully visible and interactive
                # After clicking LOGIN, the form should appear with these IDs
                logger.debug("[FreeBitcoin] Waiting for login form to appear...")
                try:
                    await self.page.wait_for_selector('#login_form_btc_address', state='visible', timeout=10000)
                    await self.page.wait_for_selector('#login_form_password', state='visible', timeout=5000)
                    logger.info("[FreeBitcoin] Login form is now visible")
                except Exception as wait_err:
                    logger.warning(f"[FreeBitcoin] Login form wait timeout: {wait_err}")
                    # Continue anyway - fields might still be findable
                
                # Solve landing page CAPTCHA if present
                logger.debug("[FreeBitcoin] Checking for landing page CAPTCHA...")
                try:
                    captcha_present = await self.page.evaluate(
                        """
                        () => {
                            const captchaSelectors = [
                                "iframe[src*='turnstile']",
                                ".cf-turnstile",
                                "iframe[src*='hcaptcha']",
                                "iframe[src*='recaptcha']"
                            ];
                            for (const sel of captchaSelectors) {
                                if (document.querySelector(sel)) return true;
                            }
                            return false;
                        }
                        """
                    )
                    if captcha_present:
                        logger.info("[FreeBitcoin] Landing page CAPTCHA detected - solving...")
                        solved = await self.solver.solve_captcha(self.page)
                        if solved is False:
                            logger.error("[FreeBitcoin] Landing page CAPTCHA solve failed")
                            continue
                        logger.info("✅ [FreeBitcoin] Landing page CAPTCHA solved")
                        await asyncio.sleep(2)
                except Exception as captcha_err:
                    logger.debug(f"[FreeBitcoin] Landing CAPTCHA check: {captcha_err}")
                
                # Find email field
                email_field = None
                for selector in email_selectors:
                    try:
                        locator = self.page.locator(selector).first
                        if await locator.is_visible(timeout=5000):
                            logger.info(f"[FreeBitcoin] Using email selector: {selector}")
                            email_field = locator
                            break
                    except Exception:
                        continue
                
                if not email_field:
                    logger.warning(f"[FreeBitcoin] Email field not found on {current_url}")
                    # Log visible form fields
                    try:
                        visible_inputs = await self.page.evaluate(
                            """
                            () => Array.from(document.querySelectorAll('input:visible')).map(el => ({
                                type: el.type,
                                name: el.name,
                                id: el.id,
                                placeholder: el.placeholder
                            })).slice(0, 10)
                            """
                        )
                        logger.info(f"[FreeBitcoin] Visible inputs: {visible_inputs}")
                    except Exception:
                        pass
                    continue
                
                # Find password field
                password_field = None
                for selector in password_selectors:
                    try:
                        locator = self.page.locator(selector).first
                        if await locator.is_visible(timeout=5000):
                            logger.info(f"[FreeBitcoin] Using password selector: {selector}")
                            password_field = locator
                            break
                    except Exception:
                        continue
                
                if not password_field:
                    logger.warning(f"[FreeBitcoin] Password field not found on {current_url}")
                    continue
                
                # Fill credentials
                username_display = login_id[:10] + "***" if len(login_id) > 10 else login_id[:3] + "***"
                logger.info(f"[FreeBitcoin] Filling credentials for user: {username_display}")
                
                try:
                    await self.human_type(email_field, login_id)
                    await self.random_delay(0.5, 1.0)
                    await self.human_type(password_field, password)
                    await self.idle_mouse(0.5)
                except Exception as type_err:
                    logger.warning(f"[FreeBitcoin] Human typing failed: {type_err}, using direct fill")
                    await email_field.fill(login_id)
                    await self.random_delay(0.3, 0.5)
                    await password_field.fill(password)
                
                # Check for CAPTCHA on login form
                logger.debug("[FreeBitcoin] Checking for login form CAPTCHA...")
                try:
                    captcha_present = await self.page.evaluate(
                        """
                        () => {
                            const captchaSelectors = [
                                "iframe[src*='turnstile']",
                                ".cf-turnstile",
                                "iframe[src*='hcaptcha']",
                                "iframe[src*='recaptcha']"
                            ];
                            for (const sel of captchaSelectors) {
                                if (document.querySelector(sel)) return true;
                            }
                            return false;
                        }
                        """
                    )
                    if captcha_present:
                        logger.info("[FreeBitcoin] Login form CAPTCHA detected - solving...")
                        solved = await self.solver.solve_captcha(self.page)
                        if solved is False:
                            logger.error("[FreeBitcoin] Login form CAPTCHA solve failed")
                            continue
                        logger.info("✅ [FreeBitcoin] Login form CAPTCHA solved")
                        await asyncio.sleep(2)
                except Exception as captcha_err:
                    logger.debug(f"[FreeBitcoin] Login form CAPTCHA check: {captcha_err}")
                
                # Find and click submit button
                submit_btn = None
                for selector in submit_selectors:
                    try:
                        locator = self.page.locator(selector).first
                        if await locator.is_visible(timeout=5000):
                            logger.info(f"[FreeBitcoin] Using submit selector: {selector}")
                            submit_btn = locator
                            break
                    except Exception:
                        continue
                
                if submit_btn:
                    logger.debug("[FreeBitcoin] Clicking submit button...")
                    await self.human_like_click(submit_btn)
                else:
                    logger.warning("[FreeBitcoin] Submit button not found, trying Enter key...")
                    try:
                        await password_field.press("Enter")
                    except Exception:
                        logger.error("[FreeBitcoin] Enter key failed")
                        timestamp = int(time.time())
                        screenshot_path = f"logs/freebitcoin_login_failed_no_submit_{timestamp}.png"
                        try:
                            await self.page.screenshot(path=screenshot_path, full_page=True)
                            logger.info(f"[FreeBitcoin] Screenshot saved: {screenshot_path}")
                        except Exception:
                            pass
                        continue
                
                # Wait for navigation
                logger.debug("[FreeBitcoin] Waiting for login to complete...")
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                except asyncio.TimeoutError:
                    logger.warning("[FreeBitcoin] Login redirect timeout")
                
                await self.random_delay(2, 3)
                
                # Check if logged in
                if await self.is_logged_in():
                    logger.info("✅ [FreeBitcoin] Login successful!")
                    return True
                
                # Check for error messages
                error_text = ""
                try:
                    error_elem = await self.page.locator(".alert-danger, .error, .login-error").first
                    if await error_elem.is_visible(timeout=2000):
                        error_text = await error_elem.text_content()
                        logger.error(f"[FreeBitcoin] Login error message: {error_text}")
                except Exception:
                    pass
                
                # Take screenshot on failure
                timestamp = int(time.time())
                screenshot_path = f"logs/freebitcoin_login_failed_{timestamp}.png"
                try:
                    await self.page.screenshot(path=screenshot_path, full_page=True)
                    logger.info(f"[FreeBitcoin] Screenshot saved: {screenshot_path}")
                except Exception:
                    pass
                
                # Log diagnostics
                await self._log_login_diagnostics(f"login_failed_attempt_{attempt + 1}")
                
            except Exception as e:
                logger.error(f"[FreeBitcoin] Login attempt {attempt + 1} exception: {e}", exc_info=True)
                timestamp = int(time.time())
                screenshot_path = f"logs/freebitcoin_login_exception_{timestamp}.png"
                try:
                    await self.page.screenshot(path=screenshot_path)
                    logger.info(f"[FreeBitcoin] Exception screenshot saved: {screenshot_path}")
                except Exception:
                    pass
        
        # All attempts failed
        logger.error(f"[FreeBitcoin] Login failed after {max_attempts} attempts")
        return False

    async def claim(self) -> ClaimResult:
        """
        Execute the claim process for FreeBitcoin.
        
        Implements:
        - Retry logic for network failures
        - Human-like behavior patterns
        - Comprehensive error logging
        
        Returns:
            ClaimResult with success status and next claim time
        """
        logger.info("[DEBUG] FreeBitcoin claim() method started")
        
        max_retries = 3
        nav_timeout = getattr(self.settings, "timeout", 180000)
        for attempt in range(max_retries):
            try:
                logger.info(f"[DEBUG] Attempt {attempt + 1}/{max_retries}: Navigating to {self.base_url}/")
                response = await self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=nav_timeout)
                if response is not None:
                    try:
                        status = response.status
                        if status in (401, 403, 429):
                            from core.orchestrator import ErrorType
                            logger.error(f"[FreeBitcoin] Claim page returned HTTP {status}. URL: {response.url}")
                            return ClaimResult(
                                success=False,
                                status=f"HTTP {status}",
                                next_claim_minutes=30,
                                error_type=ErrorType.PROXY_ISSUE if status == 403 else ErrorType.RATE_LIMIT
                            )
                    except Exception:
                        pass
                await self.handle_cloudflare(max_wait_seconds=60)
                await self.close_popups()
                await self.random_delay(2, 4)

                # Extract Balance with fallback selectors
                # FreeBitcoin uses #balance_small (visible in nav bar) as the reliable
                # balance element. #balance exists but is often hidden/not visible.
                # .balanceli is the parent container. PR #96 confirmed #balance_small.
                logger.info("[DEBUG] Getting balance...")
                balance = await self.get_balance(
                    "#balance_small",
                    fallback_selectors=[
                        "#balance",
                        ".balanceli",
                        "li.balanceli span",
                        "span.balance",
                        ".user-balance",
                        "[data-balance]",
                        ".account-balance"
                    ]
                )
                logger.info(f"[DEBUG] Balance: {balance}")

                # Check if timer is running (already claimed) with fallback selectors
                # FreeBitcoin uses .countdown_time_remaining for the countdown display.
                # #time_remaining exists but may not always be visible.
                logger.info("[DEBUG] Checking timer...")
                wait_min = await self.get_timer(
                    ".countdown_time_remaining",
                    fallback_selectors=[
                        "#time_remaining",
                        "#countdown_timer",
                        "span#timer",
                        ".countdown",
                        "[data-next-claim]",
                        ".time-remaining"
                    ]
                )
                logger.info(f"[DEBUG] Timer: {wait_min} minutes")
                if wait_min > 0:
                    # Simulate reading page content while timer is active
                    await self.simulate_reading(2.0)
                    return ClaimResult(success=True, status="Timer Active", next_claim_minutes=wait_min, balance=balance)

                # Check for Roll Button Presence BEFORE Solving (Save $$)
                # Use multiple selector options for robustness
                roll_btn = self.page.locator(
                    "#free_play_form_button, input#free_play_form_button, input[name='free_play_form_button'], "
                    "button#free_play_form_button, button[id*='play'], .homepage_play_now_button, "
                    ".claim-btn, button:has-text('Roll'), button:has-text('ROLL'), "
                    "button:has-text('Play'), input[value*='ROLL'], input[value*='Roll']"
                ).first

                try:
                    await roll_btn.wait_for(state="visible", timeout=8000)
                    roll_visible = True
                except Exception:
                    roll_visible = False

                if roll_visible:
                    if hasattr(roll_btn, "is_enabled") and not await roll_btn.is_enabled():
                        logger.warning("[DEBUG] Roll button is visible but disabled")
                        return ClaimResult(
                            success=False,
                            status="Roll Disabled",
                            next_claim_minutes=15,
                            balance=balance
                        )
                    logger.info("[DEBUG] Roll button found. Initiating Captcha Solve...")

                    # Handle Cloudflare & Captcha
                    logger.debug("[DEBUG] Checking for CloudFlare protection...")
                    cf_result = await self.handle_cloudflare()
                    logger.debug(f"[DEBUG] CloudFlare check result: {cf_result}")

                    # Solve CAPTCHA with error handling
                    logger.debug("[DEBUG] Solving CAPTCHA for claim...")
                    try:
                        await self.solver.solve_captcha(self.page)
                        logger.debug("[DEBUG] CAPTCHA solved successfully")
                        
                        # Manually enable roll button (CAPTCHA callback may not enable it)
                        try:
                            await self.page.evaluate("""
                                const btns = document.querySelectorAll('#free_play_form_button, button[id*="play"], button.claim-btn, button[type="submit"]');
                                btns.forEach(btn => {
                                    if (btn.disabled) {
                                        btn.disabled = false;
                                        btn.removeAttribute('disabled');
                                    }
                                });
                            """)
                            logger.debug("[FreeBitcoin] Manually enabled roll button")
                        except Exception:
                            pass
                        
                        await asyncio.sleep(1)
                        
                    except Exception as captcha_err:
                        logger.error(f"[DEBUG] CAPTCHA solve failed: {captcha_err}")
                        return ClaimResult(
                            success=False,
                            status="CAPTCHA Failed",
                            next_claim_minutes=15,
                            balance=balance
                        )

                    # Double check visibility after potential captcha delay
                    if await roll_btn.is_visible():
                        logger.debug("[FreeBitcoin] About to click roll button")
                        await self.human_like_click(roll_btn)
                        logger.debug("[FreeBitcoin] Roll button clicked")
                        await self.idle_mouse(1.0)  # Read result naturally
                        
                        # Wait for any navigation/reload
                        logger.debug("[FreeBitcoin] Waiting for page stabilization...")
                        try:
                            await self.page.wait_for_navigation(timeout=8000)
                            logger.debug("[FreeBitcoin] Page navigated")
                        except Exception as e:
                            logger.debug(f"[FreeBitcoin] No navigation detected: {e}")
                        
                        # Wait longer for result - FreeBitcoin can take 10-15 seconds
                        logger.debug("[FreeBitcoin] Waiting for claim result...")
                        await asyncio.sleep(3)
                        await self.close_popups()
                        
                        # Log current page URL to verify we're still on the right page
                        current_url = self.page.url
                        logger.debug(f"[FreeBitcoin] Current page URL after click: {current_url}")

                        # Try multiple result selectors with logging
                        result_selectors = [
                            "#winnings",
                            ".winning-amount", 
                            ".result-amount",
                            ".btc-won",
                            "span:has-text('BTC')",
                            ".win_amount",
                            ".claim-result",
                            "[data-result]"
                        ]
                        
                        is_visible = False
                        won_text = None
                        
                        for selector in result_selectors:
                            try:
                                loc = self.page.locator(selector)
                                count = await loc.count()
                                if count > 0:
                                    is_element_visible = await loc.first.is_visible()
                                    logger.debug(f"[FreeBitcoin] Selector '{selector}': found {count}, visible={is_element_visible}")
                                    if is_element_visible:
                                        won_text = await loc.first.text_content()
                                        is_visible = True
                                        logger.debug(f"[FreeBitcoin] Result found with selector '{selector}': {won_text}")
                                        break
                            except Exception as e:
                                logger.debug(f"[FreeBitcoin] Error checking selector '{selector}': {e}")
                        
                        if is_visible and won_text:
                            # Use DataExtractor for consistent parsing
                            clean_amount = DataExtractor.extract_balance(won_text)

                            # If we found a non-zero result text on the page, that IS the confirmation
                            # (The page display may not update immediately on freebitco.in)
                            if clean_amount and clean_amount != "0":
                                logger.info(f"FreeBitcoin Claimed! Won: {won_text} ({clean_amount})")
                                return ClaimResult(
                                    success=True,
                                    status="Claimed",
                                    next_claim_minutes=60,
                                    amount=clean_amount,
                                    balance="Unknown"  # Balance display not updated yet on page
                                )

                            logger.warning("[FreeBitcoin] Result text found but amount is 0 or invalid.")
                            return ClaimResult(
                                success=False,
                                status="Zero Amount",
                                next_claim_minutes=10,
                                amount=clean_amount or "0",
                                balance=balance
                            )
                        else:
                            # Result not found - log what we see on the page
                            logger.warning("[FreeBitcoin] Claim result not found on page")
                            logger.debug(f"[FreeBitcoin] Page content length: {len(await self.page.content())}")
                            
                            # Try to find ANY text on the page that might indicate success
                            try:
                                page_text = await self.page.text_content()
                                logger.debug(f"[FreeBitcoin] Page text preview: {page_text[:500] if page_text else 'empty'}")
                            except Exception as e:
                                logger.debug(f"[FreeBitcoin] Error getting page text: {e}")
                            
                            return ClaimResult(
                                success=False,
                                status="Result Not Found",
                                next_claim_minutes=15,
                                balance=balance
                            )
                    else:
                        logger.warning(
                            f"[DEBUG] Roll button disappeared after captcha solve. "
                            f"Page URL: {self.page.url}, Roll button count: {await self.page.locator('#free_play_form_button').count()}"
                        )
                        return ClaimResult(
                            success=False,
                            status="Roll Button Vanished",
                            next_claim_minutes=15,
                            balance=balance
                        )
                else:
                    logger.warning("Roll button not found (possibly hidden or blocked)")
                    return ClaimResult(
                        success=False,
                        status="Roll Button Not Found",
                        next_claim_minutes=15,
                        balance=balance
                    )

            except asyncio.TimeoutError as e:
                logger.warning(f"FreeBitcoin claim timeout attempt {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 5  # Exponential backoff: 5s, 10s, 20s
                    logger.info(f"Retrying in {backoff_time}s...")
                    await asyncio.sleep(backoff_time)
                    continue
                return ClaimResult(
                    success=False,
                    status=f"Timeout after {max_retries} attempts",
                    next_claim_minutes=30
                )

            except Exception as e:
                logger.error(f"FreeBitcoin claim failed attempt {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 5
                    logger.info(f"Retrying in {backoff_time}s...")
                    await asyncio.sleep(backoff_time)
                    continue
                return ClaimResult(
                    success=False,
                    status=f"Error: {e}",
                    next_claim_minutes=30
                )
            
        logger.warning(f"FreeBitcoin claim reached unknown failure path. URL: {self.page.url}")
        return ClaimResult(success=False, status="Unknown Failure", next_claim_minutes=15)

    def get_jobs(self):
        """Returns FreeBitcoin-specific jobs for the scheduler."""
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
                next_run=time.time() + 86400,  # Check withdrawal daily
                name=f"{self.faucet_name} Withdraw",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="withdraw_wrapper"
            )
        ]

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for FreeBitcoin.
        
        Supports three modes:
        - Auto Withdraw: Enabled via settings, happens automatically
        - Slow Withdraw: Lower fee (~400 sat), 6-24 hour processing
        - Instant Withdraw: Higher fee, 15 min processing
        
        Minimum: 30,000 satoshis (0.0003 BTC)
        """
        try:
            logger.info(f"[{self.faucet_name}] Navigating to withdrawal page...")
            await self.page.goto(f"{self.base_url}/?op=withdraw")
            await self.handle_cloudflare()
            await self.close_popups()
            
            # Get current balance - use #balance_small as primary (confirmed working)
            balance = await self.get_balance(
                "#balance_small",
                fallback_selectors=["#balance", ".balanceli", "li.balanceli span"]
            )
            balance_sat = int(float(balance) * 100000000) if balance else 0
            
            # Check minimum (30,000 satoshis)
            min_withdraw = 30000
            if balance_sat < min_withdraw:
                logger.info(f"[{self.faucet_name}] Balance {balance_sat} sat below minimum {min_withdraw}")
                return ClaimResult(success=True, status="Low Balance", next_claim_minutes=1440)
            
            # Get withdrawal address
            address = self.get_withdrawal_address("BTC")
            if not address:
                logger.error(f"[{self.faucet_name}] No BTC withdrawal address configured")
                return ClaimResult(success=False, status="No Address", next_claim_minutes=1440)
            
            # Fill withdrawal form with human-like typing
            address_field = self.page.locator("input#withdraw_address, input[name='address']")
            amount_field = self.page.locator("input#withdraw_amount, input[name='amount']")
            
            # Use "Slow Withdraw" for lower fees
            slow_radio = self.page.locator("input[value='slow'], #slow_withdraw")
            if await slow_radio.is_visible():
                await self.human_like_click(slow_radio)
                logger.debug(f"[{self.faucet_name}] Selected slow withdrawal for lower fees")
            
            # Click Max/All button if available
            max_btn = self.page.locator("button:has-text('Max'), #max_withdraw")
            if await max_btn.is_visible():
                await self.human_like_click(max_btn)
                logger.debug(f"[{self.faucet_name}] Clicked max withdrawal button")
            elif await amount_field.is_visible():
                await amount_field.fill(str(float(balance)))
                logger.debug(f"[{self.faucet_name}] Filled withdrawal amount: {balance}")
            
            logger.debug(f"[{self.faucet_name}] Filling withdrawal address with human-like typing")
            await self.human_type(address_field, address)
            await self.idle_mouse(1.0)  # Think time before submission
            
            # Handle 2FA if present
            twofa_field = self.page.locator("input#twofa_code, input[name='2fa']")
            if await twofa_field.is_visible():
                logger.warning(f"[{self.faucet_name}] 2FA field detected - manual intervention required")
                return ClaimResult(success=False, status="2FA Required", next_claim_minutes=60)
            
            # Solve captcha
            logger.debug(f"[{self.faucet_name}] Solving CAPTCHA for withdrawal...")
            try:
                await self.solver.solve_captcha(self.page)
                logger.debug(f"[{self.faucet_name}] CAPTCHA solved successfully")
            except Exception as captcha_err:
                logger.error(f"[{self.faucet_name}] Withdrawal CAPTCHA solve failed: {captcha_err}")
                return ClaimResult(success=False, status="CAPTCHA Failed", next_claim_minutes=60)
            
            # Submit
            submit_btn = self.page.locator("button#withdraw_button, button:has-text('Withdraw')")
            await self.human_like_click(submit_btn)
            
            await self.random_delay(3, 5)
            
            # Check result
            success_msg = self.page.locator(".alert-success, #withdraw_success, :has-text('successful')")
            if await success_msg.count() > 0:
                logger.info(f"🚀 [{self.faucet_name}] Withdrawal submitted: {balance} BTC")
                return ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440)
            
            # Check for error messages
            error_msg = self.page.locator(".alert-danger, .error, #withdraw_error")
            if await error_msg.count() > 0:
                error_text = await error_msg.first.text_content()
                logger.warning(f"[{self.faucet_name}] Withdrawal error: {error_text}")
                return ClaimResult(success=False, status=f"Error: {error_text}", next_claim_minutes=360)
            
            return ClaimResult(success=False, status="Unknown Result", next_claim_minutes=360)
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)

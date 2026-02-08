"""FreeBitcoin faucet bot for Cryptobot Gen 3.0.

Implements ``freebitco.in`` -- one of the oldest Bitcoin faucets.  Features:
    * Hourly BTC claims via the main "ROLL" button.
    * Multiply BTC (hi-lo gambling game -- optional).
    * Reward points accumulation and free-roll bonuses.
    * Cloudflare / reCAPTCHA / Turnstile bypass.

Claim interval: ~60 minutes.

Known issues:
    * Login success rate is currently ~0 %% -- selectors may require update
      or credential refresh (see ``copilot-instructions.md``).
"""

import asyncio
import logging
import random
import time
from typing import Any

from core.extractor import DataExtractor
from .base import ClaimResult, FaucetBot

logger = logging.getLogger(__name__)


class FreeBitcoinBot(FaucetBot):
    """FreeBitco.in faucet bot.

    Handles login, hourly roll claims, balance extraction, and withdrawal.
    Currently experiencing 100 %% login failure rate -- investigate selector
    changes on the site.
    """

    def __init__(
        self, settings: Any, page: Any, **kwargs: Any
    ) -> None:
        """Initialize the FreeBitcoin faucet bot.

        Args:
            settings: Application settings / configuration object.
            page: Playwright browser page instance.
            **kwargs: Additional keyword arguments forwarded to
                the parent ``FaucetBot``.
        """
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "FreeBitcoin"
        self.base_url = "https://freebitco.in"

    async def is_logged_in(self) -> bool:
        """Check whether the user is currently logged in.

        Iterates over balance and logout selectors to determine
        whether an active session exists on the page.

        Returns:
            True if a logged-in indicator is visible, False
            otherwise.
        """
        balance_selectors = [
            "#balance_small",
            "#balance_small span",
            ".balanceli",
            "#balance",
            ".balance",
            "[data-balance]",
            ".user-balance",
            "span.balance",
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
                if await self.page.locator(selector).is_visible(
                    timeout=3000
                ):
                    return True
            except Exception:
                continue
        return False

    async def _wait_for_captcha_token(
        self, timeout: int = 15000
    ) -> bool:
        """Wait for a captcha token to be injected into the page.

        Args:
            timeout: Maximum wait time in milliseconds.

        Returns:
            True if a valid captcha token was found, False on
            timeout.
        """
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
        """Check for FreeBitcoin session cookies.

        Returns:
            True if ``fbtc_session`` or ``fbtc_userid`` cookies
            are present.
        """
        try:
            cookies = await self.page.context.cookies(
                self.base_url
            )
        except Exception:
            return False
        names = {cookie.get("name") for cookie in cookies}
        return "fbtc_session" in names or "fbtc_userid" in names

    async def _log_login_diagnostics(
        self, context: str
    ) -> None:
        """Log login page diagnostics for debugging.

        Captures and logs details about inputs, textareas, iframes,
        captcha elements, forms, script sources, and JavaScript
        state to aid debugging of login failures.

        Args:
            context: Label describing the diagnostic context
                (e.g. ``"login_failed_attempt_1"``).
        """
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

        prefix = f"[FreeBitcoin] Login diagnostics ({context})"
        logger.info("%s: inputs=%s", prefix, inputs)
        logger.info("%s: textareas=%s", prefix, textareas)
        logger.info("%s: iframes=%s", prefix, iframes)
        logger.info(
            "%s: captcha_nodes=%s", prefix, captcha_nodes
        )
        logger.info("%s: forms=%s", prefix, form_summaries)
        logger.info(
            "%s: int_page_captchas_html=%s",
            prefix,
            int_captcha_html,
        )
        logger.info(
            "%s: login_form_html=%s", prefix, login_form_html
        )
        logger.info(
            "%s: captcha_state=%s", prefix, captcha_state
        )
        logger.info(
            "%s: login_nodes=%s", prefix, login_nodes
        )
        logger.info(
            "%s: login_input_forms=%s",
            prefix,
            login_input_forms,
        )
        logger.info(
            "%s: script_sources=%s", prefix, script_sources
        )
        logger.info("%s: js_state=%s", prefix, js_state)

    async def login(self) -> bool:
        """Log in to FreeBitcoin with retry and error logging.

        Simplified login flow with exponential backoff.  Uses a
        single, clean browser-based approach with the confirmed
        ``#login_form_btc_address`` / ``#login_form_password``
        selectors (Feb 2026).

        Returns:
            True on successful login, False after all retries are
            exhausted.
        """
        # Check for override (Multi-Account Loop)
        if self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("freebitcoin")

        if not creds:
            logger.error(
                "[FreeBitcoin] Credentials missing"
                " - set FREEBITCOIN_USERNAME and"
                " FREEBITCOIN_PASSWORD"
            )
            return False

        # Extract credentials
        login_id = creds.get("username") or creds.get("email")
        if not login_id:
            logger.error(
                "[FreeBitcoin] Credentials missing username/email"
            )
            return False
        login_id = self.strip_email_alias(login_id)
        if not login_id:
            logger.error(
                "[FreeBitcoin] Invalid username/email"
                " after processing"
            )
            return False
        password = creds.get("password")
        if not password:
            logger.error(
                "[FreeBitcoin] Credentials missing password"
            )
            return False

        # Updated selectors based on diagnostic findings (Feb 2026)
        email_selectors = [
            "#login_form_btc_address",
            "input[name='btc_address']",
            "input[type='text'][name='btc_address']",
            "#email",
        ]

        password_selectors = [
            "#login_form_password",
            "input[name='password']",
            "input[type='password']",
            "#password",
        ]

        submit_selectors = [
            "#login_button",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Login')",
        ]

        # Retry logic with exponential backoff
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    backoff_seconds = 5 * attempt
                    logger.info(
                        "[FreeBitcoin] Login attempt"
                        " %d/%d after %ds backoff",
                        attempt + 1,
                        max_attempts,
                        backoff_seconds,
                    )
                    await self.human_wait(
                        backoff_seconds, with_interactions=True
                    )
                else:
                    logger.info(
                        "[FreeBitcoin] Login attempt %d/%d",
                        attempt + 1,
                        max_attempts,
                    )

                # Navigate to base URL
                logger.info(
                    "[FreeBitcoin] Navigating to: %s",
                    self.base_url,
                )

                if not await self.safe_navigate(self.base_url):
                    logger.warning(
                        "[FreeBitcoin] Navigation failed"
                        " on attempt %d",
                        attempt + 1,
                    )
                    continue

                await self.random_delay(1, 2)

                # Handle Cloudflare and popups
                try:
                    await self.handle_cloudflare(
                        max_wait_seconds=60
                    )
                except Exception as cf_err:
                    logger.debug(
                        "[FreeBitcoin] Cloudflare handling: %s",
                        cf_err,
                    )

                await self.close_popups()
                await self.human_wait(1)

                # Warm up page with natural browsing behavior
                await self.warm_up_page()

                # Log current state
                current_url = self.page.url
                page_title = await self.page.title()
                logger.info(
                    "[FreeBitcoin] Current page"
                    " - URL: %s, Title: %s",
                    current_url,
                    page_title,
                )

                # Check if already logged in
                if await self.is_logged_in():
                    logger.info(
                        "[FreeBitcoin] Session already active"
                    )
                    return True

                # Click login trigger to show hidden login form
                login_trigger_selectors = [
                    "a:has-text('LOGIN')",
                    "a:has-text('Log In')",
                    "button:has-text('LOGIN')",
                    "a[href*='login']",
                    "a[href*='op=login']",
                    ".login-link",
                    "#login_link",
                ]

                login_trigger_clicked = False
                for selector in login_trigger_selectors:
                    try:
                        locator = self.page.locator(
                            selector
                        ).first
                        if await locator.is_visible(
                            timeout=3000
                        ):
                            logger.info(
                                "[FreeBitcoin] Clicking login"
                                " trigger: %s",
                                selector,
                            )
                            await self.human_like_click(locator)
                            await self.human_wait(
                                5, with_interactions=True
                            )
                            login_trigger_clicked = True
                            break
                    except Exception:
                        continue

                if not login_trigger_clicked:
                    logger.warning(
                        "[FreeBitcoin] No login trigger found"
                        " - form may already be visible"
                    )

                # Wait for login form to be fully visible
                logger.debug(
                    "[FreeBitcoin] Waiting for login form"
                    " to appear..."
                )
                try:
                    await self.page.wait_for_selector(
                        '#login_form_btc_address',
                        state='visible',
                        timeout=10000,
                    )
                    await self.page.wait_for_selector(
                        '#login_form_password',
                        state='visible',
                        timeout=5000,
                    )
                    logger.info(
                        "[FreeBitcoin] Login form is now visible"
                    )
                except Exception as wait_err:
                    logger.warning(
                        "[FreeBitcoin] Login form wait"
                        " timeout: %s",
                        wait_err,
                    )

                # Solve landing page CAPTCHA if present
                logger.debug(
                    "[FreeBitcoin] Checking for landing"
                    " page CAPTCHA..."
                )
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
                        logger.info(
                            "[FreeBitcoin] Landing page CAPTCHA"
                            " detected - solving..."
                        )
                        solved = await self.solver.solve_captcha(
                            self.page
                        )
                        if solved is False:
                            logger.error(
                                "[FreeBitcoin] Landing page"
                                " CAPTCHA solve failed"
                            )
                            continue
                        logger.info(
                            "[FreeBitcoin] Landing page"
                            " CAPTCHA solved"
                        )
                        await self.human_wait(2)
                except Exception as captcha_err:
                    logger.debug(
                        "[FreeBitcoin] Landing CAPTCHA"
                        " check: %s",
                        captcha_err,
                    )

                # Find email field
                email_field = None
                for selector in email_selectors:
                    try:
                        locator = self.page.locator(
                            selector
                        ).first
                        if await locator.is_visible(
                            timeout=5000
                        ):
                            logger.info(
                                "[FreeBitcoin] Using email"
                                " selector: %s",
                                selector,
                            )
                            email_field = locator
                            break
                    except Exception:
                        continue

                if not email_field:
                    logger.warning(
                        "[FreeBitcoin] Email field not found"
                        " on %s",
                        current_url,
                    )
                    try:
                        visible_inputs = (
                            await self.page.evaluate(
                                """
                                () => Array.from(document.querySelectorAll('input:visible')).map(el => ({
                                    type: el.type,
                                    name: el.name,
                                    id: el.id,
                                    placeholder: el.placeholder
                                })).slice(0, 10)
                                """
                            )
                        )
                        logger.info(
                            "[FreeBitcoin] Visible inputs: %s",
                            visible_inputs,
                        )
                    except Exception:
                        pass
                    continue

                # Find password field
                password_field = None
                for selector in password_selectors:
                    try:
                        locator = self.page.locator(
                            selector
                        ).first
                        if await locator.is_visible(
                            timeout=5000
                        ):
                            logger.info(
                                "[FreeBitcoin] Using password"
                                " selector: %s",
                                selector,
                            )
                            password_field = locator
                            break
                    except Exception:
                        continue

                if not password_field:
                    logger.warning(
                        "[FreeBitcoin] Password field not"
                        " found on %s",
                        current_url,
                    )
                    continue

                # Fill credentials
                if len(login_id) > 10:
                    username_display = login_id[:10] + "***"
                else:
                    username_display = login_id[:3] + "***"
                logger.info(
                    "[FreeBitcoin] Filling credentials"
                    " for user: %s",
                    username_display,
                )

                try:
                    await self.human_type(
                        email_field, login_id
                    )
                    await self.random_delay(0.5, 1.0)
                    await self.human_type(
                        password_field, password
                    )
                    await self.idle_mouse(0.5)
                except Exception as type_err:
                    logger.warning(
                        "[FreeBitcoin] Human typing failed:"
                        " %s, using direct fill",
                        type_err,
                    )
                    await email_field.fill(login_id)
                    await self.random_delay(0.3, 0.5)
                    await password_field.fill(password)

                # Check for CAPTCHA on login form
                logger.debug(
                    "[FreeBitcoin] Checking for login"
                    " form CAPTCHA..."
                )
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
                        logger.info(
                            "[FreeBitcoin] Login form CAPTCHA"
                            " detected - solving..."
                        )
                        solved = await self.solver.solve_captcha(
                            self.page
                        )
                        if solved is False:
                            logger.error(
                                "[FreeBitcoin] Login form"
                                " CAPTCHA solve failed"
                            )
                            continue
                        logger.info(
                            "[FreeBitcoin] Login form"
                            " CAPTCHA solved"
                        )
                        await self.human_wait(2)
                except Exception as captcha_err:
                    logger.debug(
                        "[FreeBitcoin] Login form CAPTCHA"
                        " check: %s",
                        captcha_err,
                    )

                # Find and click submit button
                submit_btn = None
                for selector in submit_selectors:
                    try:
                        locator = self.page.locator(
                            selector
                        ).first
                        if await locator.is_visible(
                            timeout=5000
                        ):
                            logger.info(
                                "[FreeBitcoin] Using submit"
                                " selector: %s",
                                selector,
                            )
                            submit_btn = locator
                            break
                    except Exception:
                        continue

                if submit_btn:
                    logger.debug(
                        "[FreeBitcoin] Clicking submit button..."
                    )
                    await self.thinking_pause()
                    await self.human_like_click(submit_btn)
                else:
                    logger.warning(
                        "[FreeBitcoin] Submit button not found,"
                        " trying Enter key..."
                    )
                    try:
                        await password_field.press("Enter")
                    except Exception:
                        logger.error(
                            "[FreeBitcoin] Enter key failed"
                        )
                        timestamp = int(time.time())
                        screenshot_path = (
                            "logs/freebitcoin_login_failed"
                            f"_no_submit_{timestamp}.png"
                        )
                        try:
                            await self.page.screenshot(
                                path=screenshot_path,
                                full_page=True,
                            )
                            logger.info(
                                "[FreeBitcoin] Screenshot"
                                " saved: %s",
                                screenshot_path,
                            )
                        except Exception:
                            pass
                        continue

                # Wait for navigation
                logger.debug(
                    "[FreeBitcoin] Waiting for login"
                    " to complete..."
                )
                try:
                    await self.page.wait_for_load_state(
                        "domcontentloaded", timeout=15000
                    )
                    try:
                        await self.page.wait_for_load_state(
                            "networkidle", timeout=5000
                        )
                    except Exception:
                        pass
                except asyncio.TimeoutError:
                    logger.warning(
                        "[FreeBitcoin] Login redirect timeout"
                    )

                await self.random_delay(2, 3)

                # Check if logged in
                if await self.is_logged_in():
                    logger.info(
                        "[FreeBitcoin] Login successful!"
                    )
                    return True

                # Check for error messages
                error_text = ""
                try:
                    error_selectors = [
                        ".alert-danger",
                        ".error",
                        ".login-error",
                        "#login_error",
                        "div[style*='color: red']",
                        "div[style*='color:red']",
                    ]

                    for err_sel in error_selectors:
                        error_elem = self.page.locator(
                            err_sel
                        ).first
                        if await error_elem.is_visible(
                            timeout=1000
                        ):
                            error_text = (
                                await error_elem.text_content()
                            )
                            error_text = error_text.strip()
                            logger.error(
                                "[FreeBitcoin] Login error"
                                " message: %s",
                                error_text,
                            )

                            if "account locked" in (
                                error_text.lower()
                            ):
                                logger.critical(
                                    "[FreeBitcoin] ACCOUNT"
                                    " LOCKED detected!"
                                )
                            if "too many" in (
                                error_text.lower()
                            ):
                                logger.critical(
                                    "[FreeBitcoin] RATE LIMIT"
                                    " (Too many attempts)"
                                    " detected!"
                                )
                            break
                except Exception:
                    pass

                # Take screenshot on failure
                timestamp = int(time.time())
                screenshot_path = (
                    "logs/freebitcoin_login_failed"
                    f"_{timestamp}.png"
                )
                try:
                    await self.page.screenshot(
                        path=screenshot_path, full_page=True
                    )
                    logger.info(
                        "[FreeBitcoin] Screenshot saved: %s",
                        screenshot_path,
                    )
                except Exception:
                    pass

                # Log diagnostics
                await self._log_login_diagnostics(
                    f"login_failed_attempt_{attempt + 1}"
                )

            except Exception as e:
                logger.error(
                    "[FreeBitcoin] Login attempt %d"
                    " exception: %s",
                    attempt + 1,
                    e,
                    exc_info=True,
                )
                timestamp = int(time.time())
                screenshot_path = (
                    "logs/freebitcoin_login_exception"
                    f"_{timestamp}.png"
                )
                try:
                    await self.page.screenshot(
                        path=screenshot_path
                    )
                    logger.info(
                        "[FreeBitcoin] Exception screenshot"
                        " saved: %s",
                        screenshot_path,
                    )
                except Exception:
                    pass

        # All attempts failed
        logger.error(
            "[FreeBitcoin] Login failed after %d attempts",
            max_attempts,
        )
        return False

    async def claim(self) -> ClaimResult:
        """Execute the hourly roll claim for FreeBitcoin.

        Navigates to the main page, checks balance and timer,
        solves any CAPTCHA, and clicks the roll button.  Includes
        retry logic with exponential backoff for transient network
        failures.

        Returns:
            ClaimResult with success status, amount won, and
            suggested next-claim delay.
        """
        logger.info("[DEBUG] FreeBitcoin claim() method started")

        max_retries = 3
        nav_timeout = getattr(
            self.settings, "timeout", 180000
        )
        for attempt in range(max_retries):
            try:
                logger.info(
                    "[DEBUG] Attempt %d/%d: Navigating to %s/",
                    attempt + 1,
                    max_retries,
                    self.base_url,
                )
                response = await self.page.goto(
                    f"{self.base_url}/", timeout=nav_timeout
                )
                if response is not None:
                    try:
                        status = response.status
                        if status in (401, 403, 429):
                            from core.orchestrator import (
                                ErrorType,
                            )

                            logger.error(
                                "[FreeBitcoin] Claim page"
                                " returned HTTP %d. URL: %s",
                                status,
                                response.url,
                            )
                            error_type = (
                                ErrorType.PROXY_ISSUE
                                if status == 403
                                else ErrorType.RATE_LIMIT
                            )
                            return ClaimResult(
                                success=False,
                                status=f"HTTP {status}",
                                next_claim_minutes=30,
                                error_type=error_type,
                            )
                    except Exception:
                        pass
                await self.handle_cloudflare(
                    max_wait_seconds=60
                )
                await self.close_popups()
                await self.random_delay(2, 4)

                # Simulate natural browsing after page load
                await self.simulate_reading(
                    duration=random.uniform(2.0, 4.0)
                )
                if random.random() < 0.4:
                    await self.natural_scroll()

                # Extract balance with fallback selectors
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
                        ".account-balance",
                    ],
                )
                logger.info(
                    "[DEBUG] Balance: %s", balance
                )

                # Check if timer is running (already claimed)
                logger.info("[DEBUG] Checking timer...")
                wait_min = await self.get_timer(
                    ".countdown_time_remaining",
                    fallback_selectors=[
                        "#time_remaining",
                        "#countdown_timer",
                        "span#timer",
                        ".countdown",
                        "[data-next-claim]",
                        ".time-remaining",
                    ],
                )
                logger.info(
                    "[DEBUG] Timer: %s minutes", wait_min
                )
                if wait_min > 0:
                    await self.simulate_reading(2.0)
                    return ClaimResult(
                        success=True,
                        status="Timer Active",
                        next_claim_minutes=wait_min,
                        balance=balance,
                    )

                # Check for roll button before solving CAPTCHA
                roll_btn = self.page.locator(
                    "#free_play_form_button,"
                    " input#free_play_form_button,"
                    " input[name='free_play_form_button'],"
                    " button#free_play_form_button,"
                    " button[id*='play'],"
                    " .homepage_play_now_button,"
                    " .claim-btn,"
                    " button:has-text('Roll'),"
                    " button:has-text('ROLL'),"
                    " button:has-text('Play'),"
                    " input[value*='ROLL'],"
                    " input[value*='Roll']"
                ).first

                try:
                    await roll_btn.wait_for(
                        state="visible", timeout=8000
                    )
                    roll_visible = True
                except Exception:
                    roll_visible = False

                if roll_visible:
                    if not await roll_btn.is_enabled():
                        logger.warning(
                            "[DEBUG] Roll button is visible"
                            " but disabled"
                        )
                        return ClaimResult(
                            success=False,
                            status="Roll Disabled",
                            next_claim_minutes=15,
                            balance=balance,
                        )
                    logger.info(
                        "[DEBUG] Roll button found."
                        " Initiating Captcha Solve..."
                    )

                    # Handle Cloudflare & Captcha
                    logger.debug(
                        "[DEBUG] Checking for CloudFlare"
                        " protection..."
                    )
                    cf_result = await self.handle_cloudflare()
                    logger.debug(
                        "[DEBUG] CloudFlare check result: %s",
                        cf_result,
                    )

                    # Solve CAPTCHA with error handling
                    logger.debug(
                        "[DEBUG] Solving CAPTCHA for claim..."
                    )
                    try:
                        await self.solver.solve_captcha(
                            self.page
                        )
                        logger.debug(
                            "[DEBUG] CAPTCHA solved successfully"
                        )

                        # Manually enable roll button
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
                            logger.debug(
                                "[FreeBitcoin] Manually enabled"
                                " roll button"
                            )
                        except Exception:
                            pass

                        await self.human_wait(1)
                        await self.thinking_pause()

                    except Exception as captcha_err:
                        logger.error(
                            "[DEBUG] CAPTCHA solve failed: %s",
                            captcha_err,
                        )
                        return ClaimResult(
                            success=False,
                            status="CAPTCHA Failed",
                            next_claim_minutes=15,
                            balance=balance,
                        )

                    # Double check visibility after captcha
                    if await roll_btn.is_visible():
                        logger.debug(
                            "[FreeBitcoin] About to click"
                            " roll button"
                        )
                        await self.simulate_reading(
                            duration=random.uniform(1.0, 2.0)
                        )
                        await self.human_like_click(roll_btn)
                        logger.debug(
                            "[FreeBitcoin] Roll button clicked"
                        )
                        await self.idle_mouse(1.0)

                        # Wait for any navigation/reload
                        logger.debug(
                            "[FreeBitcoin] Waiting for page"
                            " stabilization..."
                        )
                        try:
                            await self.page.wait_for_navigation(
                                timeout=8000
                            )
                            logger.debug(
                                "[FreeBitcoin] Page navigated"
                            )
                        except Exception:
                            logger.debug(
                                "[FreeBitcoin] No navigation"
                                " detected"
                            )

                        # Wait for result
                        logger.debug(
                            "[FreeBitcoin] Waiting for claim"
                            " result..."
                        )
                        await self.human_wait(3)
                        await self.close_popups()

                        current_url = self.page.url
                        logger.debug(
                            "[FreeBitcoin] Current page URL"
                            " after click: %s",
                            current_url,
                        )

                        # Try multiple result selectors
                        result_selectors = [
                            "#winnings",
                            ".winning-amount",
                            ".result-amount",
                            ".btc-won",
                            "span:has-text('BTC')",
                            ".win_amount",
                            ".claim-result",
                            "[data-result]",
                        ]

                        is_visible = False
                        won_text = None

                        for selector in result_selectors:
                            try:
                                loc = self.page.locator(
                                    selector
                                )
                                count = await loc.count()
                                if count > 0:
                                    el_visible = (
                                        await loc.first
                                        .is_visible()
                                    )
                                    logger.debug(
                                        "[FreeBitcoin]"
                                        " Selector '%s':"
                                        " found %d,"
                                        " visible=%s",
                                        selector,
                                        count,
                                        el_visible,
                                    )
                                    if el_visible:
                                        won_text = (
                                            await loc.first
                                            .text_content()
                                        )
                                        is_visible = True
                                        logger.debug(
                                            "[FreeBitcoin]"
                                            " Result found"
                                            " with '%s': %s",
                                            selector,
                                            won_text,
                                        )
                                        break
                            except Exception as e:
                                logger.debug(
                                    "[FreeBitcoin] Error"
                                    " checking selector"
                                    " '%s': %s",
                                    selector,
                                    e,
                                )

                        if is_visible and won_text:
                            clean_amount = (
                                DataExtractor.extract_balance(
                                    won_text
                                )
                            )

                            if (
                                clean_amount
                                and clean_amount != "0"
                            ):
                                logger.info(
                                    "FreeBitcoin Claimed!"
                                    " Won: %s (%s)",
                                    won_text,
                                    clean_amount,
                                )
                                return ClaimResult(
                                    success=True,
                                    status="Claimed",
                                    next_claim_minutes=60,
                                    amount=clean_amount,
                                    balance="Unknown",
                                )

                            logger.warning(
                                "[FreeBitcoin] Result text"
                                " found but amount is 0"
                                " or invalid."
                            )
                            return ClaimResult(
                                success=False,
                                status="Zero Amount",
                                next_claim_minutes=10,
                                amount=clean_amount or "0",
                                balance=balance,
                            )
                        else:
                            logger.warning(
                                "[FreeBitcoin] Claim result"
                                " not found on page"
                            )
                            page_content = (
                                await self.page.content()
                            )
                            logger.debug(
                                "[FreeBitcoin] Page content"
                                " length: %d",
                                len(page_content),
                            )

                            try:
                                page_text = (
                                    await self.page.inner_text(
                                        "body"
                                    )
                                )
                                preview = (
                                    page_text[:500]
                                    if page_text
                                    else "empty"
                                )
                                logger.debug(
                                    "[FreeBitcoin] Page text"
                                    " preview: %s",
                                    preview,
                                )
                            except Exception:
                                pass

                            return ClaimResult(
                                success=False,
                                status="Result Not Found",
                                next_claim_minutes=15,
                                balance=balance,
                            )
                    else:
                        roll_count = (
                            await self.page.locator(
                                '#free_play_form_button'
                            ).count()
                        )
                        logger.warning(
                            "[DEBUG] Roll button disappeared"
                            " after captcha solve."
                            " Page URL: %s,"
                            " Roll button count: %d",
                            self.page.url,
                            roll_count,
                        )
                        return ClaimResult(
                            success=False,
                            status="Roll Button Vanished",
                            next_claim_minutes=15,
                            balance=balance,
                        )
                else:
                    logger.warning(
                        "Roll button not found"
                        " (possibly hidden or blocked)"
                    )
                    return ClaimResult(
                        success=False,
                        status="Roll Button Not Found",
                        next_claim_minutes=15,
                        balance=balance,
                    )

            except asyncio.TimeoutError as e:
                logger.warning(
                    "FreeBitcoin claim timeout attempt"
                    " %d/%d: %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 5
                    logger.info(
                        "Retrying in %ds...", backoff_time
                    )
                    await self.human_wait(
                        backoff_time, with_interactions=True
                    )
                    continue
                return ClaimResult(
                    success=False,
                    status=(
                        f"Timeout after {max_retries}"
                        " attempts"
                    ),
                    next_claim_minutes=30,
                )

            except Exception as e:
                logger.error(
                    "FreeBitcoin claim failed attempt"
                    " %d/%d: %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 5
                    logger.info(
                        "Retrying in %ds...", backoff_time
                    )
                    await self.human_wait(
                        backoff_time, with_interactions=True
                    )
                    continue
                return ClaimResult(
                    success=False,
                    status=f"Error: {e}",
                    next_claim_minutes=30,
                )

        logger.warning(
            "FreeBitcoin claim reached unknown failure path."
            " URL: %s",
            self.page.url,
        )
        return ClaimResult(
            success=False,
            status="Unknown Failure",
            next_claim_minutes=15,
        )

    def get_jobs(self) -> list[Any]:
        """Return FreeBitcoin-specific jobs for the scheduler.

        Returns:
            A list containing a claim job (hourly) and a
            withdrawal job (daily).
        """
        from core.orchestrator import Job

        return [
            Job(
                priority=1,
                next_run=time.time(),
                name=f"{self.faucet_name} Claim",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="claim_wrapper",
            ),
            Job(
                priority=5,
                next_run=time.time() + 86400,
                name=f"{self.faucet_name} Withdraw",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="withdraw_wrapper",
            ),
        ]

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for FreeBitcoin.

        Supports three modes:
            - Auto Withdraw: enabled via settings.
            - Slow Withdraw: lower fee (~400 sat), 6-24 h.
            - Instant Withdraw: higher fee, 15 min.

        Minimum: 30 000 satoshis (0.0003 BTC).

        Returns:
            ClaimResult indicating whether the withdrawal was
            submitted successfully.
        """
        try:
            logger.info(
                "[%s] Navigating to withdrawal page...",
                self.faucet_name,
            )
            await self.page.goto(
                f"{self.base_url}/?op=withdraw"
            )
            await self.handle_cloudflare()
            await self.close_popups()

            # Get current balance
            balance = await self.get_balance(
                "#balance_small",
                fallback_selectors=[
                    "#balance",
                    ".balanceli",
                    "li.balanceli span",
                ],
            )
            balance_sat = (
                int(float(balance) * 100000000)
                if balance
                else 0
            )

            # Check minimum (30,000 satoshis)
            min_withdraw = 30000
            if balance_sat < min_withdraw:
                logger.info(
                    "[%s] Balance %d sat below minimum %d",
                    self.faucet_name,
                    balance_sat,
                    min_withdraw,
                )
                return ClaimResult(
                    success=True,
                    status="Low Balance",
                    next_claim_minutes=1440,
                )

            # Get withdrawal address
            address = self.get_withdrawal_address("BTC")
            if not address:
                logger.error(
                    "[%s] No BTC withdrawal address configured",
                    self.faucet_name,
                )
                return ClaimResult(
                    success=False,
                    status="No Address",
                    next_claim_minutes=1440,
                )

            # Fill withdrawal form
            address_field = self.page.locator(
                "input#withdraw_address,"
                " input[name='address']"
            )
            amount_field = self.page.locator(
                "input#withdraw_amount,"
                " input[name='amount']"
            )

            # Use slow withdraw for lower fees
            slow_radio = self.page.locator(
                "input[value='slow'], #slow_withdraw"
            )
            if await slow_radio.is_visible():
                await self.human_like_click(slow_radio)
                logger.debug(
                    "[%s] Selected slow withdrawal"
                    " for lower fees",
                    self.faucet_name,
                )

            # Click Max/All button if available
            max_btn = self.page.locator(
                "button:has-text('Max'), #max_withdraw"
            )
            if await max_btn.is_visible():
                await self.human_like_click(max_btn)
                logger.debug(
                    "[%s] Clicked max withdrawal button",
                    self.faucet_name,
                )
            elif await amount_field.is_visible():
                await self.human_type(
                    amount_field, str(float(balance))
                )
                logger.debug(
                    "[%s] Filled withdrawal amount: %s",
                    self.faucet_name,
                    balance,
                )

            logger.debug(
                "[%s] Filling withdrawal address"
                " with human-like typing",
                self.faucet_name,
            )
            await self.human_type(address_field, address)
            await self.idle_mouse(1.0)

            # Handle 2FA if present
            twofa_field = self.page.locator(
                "input#twofa_code, input[name='2fa']"
            )
            if await twofa_field.is_visible():
                logger.warning(
                    "[%s] 2FA field detected"
                    " - manual intervention required",
                    self.faucet_name,
                )
                return ClaimResult(
                    success=False,
                    status="2FA Required",
                    next_claim_minutes=60,
                )

            # Solve captcha
            logger.debug(
                "[%s] Solving CAPTCHA for withdrawal...",
                self.faucet_name,
            )
            try:
                await self.solver.solve_captcha(self.page)
                logger.debug(
                    "[%s] CAPTCHA solved successfully",
                    self.faucet_name,
                )
            except Exception as captcha_err:
                logger.error(
                    "[%s] Withdrawal CAPTCHA solve"
                    " failed: %s",
                    self.faucet_name,
                    captcha_err,
                )
                return ClaimResult(
                    success=False,
                    status="CAPTCHA Failed",
                    next_claim_minutes=60,
                )

            # Submit
            await self.thinking_pause()
            submit_btn = self.page.locator(
                "button#withdraw_button,"
                " button:has-text('Withdraw')"
            )
            await self.human_like_click(submit_btn)

            await self.random_delay(3, 5)

            # Check result
            success_msg = self.page.locator(
                ".alert-success, #withdraw_success,"
                " :has-text('successful')"
            )
            if await success_msg.count() > 0:
                logger.info(
                    "[%s] Withdrawal submitted: %s BTC",
                    self.faucet_name,
                    balance,
                )
                return ClaimResult(
                    success=True,
                    status="Withdrawn",
                    next_claim_minutes=1440,
                )

            # Check for error messages
            error_msg = self.page.locator(
                ".alert-danger, .error, #withdraw_error"
            )
            if await error_msg.count() > 0:
                error_text = (
                    await error_msg.first.text_content()
                )
                logger.warning(
                    "[%s] Withdrawal error: %s",
                    self.faucet_name,
                    error_text,
                )
                return ClaimResult(
                    success=False,
                    status=f"Error: {error_text}",
                    next_claim_minutes=360,
                )

            return ClaimResult(
                success=False,
                status="Unknown Result",
                next_claim_minutes=360,
            )

        except Exception as e:
            logger.error(
                "[%s] Withdrawal error: %s",
                self.faucet_name,
                e,
            )
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=60,
            )

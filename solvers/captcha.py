"""Hybrid CAPTCHA solver for Cryptobot Gen 3.0.

Supports multiple CAPTCHA types and providers:
    * **Turnstile** (Cloudflare) -- via 2Captcha or CapSolver.
    * **hCaptcha** -- via 2Captcha createTask API or CapSolver.
    * **reCAPTCHA v2 / v3** -- via 2Captcha or CapSolver.
    * **Image CAPTCHAs** -- via 2Captcha.
    * **Altcha** (proof-of-work) -- solved locally, zero cost.

Features:
    * Adaptive provider routing (choose cheapest provider per-captcha type).
    * Daily budget tracking to prevent cost overruns.
    * Rate-limiting per 2Captcha API best practices.
    * Fallback provider support (e.g. CapSolver if 2Captcha fails).
    * Per-faucet cost attribution for profitability analysis.
    * Manual human-in-the-loop fallback when running in visible mode.
"""

import asyncio
import base64
import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# Rate limiting constants per 2Captcha API best practices
INITIAL_POLL_DELAY_SECONDS = 5
POLL_INTERVAL_SECONDS = 5
RECAPTCHA_INITIAL_DELAY = 15
ERROR_NO_SLOT_DELAY = 5
ERROR_ZERO_BALANCE_DELAY = 60
MAX_POLL_ATTEMPTS = 24
DEFAULT_DAILY_BUDGET_USD = 5.0


class CaptchaSolver:
    """Hybrid CAPTCHA solver with multi-provider support.

    Primary workflow:
        1. Detect CAPTCHA type on the page.
        2. Select the optimal provider.
        3. Submit the task and poll for the solution token.
        4. Inject the token into the page and trigger callbacks.
        5. Record cost and update per-faucet statistics.

    Attributes:
        api_key: API key for the primary solving provider.
        provider: Primary provider name.
        fallback_provider: Optional secondary provider name.
        daily_budget: Maximum daily CAPTCHA spend in USD.
        adaptive_routing: Enable cost-based provider selection.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: str = "2captcha",
        daily_budget: float = DEFAULT_DAILY_BUDGET_USD,
        fallback_provider: Optional[str] = None,
        fallback_api_key: Optional[str] = None,
        adaptive_routing: bool = False,
        routing_min_samples: int = 20,
    ) -> None:
        """Initialise the CaptchaSolver.

        Args:
            api_key: API key for the primary service.
            provider: Primary provider name.
            daily_budget: Maximum daily spend in USD.
            fallback_provider: Optional secondary provider.
            fallback_api_key: API key for fallback provider.
            adaptive_routing: If True, choose cheapest provider.
            routing_min_samples: Min samples for routing.
        """
        self.api_key = api_key
        self.provider = provider.lower().replace(
            "twocaptcha", "2captcha"
        )
        if fallback_provider:
            self.fallback_provider: Optional[str] = (
                fallback_provider.lower().replace(
                    "twocaptcha", "2captcha"
                )
            )
        else:
            self.fallback_provider = None
        self.fallback_api_key = fallback_api_key
        self.provider_stats: Dict[str, Dict[str, Any]] = {
            self.provider: {
                "solves": 0,
                "failures": 0,
                "cost": 0.0,
            },
        }
        self.faucet_provider_stats: Dict[
            str, Dict[str, Dict[str, Any]]
        ] = {}
        self.adaptive_routing = adaptive_routing
        self.routing_min_samples = routing_min_samples
        self.session: Optional[aiohttp.ClientSession] = None
        self.daily_budget = daily_budget
        self.faucet_name: Optional[str] = None
        self.last_request_time: float = 0
        self.consecutive_errors: int = 0
        self._daily_spend: float = 0.0
        self._budget_reset_date: str = time.strftime(
            "%Y-%m-%d"
        )
        self._solve_count_today: int = 0
        self._cost_per_solve: Dict[str, float] = {
            "turnstile": 0.003,
            "hcaptcha": 0.003,
            "userrecaptcha": 0.003,
            "image": 0.001,
            "altcha": 0.0,
        }
        if not self.api_key:
            logger.warning(
                "No CAPTCHA API key provided. "
                "Switching to MANUAL mode."
            )
            logger.warning(
                "You must solve CAPTCHAs yourself "
                "in the browser window."
            )
        self.proxy_string: Optional[str] = None
        self.headless: bool = False

    def set_faucet_name(
        self, faucet_name: Optional[str]
    ) -> None:
        """Associate solver with a faucet for cost tracking.

        Args:
            faucet_name: The faucet identifier or None.
        """
        self.faucet_name = faucet_name
        if (
            faucet_name
            and faucet_name not in self.faucet_provider_stats
        ):
            self.faucet_provider_stats[faucet_name] = {}

    def set_proxy(self, proxy_string: str) -> None:
        """Set proxy for all CAPTCHA API requests.

        Args:
            proxy_string: Full proxy URL.
        """
        self.proxy_string = proxy_string

    def set_headless(self, headless: bool) -> None:
        """Set whether the browser is running headless.

        Args:
            headless: True if headless mode.
        """
        self.headless = bool(headless)

    def set_fallback_provider(
        self, provider: str, api_key: str
    ) -> None:
        """Configure a fallback CAPTCHA provider.

        Args:
            provider: Provider name.
            api_key: API key for the fallback provider.
        """
        self.fallback_provider = provider.lower().replace(
            "twocaptcha", "2captcha"
        )
        self.fallback_api_key = api_key
        logger.info(
            "Fallback provider configured: %s",
            self.fallback_provider,
        )
        if self.fallback_provider not in self.provider_stats:
            self.provider_stats[self.fallback_provider] = {
                "solves": 0,
                "failures": 0,
                "cost": 0.0,
            }

    def _record_provider_result(
        self,
        provider: str,
        captcha_type: str,
        success: bool,
    ) -> None:
        """Record provider success/failure statistics.

        Args:
            provider: Provider name.
            captcha_type: CAPTCHA type string.
            success: Whether the solve succeeded.
        """
        if provider not in self.provider_stats:
            self.provider_stats[provider] = {
                "solves": 0,
                "failures": 0,
                "cost": 0.0,
            }
        if success:
            self.provider_stats[provider]["solves"] += 1
            self.provider_stats[provider]["cost"] += (
                self._cost_per_solve.get(
                    captcha_type, 0.003
                )
            )
        else:
            self.provider_stats[provider]["failures"] += 1

        if self.faucet_name:
            if (
                self.faucet_name
                not in self.faucet_provider_stats
            ):
                self.faucet_provider_stats[
                    self.faucet_name
                ] = {}
            fstats = self.faucet_provider_stats[
                self.faucet_name
            ]
            if provider not in fstats:
                fstats[provider] = {
                    "solves": 0,
                    "failures": 0,
                    "cost": 0.0,
                }
            if success:
                fstats[provider]["solves"] += 1
                fstats[provider]["cost"] += (
                    self._cost_per_solve.get(
                        captcha_type, 0.003
                    )
                )
            else:
                fstats[provider]["failures"] += 1

    def _expected_cost(
        self, provider: str, captcha_type: str
    ) -> Optional[float]:
        """Estimate expected cost per successful solve.

        Args:
            provider: Provider name to evaluate.
            captcha_type: CAPTCHA type for cost lookup.

        Returns:
            Estimated cost per solve or None.
        """
        stats = None
        if (
            self.faucet_name
            and self.faucet_name
            in self.faucet_provider_stats
        ):
            stats = self.faucet_provider_stats[
                self.faucet_name
            ].get(provider)
        if not stats:
            stats = self.provider_stats.get(provider)
        if not stats:
            return None
        total = (
            stats.get("solves", 0)
            + stats.get("failures", 0)
        )
        if total < self.routing_min_samples:
            return None
        success_rate = (
            stats.get("solves", 0) / max(total, 1)
        )
        base = self._cost_per_solve.get(
            captcha_type, 0.003
        )
        return base / max(success_rate, 0.1)

    def _choose_provider_order(
        self, captcha_type: str
    ) -> List[str]:
        """Return providers ordered by expected cost.

        Args:
            captcha_type: CAPTCHA type for cost estimation.

        Returns:
            Ordered list of provider names.
        """
        providers = [self.provider]
        if (
            self.fallback_provider
            and self.fallback_api_key
            and self.fallback_provider != self.provider
        ):
            providers.append(self.fallback_provider)
        if (
            not self.adaptive_routing
            or len(providers) == 1
        ):
            return providers
        scored = []
        for p in providers:
            expected = self._expected_cost(
                p, captcha_type
            )
            scored.append((p, expected))
        if all(exp is None for _, exp in scored):
            return providers
        scored.sort(key=lambda item: (
            item[1] is None,
            item[1] if item[1] is not None else 0,
        ))
        return [p for p, _ in scored]

    def _check_and_reset_daily_budget(self) -> None:
        """Reset daily budget if a new day started."""
        today = time.strftime("%Y-%m-%d")
        if today != self._budget_reset_date:
            logger.info(
                "New day. Resetting captcha budget. "
                "Yesterday: $%.4f",
                self._daily_spend,
            )
            self._daily_spend = 0.0
            self._solve_count_today = 0
            self._budget_reset_date = today

    def _can_afford_solve(self, method: str) -> bool:
        """Check if budget allows another solve.

        Args:
            method: CAPTCHA method/type name.

        Returns:
            True if budget has room.
        """
        self._check_and_reset_daily_budget()
        cost = self._cost_per_solve.get(method, 0.003)
        if self._daily_spend + cost > self.daily_budget:
            logger.warning(
                "Daily captcha budget exhausted "
                "($%.4f/$%.2f)",
                self._daily_spend,
                self.daily_budget,
            )
            return False
        return True

    def can_afford_captcha(
        self, captcha_type: str
    ) -> bool:
        """Check if budget allows this CAPTCHA solve.

        Args:
            captcha_type: Type of captcha.

        Returns:
            True if the solve is within budget.
        """
        self._check_and_reset_daily_budget()
        cost = self._cost_per_solve.get(
            captcha_type, 0.003
        )
        remaining = (
            self.daily_budget - self._daily_spend
        )
        if cost > remaining:
            logger.warning(
                "Cannot afford %s solve ($%.4f). "
                "Remaining: $%.4f",
                captcha_type,
                cost,
                remaining,
            )
            return False
        if remaining < 0.50:
            logger.warning(
                "Low budget: $%.4f remaining.",
                remaining,
            )
            return remaining >= cost
        return True

    def _record_solve(
        self, method: str, success: bool
    ) -> None:
        """Record a solve attempt for budget tracking.

        Args:
            method: CAPTCHA method/type name.
            success: Whether the solve succeeded.
        """
        cost = (
            self._cost_per_solve.get(method, 0.003)
            if success
            else 0
        )
        self._daily_spend += cost
        self._solve_count_today += 1
        if success:
            logger.debug(
                "Captcha cost: $%.4f "
                "(Today: $%.4f, Solves: %d)",
                cost,
                self._daily_spend,
                self._solve_count_today,
            )
            try:
                from core.analytics import get_tracker
                get_tracker().record_cost(
                    "captcha",
                    cost,
                    faucet=self.faucet_name,
                )
            except Exception as e:
                logger.debug(
                    "Captcha cost tracking failed: %s",
                    e,
                )

    def get_budget_stats(self) -> Dict[str, Any]:
        """Return current daily budget statistics.

        Returns:
            Dictionary with budget info.
        """
        self._check_and_reset_daily_budget()
        return {
            "daily_budget": self.daily_budget,
            "spent_today": self._daily_spend,
            "remaining": (
                self.daily_budget - self._daily_spend
            ),
            "solves_today": self._solve_count_today,
            "date": self._budget_reset_date,
        }

    def get_provider_stats(self) -> Dict[str, Any]:
        """Return statistics for all providers.

        Returns:
            Dictionary with provider stats.
        """
        return {
            "providers": self.provider_stats.copy(),
            "primary": self.provider,
            "fallback": self.fallback_provider,
        }

    def _parse_proxy(
        self, proxy_url: str
    ) -> Dict[str, str]:
        """Parse proxy URL into 2Captcha API components.

        Args:
            proxy_url: Full proxy URL.

        Returns:
            Dict with proxytype and proxy string.
        """
        if "://" not in proxy_url:
            test_url = f"http://{proxy_url}"
        else:
            test_url = proxy_url
        parsed = urlparse(test_url)
        proxy_type = (
            "SOCKS5"
            if "socks" in parsed.scheme.lower()
            else "HTTP"
        )
        if parsed.username and parsed.password:
            proxy_str = (
                f"{parsed.username}:{parsed.password}"
                f"@{parsed.hostname}:{parsed.port}"
            )
        else:
            proxy_str = (
                f"{parsed.hostname}:{parsed.port}"
            )
        return {
            "proxytype": proxy_type,
            "proxy": proxy_str,
        }

    async def _get_session(
        self,
    ) -> aiohttp.ClientSession:
        """Return the shared aiohttp session.

        Returns:
            An open ClientSession.
        """
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def __aenter__(self) -> "CaptchaSolver":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        """Async context manager exit with cleanup."""
        await self.close()
        return False

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    # ----- Provider fallback logic -----

    async def solve_with_fallback(
        self,
        page: Any,
        captcha_type: str,
        sitekey: str,
        url: str,
        proxy_context: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Optional[str]:
        """Try primary then fallback provider with retry.

        Args:
            page: Playwright page instance.
            captcha_type: CAPTCHA type string.
            sitekey: Site key for the CAPTCHA.
            url: Page URL.
            proxy_context: Optional proxy config dict.

        Returns:
            Solution token or None.
        """
        providers_tried: List[str] = []
        provider_order = self._choose_provider_order(
            captcha_type
        )

        for provider in provider_order:
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    if attempt == 0:
                        logger.info(
                            "Trying provider: %s",
                            provider,
                        )
                    else:
                        logger.info(
                            "Retry %d/%d for: %s",
                            attempt,
                            max_retries - 1,
                            provider,
                        )
                    logger.info(
                        "[LIFECYCLE] captcha_solve_start"
                        " | type=%s | provider=%s"
                        " | attempt=%d"
                        " | timestamp=%.0f",
                        captcha_type,
                        provider,
                        attempt + 1,
                        time.time(),
                    )
                    start_time = time.time()
                    if attempt == 0:
                        providers_tried.append(provider)

                    api_key = self.api_key
                    if provider == self.fallback_provider:
                        api_key = self.fallback_api_key

                    if provider == "capsolver":
                        code = (
                            await self._solve_capsolver(
                                sitekey,
                                url,
                                captcha_type,
                                proxy_context,
                                api_key=api_key,
                            )
                        )
                    else:
                        code = (
                            await self._solve_2captcha(
                                sitekey,
                                url,
                                captcha_type,
                                proxy_context,
                                api_key=api_key,
                            )
                        )

                    dur = time.time() - start_time
                    if code:
                        logger.info(
                            "%s succeeded",
                            provider.title(),
                        )
                        logger.info(
                            "[LIFECYCLE] captcha_solve"
                            " | type=%s"
                            " | provider=%s"
                            " | duration=%.1fs"
                            " | success=true"
                            " | timestamp=%.0f",
                            captcha_type,
                            provider,
                            dur,
                            time.time(),
                        )
                        self._record_provider_result(
                            provider,
                            captcha_type,
                            success=True,
                        )
                        return code

                    if attempt < max_retries - 1:
                        logger.warning(
                            "%s timed out, retrying...",
                            provider.title(),
                        )
                        await asyncio.sleep(2)
                        continue

                    logger.warning(
                        "%s failed after %d attempts",
                        provider.title(),
                        max_retries,
                    )
                    logger.warning(
                        "[LIFECYCLE] captcha_solve"
                        " | type=%s"
                        " | provider=%s"
                        " | duration=%.1fs"
                        " | success=false"
                        " | timestamp=%.0f",
                        captcha_type,
                        provider,
                        dur,
                        time.time(),
                    )
                    self._record_provider_result(
                        provider,
                        captcha_type,
                        success=False,
                    )
                    break

                except Exception as e:
                    dur = (
                        time.time() - start_time
                        if "start_time" in locals()
                        else 0
                    )
                    error_msg = str(e)
                    logger.error(
                        "%s error: %s",
                        provider.title(),
                        e,
                    )
                    logger.error(
                        "[LIFECYCLE] captcha_solve"
                        " | type=%s"
                        " | provider=%s"
                        " | duration=%.1fs"
                        " | success=false"
                        " | error=%s"
                        " | timestamp=%.0f",
                        captcha_type,
                        provider,
                        dur,
                        error_msg[:50],
                        time.time(),
                    )
                    self._record_provider_result(
                        provider,
                        captcha_type,
                        success=False,
                    )
                    fallback_errs = [
                        "NO_SLOT",
                        "ZERO_BALANCE",
                        "ERROR_METHOD_CALL",
                        "METHOD_CALL",
                    ]
                    if not any(
                        err in error_msg.upper()
                        for err in fallback_errs
                    ):
                        raise
                    break

        logger.error(
            "All captcha providers failed. Tried: %s",
            ", ".join(providers_tried),
        )
        return None

    # ----- Main entry point -----

    async def solve_captcha(
        self,
        page: Any,
        timeout: int = 300,
        proxy_context: Optional[
            Dict[str, Any]
        ] = None,
    ) -> bool:
        """Detect and solve the CAPTCHA on a page.

        Args:
            page: The Playwright Page instance.
            timeout: Max seconds for manual solve.
            proxy_context: Optional proxy details.

        Returns:
            True if the CAPTCHA was solved.
        """
        if not self.api_key and self.headless:
            logger.error(
                "CAPTCHA detected but no API key "
                "in headless mode."
            )
            return False

        sitekey: Optional[str] = None
        method: Optional[str] = None
        turnstile_input_only = False

        try:
            await page.wait_for_selector(
                "iframe[src*='turnstile'], "
                "iframe[src*='challenges."
                "cloudflare.com'], "
                ".cf-turnstile, [data-sitekey], "
                "iframe[src*='hcaptcha'], "
                "iframe[src*='recaptcha'], "
                "input[name="
                "'cf-turnstile-response'], "
                "textarea[name="
                "'cf-turnstile-response']",
                timeout=6000,
            )
        except Exception:
            pass

        # Turnstile iframe detection
        for frame in page.frames:
            frame_url = frame.url or ""
            if (
                "turnstile" in frame_url
                or "challenges.cloudflare.com"
                in frame_url
            ):
                if "sitekey=" in frame_url:
                    method = "turnstile"
                    sitekey = (
                        frame_url
                        .split("sitekey=")[1]
                        .split("&")[0]
                    )
                    break
                if "k=" in frame_url:
                    method = "turnstile"
                    sitekey = (
                        frame_url
                        .split("k=")[1]
                        .split("&")[0]
                    )
                    break

        # Turnstile input-only detection
        if not method:
            ti = await page.query_selector(
                "input[name="
                "'cf-turnstile-response'], "
                "textarea[name="
                "'cf-turnstile-response']"
            )
            if ti:
                method = "turnstile"
                turnstile_input_only = True
                try:
                    sitekey = await page.evaluate(
                        """
                        () => {
                            const input = document.querySelector('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
                            if (!input) return null;
                            const inputId = input.id || '';
                            const widgetId = inputId.replace(/_response$/, '');
                            if (widgetId) {
                                const widget = document.getElementById(widgetId);
                                if (widget) {
                                    const dk = widget.getAttribute('data-sitekey') || (widget.dataset ? widget.dataset.sitekey : null);
                                    if (dk) return dk;
                                }
                            }
                            const elem = document.querySelector('.cf-turnstile[data-sitekey], [data-sitekey][class*="turnstile"]');
                            if (elem) return elem.getAttribute('data-sitekey');
                            if (typeof turnstile !== 'undefined' && turnstile._render_parameters && turnstile._render_parameters.sitekey) {
                                return turnstile._render_parameters.sitekey;
                            }
                            if (window.___cf_turnstile_cfg) {
                                const cfg = window.___cf_turnstile_cfg;
                                const values = Object.values(cfg || {});
                                for (const v of values) {
                                    if (v && v.sitekey) return v.sitekey;
                                }
                            }
                            return null;
                        }
                        """
                    )
                except Exception:
                    sitekey = None

        # Turnstile DOM fallback
        if not method:
            te = await page.query_selector(
                ".cf-turnstile, "
                ".cf-turnstile[data-sitekey], "
                "[data-sitekey]"
                "[class*='turnstile'], "
                "iframe[src*='turnstile'], "
                "iframe[src*='challenges."
                "cloudflare.com'], "
                "[id*='cf-turnstile']"
            )
            if te:
                method = "turnstile"
                turnstile_input_only = False
                sitekey = await te.get_attribute(
                    "data-sitekey"
                )
                if not sitekey:
                    src = await te.get_attribute("src")
                    if src and "sitekey=" in src:
                        sitekey = (
                            src.split("sitekey=")[1]
                            .split("&")[0]
                        )
                if not sitekey:
                    sitekey = await page.evaluate(
                        "() => typeof turnstile "
                        "!== 'undefined' "
                        "? (turnstile"
                        "._render_parameters "
                        "|| {}).sitekey : null"
                    )

        # hCaptcha
        if not method:
            he = await page.query_selector(
                "iframe[src*='hcaptcha']"
            )
            if he:
                method = "hcaptcha"
                src = await he.get_attribute("src")
                if src and "sitekey=" in src:
                    sitekey = (
                        src.split("sitekey=")[1]
                        .split("&")[0]
                    )

        # reCAPTCHA
        if not method:
            rce = await page.query_selector(
                "iframe[src*='recaptcha']"
            )
            if rce:
                method = "userrecaptcha"
                src = await rce.get_attribute("src")
                if src and "k=" in src:
                    sitekey = (
                        src.split("k=")[1]
                        .split("&")[0]
                    )

        # HTML fallback
        if not method:
            try:
                html = await page.content()
                for pat in [
                    r'data-sitekey='
                    r'"([0-9A-Za-z_-]{20,})"',
                    r"data-sitekey="
                    r"'([0-9A-Za-z_-]{20,})'",
                    r"sitekey="
                    r"([0-9A-Za-z_-]{20,})",
                ]:
                    m = re.search(pat, html)
                    if m:
                        method = "turnstile"
                        sitekey = m.group(1)
                        break
            except Exception:
                pass

        # ALTCHA
        if not method:
            aw = await page.query_selector(
                "altcha-widget, "
                "[data-altcha], .altcha"
            )
            if aw:
                method = "altcha"
                logger.info(
                    "ALTCHA proof-of-work detected."
                )

        # Image captcha
        if not method:
            ic = await page.query_selector(
                "img[src*='captcha'], "
                "div.captcha-img, "
                ".adcopy-puzzle-image"
            )
            if ic:
                method = "image"
                logger.info(
                    "Custom Image Captcha detected."
                )

        # Normalize sitekey
        sitekey = self._normalize_sitekey(sitekey)

        if not method or not sitekey:
            sitekey = (
                await self._extract_sitekey_from_scripts(
                    page, method or "any"
                )
            )
            if (
                sitekey is not None
                and not isinstance(sitekey, str)
            ):
                try:
                    sitekey = str(sitekey)
                except Exception:
                    sitekey = None
            sitekey = self._normalize_sitekey(sitekey)

            if not sitekey:
                if (
                    method == "turnstile"
                    and turnstile_input_only
                ):
                    logger.info(
                        "Turnstile input without "
                        "sitekey; skipping."
                    )
                    return True
                has_frames = await page.query_selector(
                    "iframe[src*='hcaptcha'], "
                    "iframe[src*='recaptcha'], "
                    ".cf-turnstile, "
                    "[id*='cf-turnstile'], "
                    "[data-sitekey]"
                )
                if not has_frames:
                    return True
                if self.headless:
                    logger.error(
                        "Captcha detected but "
                        "sitekey not found "
                        "in headless mode."
                    )
                    return False
                logger.warning(
                    "Captcha detected but sitekey "
                    "not found. Manual fallback."
                )
            else:
                if not method:
                    if (
                        len(sitekey) == 40
                        and "-" in sitekey
                    ):
                        method = "hcaptcha"
                    elif len(sitekey) == 40:
                        method = "userrecaptcha"
                    else:
                        method = "turnstile"
                logger.info(
                    "CAPTCHA via Script: %s "
                    "(SiteKey: %s...)",
                    method,
                    sitekey[:10],
                )
        elif method != "image":
            sk = sitekey[:10] if sitekey else "N/A"
            logger.info(
                "CAPTCHA Detected: %s "
                "(SiteKey: %s...)",
                method,
                sk,
            )
        else:
            logger.info(
                "CAPTCHA Detected: Image "
                "(Coordinates based)"
            )

        if method == "altcha":
            return await self._solve_altcha(page)

        auto_ok = False
        if self.api_key and method:
            auto_ok = self.can_afford_captcha(method)
            if not auto_ok:
                logger.warning(
                    "Budget exceeded. "
                    "Attempting manual..."
                )

        if self.api_key and auto_ok:
            try:
                if method == "image":
                    return (
                        await self._solve_image_captcha(
                            page
                        )
                    )

                if sitekey:
                    if not proxy_context:
                        proxy_context = {}
                    if (
                        "proxy_string"
                        not in proxy_context
                        and self.proxy_string
                    ):
                        proxy_context[
                            "proxy_string"
                        ] = self.proxy_string
                        proxy_context[
                            "proxy_type"
                        ] = "http"
                        logger.debug(
                            "Auto proxy: %s...",
                            self.proxy_string[:30],
                        )
                    if (
                        "user_agent"
                        not in proxy_context
                    ):
                        try:
                            ua = await page.evaluate(
                                "() => "
                                "navigator.userAgent"
                            )
                            proxy_context[
                                "user_agent"
                            ] = ua
                            logger.debug(
                                "User-Agent: %s...",
                                ua[:50],
                            )
                        except Exception as e:
                            logger.warning(
                                "UA extract "
                                "failed: %s",
                                e,
                            )

                    code = (
                        await self.solve_with_fallback(
                            page,
                            method,
                            sitekey,
                            page.url,
                            proxy_context,
                        )
                    )

                    if code:
                        logger.info(
                            "Captcha Solved! "
                            "Injecting token..."
                        )
                        await self._inject_token(
                            page, method, code
                        )
                        self._record_solve(
                            method, True
                        )
                        return True
                    else:
                        logger.error(
                            "All captcha providers "
                            "failed"
                        )
            except Exception as e:
                logger.error(
                    "Captcha solving error: %s", e
                )

        high_value = False
        if self.faucet_name:
            hv_faucets = [
                "firefaucet",
                "freebitcoin",
                "cointiply",
            ]
            high_value = any(
                hv in self.faucet_name.lower()
                for hv in hv_faucets
            )

        return await self._wait_for_human(
            page,
            timeout,
            high_value_claim=high_value,
        )

    # ----- Helpers -----

    @staticmethod
    def _normalize_sitekey(
        sitekey: Optional[Any],
    ) -> Optional[str]:
        """Validate and normalise a raw sitekey value.

        Args:
            sitekey: Raw sitekey value.

        Returns:
            Cleaned sitekey string or None.
        """
        if sitekey is None:
            return None
        if not isinstance(sitekey, str):
            try:
                if (
                    isinstance(sitekey, dict)
                    and sitekey.get("sitekey")
                ):
                    sitekey = sitekey.get("sitekey")
                else:
                    sitekey = str(sitekey)
            except Exception:
                return None
        sitekey = sitekey.strip()
        if any(
            c in sitekey
            for c in ["{", "}", ",", ":"]
        ):
            m = re.search(
                r"[0-9A-Za-z_-]{20,}", sitekey
            )
            if m:
                sitekey = m.group(0)
        if not re.fullmatch(
            r"[0-9A-Za-z_-]{20,}", sitekey
        ):
            logger.debug(
                "Invalid sitekey format: %s",
                sitekey[:20],
            )
            return None
        if len(sitekey) < 10:
            return None
        return sitekey

    # ----- Solver backends -----

    async def _solve_image_captcha(
        self, page: Any
    ) -> bool:
        """Solve image CAPTCHA via 2Captcha coordinates.

        Args:
            page: The Playwright Page instance.

        Returns:
            True if solved, False otherwise.
        """
        if not self.api_key:
            logger.warning(
                "No API key for image captcha."
            )
            return await self._wait_for_human(
                page, 120
            )

        try:
            ce = await page.query_selector(
                "img[src*='captcha'], "
                "div.captcha-img img, "
                ".adcopy-puzzle-image, "
                "#captcha-image, "
                ".captcha-image, "
                "[class*='captcha'] img"
            )
            if not ce:
                logger.warning(
                    "Could not find captcha image"
                )
                return await self._wait_for_human(
                    page, 120
                )

            box = await ce.bounding_box()
            if not box:
                logger.warning(
                    "Could not get bounding box"
                )
                return await self._wait_for_human(
                    page, 120
                )

            ss_bytes = await ce.screenshot()
            ss_b64 = base64.b64encode(
                ss_bytes
            ).decode("utf-8")

            logger.info(
                "Captured captcha (%d bytes), "
                "sending to 2Captcha...",
                len(ss_bytes),
            )

            session = await self._get_session()
            params: Dict[str, Any] = {
                "key": self.api_key,
                "method": "base64",
                "coordinatescaptcha": 1,
                "body": ss_b64,
                "json": 1,
            }

            async with session.post(
                "http://2captcha.com/in.php",
                data=params,
            ) as resp:
                data = await resp.json()
                if data.get("status") != 1:
                    logger.error(
                        "2Captcha Image Error: %s",
                        data,
                    )
                    return (
                        await self._wait_for_human(
                            page, 120
                        )
                    )
                req_id = data["request"]

            logger.info(
                "Waiting for coords (ID: %s)...",
                req_id,
            )
            waited = 0
            coordinates = None
            while waited < 120:
                await asyncio.sleep(5)
                waited += 5
                poll = (
                    "http://2captcha.com/res.php"
                    f"?key={self.api_key}"
                    f"&action=get"
                    f"&id={req_id}&json=1"
                )
                async with session.get(
                    poll
                ) as resp:
                    try:
                        data = await resp.json()
                    except Exception:
                        continue
                    if data.get("status") == 1:
                        coordinates = (
                            data["request"]
                        )
                        break
                    if (
                        data.get("request")
                        != "CAPCHA_NOT_READY"
                    ):
                        logger.error(
                            "2Captcha Poll Error: "
                            "%s", data
                        )
                        return (
                            await
                            self._wait_for_human(
                                page, 120
                            )
                        )

            if not coordinates:
                logger.error(
                    "Timeout waiting for coords"
                )
                return await self._wait_for_human(
                    page, 120
                )

            logger.info(
                "Got coordinates: %s", coordinates
            )
            click_points = self._parse_coordinates(
                coordinates
            )

            for x, y in click_points:
                px = (
                    box["x"]
                    + x
                    + random.uniform(-2, 2)
                )
                py = (
                    box["y"]
                    + y
                    + random.uniform(-2, 2)
                )
                logger.info(
                    "Clicking (%.0f, %.0f)",
                    px, py,
                )
                await page.mouse.click(px, py)
                await asyncio.sleep(
                    random.uniform(0.3, 0.8)
                )

            await asyncio.sleep(1)
            sb = await page.query_selector(
                "button[type='submit'], "
                "input[type='submit'], "
                ".captcha-submit, "
                "#captcha-submit, "
                "[class*='submit']"
            )
            if sb:
                await sb.click()
                logger.info("Clicked submit")

            await asyncio.sleep(2)
            self._record_solve("image", True)
            return True

        except Exception as e:
            logger.error(
                "Error solving image captcha: %s", e
            )
            return await self._wait_for_human(
                page, 120
            )

    @staticmethod
    def _parse_coordinates(
        coordinates: str,
    ) -> List[tuple]:
        """Parse 2Captcha coordinate response.

        Args:
            coordinates: Raw coordinate string.

        Returns:
            List of (x, y) integer tuples.
        """
        pts: List[tuple] = []
        if "x=" in coordinates:
            for point in coordinates.split(";"):
                parts = dict(
                    p.split("=")
                    for p in point.split(",")
                )
                pts.append(
                    (
                        int(parts["x"]),
                        int(parts["y"]),
                    )
                )
        else:
            parts = coordinates.split(",")
            if len(parts) >= 2:
                pts.append(
                    (int(parts[0]), int(parts[1]))
                )
        return pts

    async def _solve_altcha(
        self, page: Any
    ) -> bool:
        """Solve ALTCHA proof-of-work locally (free).

        Args:
            page: The Playwright Page instance.

        Returns:
            True if the PoW was solved successfully.
        """
        try:
            logger.info(
                "Solving ALTCHA proof-of-work..."
            )

            solved = await page.evaluate(r"""
                async () => {
                    const widget = document.querySelector('altcha-widget, [data-altcha], .altcha');
                    if (!widget) return {ok: false, error: 'widget not found'};

                    let challengeUrl = widget.getAttribute('challengeurl') ||
                                         widget.getAttribute('data-challengeurl') ||
                                         widget.getAttribute('challengeURL');
                    if (!challengeUrl) {
                        const scripts = document.querySelectorAll('script');
                        for (const s of scripts) {
                            const m = s.textContent.match(/challengeurl["\s:=]+["']([^"']+)["']/i);
                            if (m) { challengeUrl = m[1]; break; }
                        }
                    }
                    if (!challengeUrl) return {ok: false, error: 'challengeurl not found'};

                    let challenge;
                    try {
                        const resp = await fetch(challengeUrl);
                        challenge = await resp.json();
                    } catch(e) {
                        return {ok: false, error: 'fetch challenge failed: ' + e.message};
                    }

                    const {algorithm, salt, maxnumber} = challenge;
                    const targetHash = challenge.challenge;
                    const max = maxnumber || 1000000;

                    const encoder = new TextEncoder();
                    for (let n = 0; n <= max; n++) {
                        const data = encoder.encode(salt + n.toString());
                        const hashBuf = await crypto.subtle.digest('SHA-256', data);
                        const hashHex = Array.from(new Uint8Array(hashBuf))
                            .map(b => b.toString(16).padStart(2, '0')).join('');
                        if (hashHex === targetHash) {
                            const payload = btoa(JSON.stringify({
                                algorithm: algorithm || 'SHA-256',
                                challenge: targetHash,
                                number: n,
                                salt: salt,
                                signature: challenge.signature || ''
                            }));

                            const input = widget.querySelector('input[name="altcha"]') ||
                                          document.querySelector('input[name="altcha"]');
                            if (input) {
                                input.value = payload;
                                input.dispatchEvent(new Event('change', {bubbles: true}));
                                input.dispatchEvent(new Event('input', {bubbles: true}));
                            }

                            try {
                                widget.dispatchEvent(new CustomEvent('statechange', {
                                    detail: {state: 'verified', payload: payload}
                                }));
                            } catch(e) {}

                            if (typeof widget.value !== 'undefined') {
                                widget.value = payload;
                            }

                            return {ok: true, number: n, iterations: n + 1};
                        }
                    }
                    return {ok: false, error: 'solution not found within ' + max + ' iterations'};
                }
            """)

            if solved and solved.get("ok"):
                logger.info(
                    "ALTCHA solved in %s iterations "
                    "(free)",
                    solved.get("iterations", "?"),
                )
                self._record_solve("altcha", True)
                return True
            else:
                error = (
                    solved.get("error", "unknown")
                    if solved
                    else "evaluation failed"
                )
                logger.error(
                    "ALTCHA solve failed: %s", error
                )
                return False

        except Exception as e:
            logger.error(
                "Error solving ALTCHA: %s", e
            )
            return False

    async def solve_text_captcha(
        self,
        page: Any,
        image_selector: str,
        timeout: int = 120,
    ) -> Optional[str]:
        """Solve text-based CAPTCHA via 2Captcha OCR.

        Args:
            page: The Playwright Page instance.
            image_selector: CSS selector for CAPTCHA image.
            timeout: Max seconds to wait.

        Returns:
            Recognised text or None.
        """
        if not self.api_key:
            logger.warning(
                "No API key for text captcha."
            )
            await self._wait_for_human(page, timeout)
            return None

        try:
            ce = await page.query_selector(
                image_selector
            )
            if not ce:
                logger.warning(
                    "Could not find text captcha image"
                )
                return None

            box = await ce.bounding_box()
            if not box:
                logger.warning(
                    "Could not get bounding box"
                )
                return None

            ss = await ce.screenshot()
            b64 = base64.b64encode(ss).decode(
                "utf-8"
            )

            session = await self._get_session()
            params: Dict[str, Any] = {
                "key": self.api_key,
                "method": "base64",
                "body": b64,
                "json": 1,
            }

            async with session.post(
                "http://2captcha.com/in.php",
                data=params,
            ) as resp:
                data = await resp.json()
                if data.get("status") != 1:
                    logger.error(
                        "2Captcha Text Error: %s",
                        data,
                    )
                    return None
                req_id = data["request"]

            waited = 0
            while waited < timeout:
                await asyncio.sleep(5)
                waited += 5
                poll = (
                    "http://2captcha.com/res.php"
                    f"?key={self.api_key}"
                    f"&action=get"
                    f"&id={req_id}&json=1"
                )
                async with session.get(
                    poll
                ) as resp:
                    try:
                        data = await resp.json()
                    except Exception:
                        continue
                if data.get("status") == 1:
                    text = data.get("request")
                    if text:
                        logger.info(
                            "Text captcha solved"
                        )
                        return text.strip()
                if (
                    data.get("request")
                    != "CAPCHA_NOT_READY"
                ):
                    logger.error(
                        "2Captcha Text Poll "
                        "Error: %s", data
                    )
                    return None

        except Exception as e:
            logger.error(
                "Error solving text captcha: %s", e
            )
            return None

        return None

    async def _solve_2captcha(
        self,
        sitekey: str,
        url: str,
        method: str,
        proxy_context: Optional[
            Dict[str, Any]
        ] = None,
        api_key: Optional[str] = None,
    ) -> Optional[str]:
        """Submit CAPTCHA to 2Captcha and poll for solution.

        Args:
            sitekey: CAPTCHA site key.
            url: Page URL.
            method: CAPTCHA method string.
            proxy_context: Optional proxy config.
            api_key: Override API key.

        Returns:
            Solution token or None.

        Raises:
            Exception: For fallback-worthy errors.
        """
        # Use the newer createTask API for hCaptcha
        # (the legacy in.php method=hcaptcha returns
        # ERROR_METHOD_CALL)
        if method == "hcaptcha":
            return await self._solve_2captcha_task_api(
                sitekey, url, method,
                proxy_context, api_key,
            )

        session = await self._get_session()
        api_key = api_key or self.api_key

        req_url = "http://2captcha.com/in.php"
        params: Dict[str, Any] = {
            "key": api_key,
            "method": method,
            "pageurl": url,
            "json": 1,
        }

        if method == "userrecaptcha":
            params["googlekey"] = sitekey
        else:
            params["sitekey"] = sitekey

        proxy_str = None
        if (
            proxy_context
            and proxy_context.get("proxy_string")
        ):
            raw = proxy_context["proxy_string"]
            pi = self._parse_proxy(raw)
            proxy_str = pi["proxy"]
            params["proxytype"] = pi["proxytype"]
            logger.info(
                "Using Proxy for 2Captcha (%s): "
                "%s...",
                pi["proxytype"],
                proxy_str[:40],
            )
        elif self.proxy_string:
            pi = self._parse_proxy(self.proxy_string)
            proxy_str = pi["proxy"]
            params["proxytype"] = pi["proxytype"]
            logger.info(
                "Using Proxy for 2Captcha (%s): "
                "%s...",
                pi["proxytype"],
                proxy_str[:30],
            )

        if proxy_str:
            params["proxy"] = proxy_str

        if (
            proxy_context
            and "user_agent" in proxy_context
        ):
            params["userAgent"] = (
                proxy_context["user_agent"]
            )
            logger.debug(
                "Sending UA to 2Captcha: %s...",
                params["userAgent"][:50],
            )

        logger.info(
            "Submitting %s to 2Captcha "
            "(sitekey: %s...)...",
            method,
            sitekey[:20],
        )
        async with session.post(
            req_url, data=params
        ) as resp:
            try:
                data = await resp.json()
            except Exception as e:
                logger.error(
                    "2Captcha Invalid JSON: %s (%s)",
                    resp.status,
                    e,
                )
                return None

            if data.get("status") != 1:
                ec = data.get(
                    "request", "UNKNOWN_ERROR"
                )
                logger.error(
                    "2Captcha Submit Error: %s", ec
                )
                if ec == "ERROR_IP_NOT_ALLOWED":
                    logger.error(
                        "2Captcha: IP not "
                        "whitelisted."
                    )
                fb_codes = [
                    "ERROR_METHOD_CALL",
                    "ERROR_ZERO_BALANCE",
                    "ERROR_NO_SLOT_AVAILABLE",
                ]
                if ec in fb_codes:
                    raise Exception(
                        f"2Captcha Error: {ec}"
                    )
                return None

            request_id = data["request"]

        logger.info(
            "Waiting for solution (ID: %s)...",
            request_id,
        )
        waited = 0
        while waited < 120:
            await asyncio.sleep(5)
            waited += 5

            poll = (
                "http://2captcha.com/res.php"
                f"?key={api_key}&action=get"
                f"&id={request_id}&json=1"
            )
            async with session.get(poll) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    continue

                if waited % 10 == 0:
                    logger.info(
                        "Still waiting "
                        "(ID: %s, %ds)...",
                        request_id,
                        waited,
                    )

                if data.get("status") == 1:
                    return data["request"]

                ec = data.get("request")
                if ec == "CAPCHA_NOT_READY":
                    continue

                logger.error(
                    "2Captcha Error: %s", ec
                )
                if ec == "ERROR_IP_NOT_ALLOWED":
                    logger.error(
                        "IP NOT whitelisted in "
                        "2Captcha."
                    )
                elif ec == "ERROR_ZERO_BALANCE":
                    logger.error(
                        "2Captcha balance is ZERO!"
                    )

                fb_codes = [
                    "ERROR_METHOD_CALL",
                    "ERROR_ZERO_BALANCE",
                    "ERROR_NO_SLOT_AVAILABLE",
                ]
                if ec in fb_codes:
                    raise Exception(
                        f"2Captcha Error: {ec}"
                    )

                return None
        return None

    async def _solve_2captcha_task_api(
        self,
        sitekey: str,
        url: str,
        method: str,
        proxy_context: Optional[
            Dict[str, Any]
        ] = None,
        api_key: Optional[str] = None,
    ) -> Optional[str]:
        """Solve CAPTCHA via 2Captcha createTask API.

        Uses the newer JSON-based API which handles
        hCaptcha more reliably than the legacy in.php
        endpoint.

        Args:
            sitekey: CAPTCHA site key.
            url: Page URL.
            method: CAPTCHA method string.
            proxy_context: Optional proxy config.
            api_key: Override API key.

        Returns:
            Solution token or None.

        Raises:
            Exception: For fallback-worthy errors.
        """
        session = await self._get_session()
        api_key = api_key or self.api_key

        type_map = {
            "hcaptcha": "HCaptchaTaskProxyless",
            "turnstile": "TurnstileTaskProxyless",
            "userrecaptcha": "RecaptchaV2TaskProxyless",
        }
        type_map_proxy = {
            "hcaptcha": "HCaptchaTask",
            "turnstile": "TurnstileTask",
            "userrecaptcha": "RecaptchaV2Task",
        }

        use_proxy = bool(
            proxy_context
            and proxy_context.get("proxy_string")
        )

        task_type = (
            type_map_proxy.get(method, "HCaptchaTask")
            if use_proxy
            else type_map.get(
                method, "HCaptchaTaskProxyless"
            )
        )

        task: Dict[str, Any] = {
            "type": task_type,
            "websiteURL": url,
            "websiteKey": sitekey,
        }

        if use_proxy and proxy_context:
            raw = proxy_context["proxy_string"]
            if "://" not in raw:
                raw = f"http://{raw}"
            parsed = urlparse(raw)
            task["proxyType"] = (
                "socks5"
                if "socks" in parsed.scheme.lower()
                else "http"
            )
            task["proxyAddress"] = parsed.hostname
            task["proxyPort"] = parsed.port
            if parsed.username:
                task["proxyLogin"] = parsed.username
            if parsed.password:
                task["proxyPassword"] = (
                    parsed.password
                )
            logger.info(
                "Using proxy for 2Captcha Task API"
                " (%s): %s:%s",
                task["proxyType"],
                parsed.hostname,
                parsed.port,
            )

        if (
            proxy_context
            and "user_agent" in proxy_context
        ):
            task["userAgent"] = (
                proxy_context["user_agent"]
            )

        payload: Dict[str, Any] = {
            "clientKey": api_key,
            "task": task,
        }

        logger.info(
            "Submitting %s to 2Captcha Task API "
            "(sitekey: %s...)...",
            method,
            sitekey[:20],
        )

        try:
            async with session.post(
                "https://api.2captcha.com/createTask",
                json=payload,
            ) as resp:
                data = await resp.json()
                error_id = data.get("errorId", 0)
                if error_id != 0:
                    ec = data.get(
                        "errorCode", "UNKNOWN"
                    )
                    logger.error(
                        "2Captcha Task API Error: "
                        "%s - %s",
                        ec,
                        data.get(
                            "errorDescription", ""
                        ),
                    )
                    fb_codes = [
                        "ERROR_ZERO_BALANCE",
                        "ERROR_NO_SLOT_AVAILABLE",
                    ]
                    if ec in fb_codes:
                        raise Exception(
                            f"2Captcha Error: {ec}"
                        )
                    return None
                task_id = data.get("taskId")
                if not task_id:
                    logger.error(
                        "2Captcha Task API: "
                        "no taskId in response"
                    )
                    return None
        except aiohttp.ClientError as e:
            logger.error(
                "2Captcha Task API connection "
                "error: %s",
                e,
            )
            return None

        logger.info(
            "Waiting for solution (Task: %s)...",
            task_id,
        )

        result_payload: Dict[str, Any] = {
            "clientKey": api_key,
            "taskId": task_id,
        }
        waited = 0
        while waited < 120:
            await asyncio.sleep(
                POLL_INTERVAL_SECONDS
            )
            waited += POLL_INTERVAL_SECONDS

            try:
                async with session.post(
                    "https://api.2captcha.com"
                    "/getTaskResult",
                    json=result_payload,
                ) as resp:
                    data = await resp.json()
            except Exception:
                continue

            if waited % 10 == 0:
                logger.info(
                    "Still waiting "
                    "(Task: %s, %ds)...",
                    task_id,
                    waited,
                )

            status = data.get("status")
            if status == "ready":
                sol = data.get("solution", {})
                token = (
                    sol.get("gRecaptchaResponse")
                    or sol.get("token")
                )
                if not token:
                    logger.error(
                        "2Captcha Task ready but "
                        "no token: %s",
                        list(sol.keys()),
                    )
                    return None
                return token

            error_id = data.get("errorId", 0)
            if error_id != 0:
                ec = data.get(
                    "errorCode", "UNKNOWN"
                )
                logger.error(
                    "2Captcha Task Error: %s", ec
                )
                fb_codes = [
                    "ERROR_ZERO_BALANCE",
                    "ERROR_NO_SLOT_AVAILABLE",
                ]
                if ec in fb_codes:
                    raise Exception(
                        f"2Captcha Error: {ec}"
                    )
                return None

            if status != "processing":
                logger.warning(
                    "2Captcha unexpected status: "
                    "%s",
                    status,
                )

        logger.warning(
            "2Captcha Task API timed out "
            "after %ds",
            waited,
        )
        return None

    async def _solve_capsolver(
        self,
        sitekey: str,
        url: str,
        method: str,
        proxy_context: Optional[
            Dict[str, Any]
        ] = None,
        api_key: Optional[str] = None,
    ) -> Optional[str]:
        """Submit CAPTCHA to CapSolver and poll.

        Args:
            sitekey: CAPTCHA site key.
            url: Page URL.
            method: CAPTCHA method string.
            proxy_context: Optional proxy config.
            api_key: Override API key.

        Returns:
            Solution token or None.
        """
        session = await self._get_session()
        api_key = api_key or self.api_key

        use_proxy = bool(
            proxy_context
            and proxy_context.get("proxy_string")
        )

        type_map = {
            "turnstile": (
                "TurnstileTask"
                if use_proxy
                else "TurnstileTaskProxyLess"
            ),
            "hcaptcha": (
                "HCaptchaTask"
                if use_proxy
                else "HCaptchaTaskProxyLess"
            ),
        }
        task_type = type_map.get(
            method,
            (
                "ReCaptchaV2Task"
                if use_proxy
                else "ReCaptchaV2TaskProxyLess"
            ),
        )

        task: Dict[str, Any] = {
            "type": task_type,
            "websiteURL": url,
            "websiteKey": sitekey,
        }

        if use_proxy and proxy_context:
            task["proxy"] = (
                proxy_context["proxy_string"]
            )

        payload: Dict[str, Any] = {
            "clientKey": api_key,
            "task": task,
        }

        try:
            async with session.post(
                "https://api.capsolver.com"
                "/createTask",
                json=payload,
            ) as resp:
                data = await resp.json()
                if data.get("errorId") != 0:
                    logger.error(
                        "CapSolver Create Error: %s",
                        data,
                    )
                    return None
                task_id = data["taskId"]
        except Exception as e:
            logger.error(
                "CapSolver Connection Error: %s", e
            )
            return None

        logger.info(
            "CapSolver Task (%s) "
            "[Proxy: %s]. Polling...",
            task_id,
            use_proxy,
        )
        waited = 0
        result_payload: Dict[str, Any] = {
            "clientKey": api_key,
            "taskId": task_id,
        }
        while waited < 120:
            await asyncio.sleep(2)
            waited += 2

            async with session.post(
                "https://api.capsolver.com"
                "/getTaskResult",
                json=result_payload,
            ) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    continue

                if data.get("status") == "ready":
                    sol = data.get("solution", {})
                    token = (
                        sol.get("token")
                        or sol.get(
                            "gRecaptchaResponse"
                        )
                    )
                    if not token:
                        logger.error(
                            "CapSolver ready but "
                            "no token: %s",
                            list(sol.keys()),
                        )
                        return None
                    return token

                if data.get("status") == "failed":
                    logger.error(
                        "CapSolver Failed: %s",
                        data.get(
                            "errorDescription"
                        ),
                    )
                    return None

        return None

    async def _inject_token(
        self,
        page: Any,
        method: str,
        token: str,
    ) -> None:
        """Inject solver token into page fields.

        Args:
            page: The Playwright Page instance.
            method: CAPTCHA method string.
            token: The solution token.
        """
        await page.evaluate(f"""(token) => {{
            const setVal = (sel, val, ensure = false) => {{
                let el = document.querySelector(sel);
                if (!el && ensure) {{
                    el = document.createElement('input');
                    el.type = 'hidden';
                    el.name = sel.replace('[name="', '').replace('"]', '');
                    (document.querySelector('form') || document.body).appendChild(el);
                }}
                if (el) {{
                    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') el.value = val;
                    else el.innerHTML = val;
                }}
            }};

            if ("{method}" === "hcaptcha") {{
                setVal('[name="h-captcha-response"]', token);
                setVal('[name="g-recaptcha-response"]', token);
            }} else if ("{method}" === "userrecaptcha") {{
                setVal('#g-recaptcha-response', token);
                setVal('[name="g-recaptcha-response"]', token);
            }} else if ("{method}" === "turnstile") {{
                setVal('[name="cf-turnstile-response"]', token, true);
            }}

            const callbacks = ['onCaptchaSuccess', 'onhCaptchaSuccess', 'onTurnstileSuccess', 'recaptchaCallback', 'grecaptchaCallback', 'captchaCallback'];
            callbacks.forEach(cb => {{
                if (typeof window[cb] === 'function') {{
                    try {{ window[cb](token); }} catch(e) {{ console.error('Callback error:', e); }}
                }}
            }});

            ['h-captcha-response', 'g-recaptcha-response', 'cf-turnstile-response'].forEach(name => {{
                const el = document.querySelector(`[name="${{name}}"]`);
                if (el) {{
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }});
        }}""", token)

    async def _wait_for_human(
        self,
        page: Any,
        timeout: int,
        high_value_claim: bool = False,
    ) -> bool:
        """Wait for manual CAPTCHA solving.

        Args:
            page: The Playwright Page instance.
            timeout: Max seconds to wait.
            high_value_claim: If True, log urgency.

        Returns:
            True if token detected, False if timed out.
        """
        is_headless = (
            os.environ.get("HEADLESS", "false")
            .lower() == "true"
        )

        if is_headless:
            logger.error(
                "Headless mode. "
                "Skipping manual solve."
            )
            return False

        if high_value_claim:
            logger.warning(
                "BUDGET EXHAUSTED - HIGH VALUE CLAIM"
            )
            logger.warning(
                "Please solve CAPTCHA manually "
                "(timeout: %ds)",
                timeout,
            )
        else:
            logger.info(
                "PAUSED FOR MANUAL CAPTCHA SOLVE"
            )
            logger.info(
                "Solve captcha in browser "
                "within %d seconds.",
                timeout,
            )

        start_time = time.monotonic()

        while (time.monotonic() - start_time) < timeout:
            await asyncio.sleep(2)

            token = await page.evaluate("""() => {
                const h = document.querySelector('[name="h-captcha-response"]');
                const g = document.querySelector('[name="g-recaptcha-response"]');
                const cf = document.querySelector('[name="cf-turnstile-response"]');
                return (h && h.value) || (g && g.value) || (cf && cf.value);
            }""")

            if token:
                logger.info(
                    "Manual solve detected! "
                    "Resuming..."
                )
                return True

        logger.error("Manual solve timed out.")
        return False

    async def _extract_sitekey_from_scripts(
        self,
        page: Any,
        method: str,
    ) -> Optional[str]:
        """Scan page scripts and globals for sitekeys.

        Args:
            page: The Playwright Page instance.
            method: The detected CAPTCHA method.

        Returns:
            A sitekey string if found, or None.
        """
        return await page.evaluate("""() => {
            const patterns = [
                /sitekey["']\\s*:\\s*["']([^"']{20,})["']/i,
                /site-key["']\\s*:\\s*["']([^"']{20,})["']/i,
                /siteKey["']\\s*:\\s*["']([^"']{20,})["']/i,
                /key["']\\s*:\\s*["']([^"']{20,})["']/i,
                /render\\(.+?["']([^"']{20,})["']/i
            ];

            const dataSiteKeyElem = document.querySelector('[data-sitekey]');
            if (dataSiteKeyElem) {
                const dk = dataSiteKeyElem.getAttribute('data-sitekey');
                if (dk && dk.length > 20) return dk;
            }

            const globals = [
                 '___hcaptcha_sitekey_id', 'RECAPTCHA_SITE_KEY', 'H_SITE_KEY',
                 'hcaptcha_sitekey', 'captcha_sitekey', 'cf_sitekey'
            ];
            for (const g of globals) {
                if (window[g] && typeof window[g] === 'string' && window[g].length > 20) return window[g];
            }

            const scripts = Array.from(document.getElementsByTagName('script'));
            for (const script of scripts) {
                const content = script.textContent || script.innerHTML;
                if (!content) continue;

                for (const pattern of patterns) {
                    const match = content.match(pattern);
                    if (match && match[1] && match[1].length > 20) return match[1];
                }
            }

            if (typeof turnstile !== 'undefined' && turnstile._render_parameters) {
                 return turnstile._render_parameters.sitekey;
            }

            return null;
        }""")

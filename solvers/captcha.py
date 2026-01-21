import asyncio
import logging
import aiohttp
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Rate limiting constants per 2Captcha API best practices
INITIAL_POLL_DELAY_SECONDS = 5  # Wait 5s before first poll
POLL_INTERVAL_SECONDS = 5  # Retry every 5s
RECAPTCHA_INITIAL_DELAY = 15  # reCAPTCHA needs longer initial wait
ERROR_NO_SLOT_DELAY = 5  # Wait 5s if no slots available
ERROR_ZERO_BALANCE_DELAY = 60  # Wait 60s if balance is zero
MAX_POLL_ATTEMPTS = 24  # 24 * 5s = 2 minutes max wait
DEFAULT_DAILY_BUDGET_USD = 5.0  # Default daily budget limit


class CaptchaSolver:
    """
    Hybrid Solver: Defaults to 2Captcha if key exists, otherwise
    falls back to manual human solving (Human-in-the-Loop).
    
    Includes rate limiting per 2Captcha API best practices and
    daily budget tracking to prevent cost overruns.
    """

    def __init__(self, api_key: str = None, provider: str = "2captcha", daily_budget: float = DEFAULT_DAILY_BUDGET_USD):
        """
        Initialize the CaptchaSolver.

        Args:
            api_key: The API key for the captcha solving service.
            provider: The name of the captcha solving provider (default is "2captcha").
            daily_budget: Maximum daily spend in USD (default $5.00).
        """
        self.api_key = api_key
        self.provider = provider.lower().replace("twocaptcha", "2captcha")
        # Fallback support (optional secondary provider)
        self.fallback_provider = None
        self.fallback_api_key = None
        self.provider_stats = {self.provider: {"solves": 0, "failures": 0, "cost": 0.0}}
        self.session = None
        self.daily_budget = daily_budget
        self.faucet_name = None
        
        # Rate limiting state
        self.last_request_time = 0
        self.consecutive_errors = 0
        
        # Budget tracking
        self._daily_spend = 0.0
        self._budget_reset_date = time.strftime("%Y-%m-%d")
        self._solve_count_today = 0
        
        # Approximate costs per solve (2Captcha prices as of 2024)
        self._cost_per_solve = {
            "turnstile": 0.003,
            "hcaptcha": 0.003,
            "userrecaptcha": 0.003,
            "image": 0.001
        }
        
        if not self.api_key:
            logger.warning("⚠️ No CAPTCHA API key provided. Switching to MANUAL mode.")
            logger.warning("You must solve CAPTCHAs yourself in the browser window.")
            
        self.proxy_string = None  # Store proxy for sticky sessions

    def set_faucet_name(self, faucet_name: Optional[str]) -> None:
        """Associate this solver instance with a faucet for cost attribution."""
        self.faucet_name = faucet_name

    def set_proxy(self, proxy_string: str):
        """Set the proxy to be used for all 2Captcha requests."""
        self.proxy_string = proxy_string

        def set_fallback_provider(self, provider: str, api_key: str):
            """Set a fallback captcha provider in case primary fails."""
            self.fallback_provider = provider.lower().replace("twocaptcha", "2captcha")
            self.fallback_api_key = api_key
            logger.info(f"Fallback provider configured: {self.fallback_provider}")
            if self.fallback_provider not in self.provider_stats:
                self.provider_stats[self.fallback_provider] = {"solves": 0, "failures": 0, "cost": 0.0}

    def _check_and_reset_daily_budget(self):
        """Reset daily budget counter if new day."""
        today = time.strftime("%Y-%m-%d")
        if today != self._budget_reset_date:
            logger.info(f"📅 New day detected. Resetting captcha budget. Yesterday's spend: ${self._daily_spend:.4f}")
            self._daily_spend = 0.0
            self._solve_count_today = 0
            self._budget_reset_date = today

    def _can_afford_solve(self, method: str) -> bool:
        """Check if we can afford another solve within daily budget."""
        self._check_and_reset_daily_budget()
        cost = self._cost_per_solve.get(method, 0.003)
        if self._daily_spend + cost > self.daily_budget:
            logger.warning(f"💰 Daily captcha budget exhausted (${self._daily_spend:.4f}/${self.daily_budget:.2f})")
            return False
        return True

    def _record_solve(self, method: str, success: bool):
        """Record a solve attempt for budget tracking."""
        cost = self._cost_per_solve.get(method, 0.003) if success else 0
        self._daily_spend += cost
        self._solve_count_today += 1
        if success:
            logger.debug(f"💰 Captcha cost: ${cost:.4f} (Today: ${self._daily_spend:.4f}, Solves: {self._solve_count_today})")
            try:
                from core.analytics import get_tracker
                get_tracker().record_cost("captcha", cost, faucet=self.faucet_name)
            except Exception as e:
                logger.debug(f"Captcha cost tracking failed: {e}")

    def get_budget_stats(self) -> dict:
        """Get current budget statistics."""
        self._check_and_reset_daily_budget()
        return {
            "daily_budget": self.daily_budget,
            "spent_today": self._daily_spend,
            "remaining": self.daily_budget - self._daily_spend,
            "solves_today": self._solve_count_today,
            "date": self._budget_reset_date
        }

    def _parse_proxy(self, proxy_url: str) -> dict:
        """Parse proxy URL into components for 2Captcha API.
        
        Args:
            proxy_url: Full proxy URL (e.g., http://user:pass@host:port)
            
        Returns:
            Dict with proxytype and proxy (formatted for 2Captcha legacy API)
        """
        # Ensure we have a protocol for urlparse
        if "://" not in proxy_url:
            test_url = f"http://{proxy_url}"
        else:
            test_url = proxy_url
            
        from urllib.parse import urlparse
        parsed = urlparse(test_url)
        
        proxy_type = "SOCKS5" if "socks" in parsed.scheme.lower() else "HTTP"
        
        # 2Captcha legacy API wants: user:pass@host:port (no protocol)
        if parsed.username and parsed.password:
            proxy_string = f"{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port}"
        else:
            proxy_string = f"{parsed.hostname}:{parsed.port}"
        
        return {"proxytype": proxy_type, "proxy": proxy_string}

    async def _get_session(self):
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """Close the underlying aiohttp session."""
        if self.session:
            await self.session.close()

    async def solve_captcha(self, page, timeout: int = 300, proxy_context: dict = None) -> bool:
        """Detects and solves CAPTCHA.

        If an API key exists, it attempts to auto-solve using the configured
        provider (2Captcha or CapSolver). If no API key is provided or auto-solve
        fails, it pauses for manual user input.

        Args:
            page (Page): The Playwright Page instance.
            timeout (int, optional): Maximum time to wait for manual solve in seconds.
            proxy_context (dict, optional): Proxy details to pass to solver service.

        Returns:
            bool: True if the captcha was solved successfully.
        """
        # 1. Detection & Extraction
        sitekey = None
        method = None
        
        # Turnstile
        turnstile_elem = await page.query_selector(".cf-turnstile, iframe[src*='turnstile'], [id*='cf-turnstile']")
        if turnstile_elem:
            method = "turnstile"
            sitekey = await turnstile_elem.get_attribute("data-sitekey")
            if not sitekey:
                # Try to extract from iframe src
                src = await turnstile_elem.get_attribute("src")
                if src and "sitekey=" in src:
                    sitekey = src.split("sitekey=")[1].split("&")[0]
            
            # If still no sitekey, try searching in scripts
            if not sitekey:
                sitekey = await page.evaluate("() => typeof turnstile !== 'undefined' ? (turnstile._render_parameters || {}).sitekey : null")

        # hCaptcha
        if not method:
            hcaptcha_elem = await page.query_selector("iframe[src*='hcaptcha']")
            if hcaptcha_elem:
                method = "hcaptcha"
                # Often in the url params
                src = await hcaptcha_elem.get_attribute("src")
                if "sitekey=" in src:
                    sitekey = src.split("sitekey=")[1].split("&")[0]

        # reCaptcha
        if not method:
            recaptcha_elem = await page.query_selector("iframe[src*='recaptcha']")
            if recaptcha_elem:
                method = "userrecaptcha"
                src = await recaptcha_elem.get_attribute("src")
                if "k=" in src:
                    sitekey = src.split("k=")[1].split("&")[0]

        # Image Captcha Detection (Fragmented/Custom)
        if not method:
             # Check for image captchas that might need coordinates (e.g. Cointiply/Freebitco.in custom ones)
             image_captcha = await page.query_selector("img[src*='captcha'], div.captcha-img, .adcopy-puzzle-image")
             if image_captcha:
                 method = "image"
                 logger.info("Custom Image Captcha detected.")

        if not method or not sitekey:
            # 2. Search in Scripts & Global Variables if still missing sitekey
            sitekey = await self._extract_sitekey_from_scripts(page, method or "any")
            
            if not sitekey:
                # Check if any captcha frames exist at all as a last resort
                has_frames = await page.query_selector("iframe[src*='hcaptcha'], iframe[src*='recaptcha'], .cf-turnstile, [id*='cf-turnstile']")
                if not has_frames:
                    return True
                logger.warning("Captcha detected but Sitekey not found. Falling back to manual.")
            else:
                if not method:
                    # Infer method from sitekey characteristics
                    if len(sitekey) == 40 and "-" in sitekey: method = "hcaptcha"
                    elif len(sitekey) == 40: method = "userrecaptcha"
                    else: method = "turnstile"
                logger.info(f"CAPTCHA Detected via Script: {method} (SiteKey: {sitekey[:10]}...)")
        elif method != "image":
            logger.info(f"CAPTCHA Detected: {method} (SiteKey: {sitekey[:10] if sitekey else 'N/A'}...)")
        else:
            logger.info("CAPTCHA Detected: Image (Coordinates based)")

        # 2. Auto-Solve Path
        auto_solve_allowed = False
        if self.api_key and method:
            auto_solve_allowed = self._can_afford_solve(method)
            if not auto_solve_allowed:
                logger.warning("💰 Captcha budget exceeded. Falling back to manual solve.")

        if self.api_key and auto_solve_allowed:
            try:
                if method == "image":
                    return await self._solve_image_captcha(page)

                if sitekey:
                    if self.provider == "capsolver":
                        code = await self._solve_capsolver(sitekey, page.url, method, proxy_context)
                    else:
                        code = await self._solve_2captcha(sitekey, page.url, method, proxy_context)

                    
                    if code:
                        logger.info(f"✅ {self.provider.title()} Solved! Injecting token...")
                        await self._inject_token(page, method, code)
                        self._record_solve(method, True)
                        return True
                    else:
                        logger.error(f"❌ {self.provider.title()} failed to return a solution.")
            except Exception as e:
                logger.error(f"{self.provider.title()} Error: {e}")

        # 3. Manual Fallback Path
        return await self._wait_for_human(page, timeout)

    async def _solve_image_captcha(self, page) -> bool:
        """
        Handle image-based captchas using 2Captcha Coordinates API.
        
        This method captures a screenshot of the captcha image, sends it to 2Captcha,
        receives click coordinates, and simulates clicks at those positions.
        
        Args:
            page: The Playwright Page instance
            
        Returns:
            True if solved automatically or manually, False otherwise
        """
        if not self.api_key:
            logger.warning("⚠️ No API key for image captcha. Falling back to manual.")
            return await self._wait_for_human(page, 120)
        
        try:
            # Find the captcha image element
            captcha_element = await page.query_selector(
                "img[src*='captcha'], div.captcha-img img, .adcopy-puzzle-image, "
                "#captcha-image, .captcha-image, [class*='captcha'] img"
            )
            
            if not captcha_element:
                logger.warning("Could not find captcha image element")
                return await self._wait_for_human(page, 120)
            
            # Get bounding box for coordinate translation
            box = await captcha_element.bounding_box()
            if not box:
                logger.warning("Could not get captcha bounding box")
                return await self._wait_for_human(page, 120)
            
            # Capture screenshot of the captcha element
            import base64
            screenshot_bytes = await captcha_element.screenshot()
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            logger.info(f"📸 Captured captcha image ({len(screenshot_bytes)} bytes), sending to 2Captcha...")
            
            # Send to 2Captcha Coordinates API
            session = await self._get_session()
            submit_url = "http://2captcha.com/in.php"
            params = {
                "key": self.api_key,
                "method": "base64",
                "coordinatescaptcha": 1,
                "body": screenshot_b64,
                "json": 1
            }
            
            async with session.post(submit_url, data=params) as resp:
                data = await resp.json()
                if data.get('status') != 1:
                    logger.error(f"2Captcha Image Submit Error: {data}")
                    return await self._wait_for_human(page, 120)
                request_id = data['request']
            
            # Poll for result
            logger.info(f"⏳ Waiting for coordinates (ID: {request_id})...")
            waited = 0
            coordinates = None
            while waited < 120:
                await asyncio.sleep(5)
                waited += 5
                
                poll_url = f"http://2captcha.com/res.php?key={self.api_key}&action=get&id={request_id}&json=1"
                async with session.get(poll_url) as resp:
                    try:
                        data = await resp.json()
                    except Exception:
                        continue
                    
                    if data.get('status') == 1:
                        coordinates = data['request']
                        break
                    if data.get('request') != "CAPCHA_NOT_READY":
                        logger.error(f"2Captcha Poll Error: {data}")
                        return await self._wait_for_human(page, 120)
            
            if not coordinates:
                logger.error("Timeout waiting for coordinates")
                return await self._wait_for_human(page, 120)
            
            # Parse coordinates (format: "x=123,y=456;x=234,y=567" or "123,456")
            logger.info(f"✅ Got coordinates: {coordinates}")
            
            click_points = []
            if 'x=' in coordinates:
                # Format: x=123,y=456;x=234,y=567
                for point in coordinates.split(';'):
                    parts = dict(p.split('=') for p in point.split(','))
                    click_points.append((int(parts['x']), int(parts['y'])))
            else:
                # Simple format: 123,456
                parts = coordinates.split(',')
                if len(parts) >= 2:
                    click_points.append((int(parts[0]), int(parts[1])))
            
            # Click at each coordinate (relative to captcha element)
            import random
            for x, y in click_points:
                # Translate to page coordinates
                page_x = box['x'] + x + random.uniform(-2, 2)
                page_y = box['y'] + y + random.uniform(-2, 2)
                
                logger.info(f"🖱️ Clicking at ({page_x:.0f}, {page_y:.0f})")
                await page.mouse.click(page_x, page_y)
                await asyncio.sleep(random.uniform(0.3, 0.8))
            
            # Wait a moment for any submit button
            await asyncio.sleep(1)
            
            # Try to find and click submit button if present
            submit_btn = await page.query_selector(
                "button[type='submit'], input[type='submit'], "
                ".captcha-submit, #captcha-submit, [class*='submit']"
            )
            if submit_btn:
                await submit_btn.click()
                logger.info("📤 Clicked submit button")
            
            await asyncio.sleep(2)
            self._record_solve("image", True)
            return True
            
        except Exception as e:
            logger.error(f"Error solving image captcha: {e}")
            return await self._wait_for_human(page, 120)

    async def _solve_2captcha(self, sitekey, url, method, proxy_context=None):
        session = await self._get_session()
        
        # 1. Submit
        req_url = "http://2captcha.com/in.php"
        params = {
            "key": self.api_key,
            "method": method,
            "pageurl": url,
            "json": 1
        }
        
        # 2Captcha uses different parameter names for different captcha types
        # reCAPTCHA uses 'googlekey', hCaptcha uses 'sitekey', Turnstile uses 'sitekey'
        if method == "userrecaptcha":
            params["googlekey"] = sitekey
        else:
            params["sitekey"] = sitekey
        
        if proxy_context:
            params["proxy"] = proxy_context.get("proxy_string")
            params["proxytype"] = proxy_context.get("proxy_type", "HTTP")
            logger.info(f"🔒 Using Proxy for 2Captcha (Context): {params['proxy']}")
        elif self.proxy_string:
            proxy_info = self._parse_proxy(self.proxy_string)
            params["proxy"] = proxy_info["proxy"]
            params["proxytype"] = proxy_info["proxytype"]
            logger.info(f"🔒 Using Proxy for 2Captcha ({proxy_info['proxytype']}): {proxy_info['proxy'][:30]}...")
        
        logger.info(f"Submitting {method} to 2Captcha (sitekey: {sitekey[:20]}...)...")
        async with session.post(req_url, data=params) as resp:
            try:
                data = await resp.json()
            except Exception as e:
                logger.error(f"2Captcha Invalid JSON response: {resp.status} ({e})")
                return None
                
            if data.get('status') != 1:
                error_code = data.get('request', 'UNKNOWN_ERROR')
                logger.error(f"2Captcha Submit Error: {error_code}")
                if error_code == "ERROR_IP_NOT_ALLOWED":
                    logger.error("❌ 2Captcha: IP not whitelisted. Triggering whitelist update.")
                return None
                
            request_id = data['request']

        # 2. Poll
        logger.info(f"Waiting for solution (ID: {request_id})...")
        waited = 0
        while waited < 120:
            await asyncio.sleep(5)
            waited += 5
            
            poll_url = f"http://2captcha.com/res.php?key={self.api_key}&action=get&id={request_id}&json=1"
            async with session.get(poll_url) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    continue  # Retry on temporary network blips

                if waited % 10 == 0:
                    logger.info(f"⏳ Still waiting for 2Captcha solution (ID: {request_id}, Waited: {waited}s)...")

                if data.get('status') == 1:
                    return data['request']
                
                error_code = data.get('request')
                if error_code == "CAPCHA_NOT_READY":
                    continue
                
                logger.error(f"❌ 2Captcha Error: {error_code}")
                if error_code == "ERROR_IP_NOT_ALLOWED":
                    logger.error("🚫 Your IP is NOT whitelisted in 2Captcha. Please add it to the portal.")
                elif error_code == "ERROR_ZERO_BALANCE":
                    logger.error("💸 2Captcha balance is ZERO!")
                
                return None
        return None


    async def _solve_capsolver(self, sitekey, url, method, proxy_context=None):
        session = await self._get_session()
        
        # Determine Task Type (ProxyLess or Proxy)
        # CapSolver uses different task names for proxy vs proxyless
        # e.g., TurnstileTask vs TurnstileTaskProxyLess
        
        use_proxy = False
        if proxy_context:
            proxy_str = proxy_context.get("proxy_string")
            # CapSolver format: http://user:pass@host:port (socks5 also supported)
            if proxy_str:
                use_proxy = True
        
        if method == "turnstile":
            task_type = "TurnstileTask" if use_proxy else "TurnstileTaskProxyLess"
        elif method == "hcaptcha":
            task_type = "HCaptchaTask" if use_proxy else "HCaptchaTaskProxyLess"
        else:
             # ReCaptchaV2Task / ReCaptchaV2TaskProxyLess
            task_type = "ReCaptchaV2Task" if use_proxy else "ReCaptchaV2TaskProxyLess"
            
        task_payload = {
            "type": task_type,
            "websiteURL": url,
            "websiteKey": sitekey
        }
        
        if use_proxy:
             task_payload["proxy"] = proxy_context.get("proxy_string")
             # CapSolver might auto-detect type, but for safety:
             # task_payload["proxyType"] = proxy_context.get("proxy_type", "http").lower()

        payload = {
            "clientKey": self.api_key,
            "task": task_payload
        }

        # 1. Create Task
        try:
            async with session.post("https://api.capsolver.com/createTask", json=payload) as resp:
                data = await resp.json()
                if data.get("errorId") != 0:
                    logger.error(f"CapSolver Create Error: {data}")
                    return None
                task_id = data["taskId"]
        except Exception as e:
            logger.error(f"CapSolver Connection Error: {e}")
            return None

        # 2. Get Result
        logger.info(f"CapSolver Task Created ({task_id}) [Proxy: {use_proxy}]. Polling...")
        waited = 0
        while waited < 120:
            await asyncio.sleep(2)
            waited += 2
            
            async with session.post("https://api.capsolver.com/getTaskResult", json={"clientKey": self.api_key, "taskId": task_id}) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    continue
                    
                if data.get("status") == "ready":
                    return data["solution"]["token"] if "token" in data["solution"] else data["solution"]["gRecaptchaResponse"]
                
                if data.get("status") == "failed":
                    logger.error(f"CapSolver Failed: {data.get('errorDescription')}")
                    return None
                    
        return None

    async def _inject_token(self, page, method, token):
        """
        Injects the solver token into the page's hidden response fields.
        Uses defensive checks to avoid null-pointer errors.
        """
        await page.evaluate(f"""(token) => {{
            const setVal = (sel, val) => {{
                const el = document.querySelector(sel);
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
                setVal('[name="cf-turnstile-response"]', token);
            }}
            
            // Trigger generic callbacks that many sites use to proceed after token injection
            const callbacks = ['onCaptchaSuccess', 'onhCaptchaSuccess', 'onTurnstileSuccess', 'recaptchaCallback', 'grecaptchaCallback', 'captchaCallback'];
            callbacks.forEach(cb => {{
                if (typeof window[cb] === 'function') {{
                    try {{ window[cb](token); }} catch(e) {{ console.error('Callback error:', e); }}
                }}
            }});
            
            // Dispatch events to notify the site of the change
            ['h-captcha-response', 'g-recaptcha-response', 'cf-turnstile-response'].forEach(name => {{
                const el = document.querySelector(`[name="${{name}}"]`);
                if (el) {{
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }});
        }}""", token)

    async def _wait_for_human(self, page, timeout):
        """
        Pause execution and wait for manual captcha resolution.

        Args:
            page: The Playwright Page instance.
            timeout: Maximum time to wait in seconds.

        Returns:
            True if the captcha was solved (token detected), False if timed out.
        """
        # HEADLESS CHECK: If running headless, we cannot solve manually.
        import os
        is_headless = os.environ.get("HEADLESS", "false").lower() == "true"
        
        if is_headless:
            logger.error("❌ Headless mode detected. Skipping manual captcha solve.")
            return False

        logger.info("⚠️ PAUSED FOR MANUAL CAPTCHA SOLVE ⚠️")
        logger.info(f"Please solve the captcha in the browser within {timeout} seconds.")
        
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            await asyncio.sleep(2)
            
            # Check for tokens to see if user solved it
            token = await page.evaluate("""() => {
                const h = document.querySelector('[name="h-captcha-response"]');
                const g = document.querySelector('[name="g-recaptcha-response"]');
                const cf = document.querySelector('[name="cf-turnstile-response"]');
                return (h && h.value) || (g && g.value) || (cf && cf.value);
            }""")
            
            if token:
                logger.info("✅ Manual solve detected! Resuming...")
                return True
                
        logger.error("❌ Manual solve timed out.")
        return False

    async def _extract_sitekey_from_scripts(self, page, method):
        """
        Scan page scripts and global variables for sitekeys.
        """
        return await page.evaluate("""() => {
            const patterns = [
                /sitekey["']\\s*:\\s*["']([^"']{20,})["']/i,
                /site-key["']\\s*:\\s*["']([^"']{20,})["']/i,
                /key["']\\s*:\\s*["']([^"']{20,})["']/i,
                /render\\(.+?["']([^"']{20,})["']/i
            ];
            
            // 1. Check common global variables
            const globals = [
                 '___hcaptcha_sitekey_id', 'RECAPTCHA_SITE_KEY', 'H_SITE_KEY', 
                 'hcaptcha_sitekey', 'captcha_sitekey', 'cf_sitekey'
            ];
            for (const g of globals) {
                if (window[g] && typeof window[g] === 'string' && window[g].length > 20) return window[g];
            }
            
            // 2. Scan script tags
            const scripts = Array.from(document.getElementsByTagName('script'));
            for (const script of scripts) {
                const content = script.textContent || script.innerHTML;
                if (!content) continue;
                
                for (const pattern of patterns) {
                    const match = content.match(pattern);
                    if (match && match[1] && match[1].length > 20) return match[1];
                }
            }
            
            // 3. Check for turnstile specifically in render calls
            if (typeof turnstile !== 'undefined' && turnstile._render_parameters) {
                 return turnstile._render_parameters.sitekey;
            }

            return null;
        }""")
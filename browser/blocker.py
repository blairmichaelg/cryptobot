import logging
import re
from playwright.async_api import Route, Request

logger = logging.getLogger(__name__)

# Common Ad/Tracker/Fingerprinting Domains (Expanded)
AD_DOMAINS = [
    # Google Ads & Analytics
    r".*googlesyndication\.com.*",
    r".*doubleclick\.net.*",
    r".*google-analytics\.com.*",
    r".*googleadservices\.com.*",
    r".*googletagmanager\.com.*",
    r".*googletagservices\.com.*",
    r".*pagead2\.googlesyndication\.com.*",
    # Facebook/Meta
    r".*facebook\.net.*",
    r".*facebook\.com/tr.*",
    r".*connect\.facebook\.net.*",
    # Amazon
    r".*amazon-adsystem\.com.*",
    r".*assoc-amazon\.com.*",
    # Ad Networks
    r".*criteo\.com.*",
    r".*adnxs\.com.*",
    r".*outbrain\.com.*",
    r".*taboola\.com.*",
    r".*pubmatic\.com.*",
    r".*rubiconproject\.com.*",
    r".*openx\.net.*",
    r".*adform\.net.*",
    r".*bidswitch\.net.*",
    r".*casalemedia\.com.*",
    # Analytics & Tracking
    r".*hotjar\.com.*",
    r".*bing\.com/bat\.js.*",
    r".*clarity\.ms.*",
    r".*mouseflow\.com.*",
    r".*mixpanel\.com.*",
    r".*segment\.com.*",
    r".*amplitude\.com.*",
    r".*fullstory\.com.*",
    r".*heapanalytics\.com.*",
    # Fingerprinting & Bot Detection
    r".*datadome\.co.*",
    r".*perimeterx\.net.*",
    r".*kasada\.io.*",
    r".*imperva\.com.*",
    r".*fingerprintjs\.com.*",
    r".*creativecdn\.com.*",
    # Social Widgets (load tracking scripts)
    r".*addthis\.com.*",
    r".*sharethis\.com.*",
    # Crypto-specific Ad Networks
    r".*a-ads\.com.*",
    r".*bitmedia\.io.*",
    r".*coinzilla\.com.*",
    r".*cointraffic\.io.*",
]

class ResourceBlocker:
    def __init__(self, block_images: bool = True, block_media: bool = True):
        self.block_images = block_images
        self.block_media = block_media
        self.compiled_patterns = [re.compile(p) for p in AD_DOMAINS]
        self.enabled = True

    async def handle_route(self, route: Route):
        if not self.enabled:
            await route.continue_()
            return
            
        request = route.request
        resource_type = request.resource_type
        url = request.url

        # 1. Block by Resource Type
        if self.block_images and resource_type == "image":
            lower_url = url.lower()
            captcha_allowlist = (
                "captcha",
                "recaptcha",
                "hcaptcha",
                "turnstile",
                "challenge",
                "challenges.cloudflare.com",
                "cdn-cgi",
            )
            if lower_url.startswith("data:image/") or any(token in lower_url for token in captcha_allowlist):
                await route.continue_()
                return
            await route.abort()
            return
        
        if self.block_media and resource_type in ["media", "font", "stylesheet"]:
            # We are careful with stylesheets, but for heavy optimization:
            # Maybe restrict stylesheet blocking to specific heavy domains if needed.
            # For now, let's stick to media/font.
            if resource_type in ["media", "font"]:
                await route.abort()
                return

        # 2. Block by Domain (Ads/Trackers)
        for pattern in self.compiled_patterns:
            if pattern.match(url):
                # logger.debug(f"Blocked Ad: {url}")
                await route.abort()
                return

        # 3. Allow
        await route.continue_()

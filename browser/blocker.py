"""Network-level resource blocker for Cryptobot Gen 3.0.

Blocks ad networks, analytics trackers, fingerprinting services, and
optionally images / media at the Playwright route level.  This reduces
page-load time, bandwidth, and fingerprint surface area.

The domain block-list (``AD_DOMAINS``) is compiled to regex patterns at
construction time for fast matching.
"""

import logging
import re
from typing import List
from playwright.async_api import Route, Request

logger = logging.getLogger(__name__)

# Common Ad/Tracker/Fingerprinting Domains (Expanded 2025-2026)
AD_DOMAINS = [
    # Google Ads & Analytics
    r".*googlesyndication\.com.*",
    r".*doubleclick\.net.*",
    r".*google-analytics\.com.*",
    r".*googleadservices\.com.*",
    r".*googletagmanager\.com.*",
    r".*googletagservices\.com.*",
    r".*pagead2\.googlesyndication\.com.*",
    r".*adservice\.google\.com.*",
    # Facebook/Meta
    r".*facebook\.net.*",
    r".*facebook\.com/tr.*",
    r".*connect\.facebook\.net.*",
    r".*pixel\.facebook\.com.*",
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
    r".*popads\.net.*",
    r".*popcash\.net.*",
    r".*propellerads\.com.*",
    r".*adsterra\.com.*",
    r".*hilltopads\.net.*",
    r".*richads\.com.*",
    r".*clickadu\.com.*",
    r".*exoclick\.com.*",
    r".*juicyads\.com.*",
    r".*trafficjunky\.com.*",
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
    r".*smartlook\.com.*",
    r".*logrocket\.com.*",
    r".*posthog\.com.*",
    r".*plausible\.io.*",
    r".*matomo\.cloud.*",
    # Bot Detection & Fingerprinting Services
    r".*datadome\.co.*",
    r".*perimeterx\.net.*",
    r".*kasada\.io.*",
    r".*imperva\.com.*",
    r".*fingerprintjs\.com.*",
    r".*fingerprint\.com.*",
    r".*creativecdn\.com.*",
    r".*distil\.it.*",
    r".*distilnetworks\.com.*",
    r".*arkoselabs\.com.*",
    r".*funcaptcha\.com.*",
    r".*shape\.com.*",
    r".*shapesecurity\.com.*",
    r".*akamaiedge\.net/bot.*",
    r".*botd\.io.*",
    r".*castle\.io.*",
    r".*human\.com.*",
    r".*humansecurity\.com.*",
    r".*ipqualityscore\.com.*",
    r".*maxmind\.com.*",
    r".*sift\.com.*",
    r".*device-detector\.io.*",
    # IP/Proxy Detection APIs
    r".*api\.ipify\.org.*",
    r".*ip-api\.com.*",
    r".*ipinfo\.io.*",
    r".*proxycheck\.io.*",
    r".*iphub\.info.*",
    r".*ip2location\.com.*",
    r".*getipintel\.net.*",
    r".*abstractapi\.com.*",
    r".*vpnapi\.io.*",
    r".*ipqualityscore\.com/api.*",
    r".*icanhazip\.com.*",
    r".*checkip\.amazonaws\.com.*",
    r".*ifconfig\.me.*",
    r".*ipecho\.net.*",
    r".*api\.myip\.com.*",
    r".*wtfismyip\.com.*",
    r".*httpbin\.org/ip.*",
    r".*api64\.ipify\.org.*",
    r".*ipapi\.co.*",
    r".*extreme-ip-lookup\.com.*",
    r".*db-ip\.com/api.*",
    # Advanced Bot Detection & Anti-Fraud (2025-2026)
    r".*mtcaptcha\.com.*",
    r".*geetest\.com.*",
    r".*hcaptcha\.com/siteverify.*",
    r".*recaptcha\.net/recaptcha/enterprise.*",
    r".*cleantalk\.org.*",
    r".*shield\.io.*",
    r".*threat-intelligence\.io.*",
    r".*fraudlogix\.com.*",
    r".*pixalate\.com.*",
    r".*spamhaus\.org.*",
    r".*securitytrails\.com.*",
    r".*creepjs\.netlify\.app.*",
    r".*browserleaks\.com.*",
    r".*fingerprintjs\.com/v3.*",
    r".*fingerprint\.com/v3.*",
    r".*cdn\.fingerprint\.com.*",
    r".*fpjs\.io.*",
    r".*openfpcdn\.io.*",
    r".*cdn\.castle\.io.*",
    # Social Widgets
    r".*addthis\.com.*",
    r".*sharethis\.com.*",
    # Crypto-specific Ad Networks
    r".*a-ads\.com.*",
    r".*bitmedia\.io.*",
    r".*coinzilla\.com.*",
    r".*cointraffic\.io.*",
    r".*coinad\.media.*",
    r".*mellow\.ads.*",
]


class ResourceBlocker:
    """Route-level resource blocker for Playwright browser contexts.

    Blocks requests by resource type (images, media, fonts) and by URL
    pattern (ad networks, analytics, fingerprinting services).  CAPTCHA-related
    resources are always allowed through, even when image blocking is enabled.

    Attributes:
        block_images: Whether image resources are blocked.
        block_media: Whether media and font resources are blocked.
        compiled_patterns: Pre-compiled regex patterns for domain blocking.
        enabled: Master switch – set to ``False`` to bypass all blocking
            (used during shortlink traversal).
    """

    def __init__(self, block_images: bool = True, block_media: bool = True) -> None:
        """Initialise the resource blocker.

        Args:
            block_images: Block image resource requests.
            block_media: Block media (video/audio) and font requests.
        """
        self.block_images = block_images
        self.block_media = block_media
        self.compiled_patterns: List[re.Pattern[str]] = [
            re.compile(p) for p in AD_DOMAINS
        ]
        self.enabled: bool = True

    async def handle_route(self, route: Route) -> None:
        """Playwright route handler that aborts or continues each request.

        Decision order:
            1. If blocking is disabled (``self.enabled is False``), continue.
            2. Block images (except CAPTCHA-related).
            3. Block media / fonts.
            4. Block known ad / tracker domains.
            5. Allow everything else.

        Args:
            route: Playwright ``Route`` object for the intercepted request.
        """
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
            is_data_uri = lower_url.startswith("data:image/")
            is_captcha = any(
                token in lower_url
                for token in captcha_allowlist
            )
            if is_data_uri or is_captcha:
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

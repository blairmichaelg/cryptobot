import logging
import re
from playwright.async_api import Route, Request

logger = logging.getLogger(__name__)

# Common Ad/Tracker Domains (Simplified List)
AD_DOMAINS = [
    r".*googlesyndication.com.*",
    r".*doubleclick.net.*",
    r".*google-analytics.com.*",
    r".*facebook.net.*",
    r".*amazon-adsystem.com.*",
    r".*criteo.com.*",
    r".*adnxs.com.*",
    r".*hotjar.com.*",
    r".*bing.com/bat.js.*"
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

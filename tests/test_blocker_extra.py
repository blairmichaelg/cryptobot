import pytest
import re
from unittest.mock import AsyncMock, MagicMock
from browser.blocker import ResourceBlocker

class TestResourceBlocker:
    
    @pytest.mark.asyncio
    async def test_handle_route_disabled(self):
        """Test blocking when blocker is disabled (lines 70-72)."""
        blocker = ResourceBlocker()
        blocker.enabled = False
        mock_route = AsyncMock()
        
        await blocker.handle_route(mock_route)
        mock_route.continue_.assert_called_once()

    @pytest.mark.asyncio
    async def test_block_images(self):
        """Test image blocking logic (lines 79-81)."""
        # 1. Enabled (Default)
        blocker = ResourceBlocker(block_images=True)
        mock_route = AsyncMock()
        mock_route.request.resource_type = "image"
        mock_route.request.url = "http://example.com/a.png"
        
        await blocker.handle_route(mock_route)
        mock_route.abort.assert_called_once()
        
        # 2. Disabled
        blocker.block_images = False
        mock_route.reset_mock()
        await blocker.handle_route(mock_route)
        mock_route.continue_.assert_called_once()

    @pytest.mark.asyncio
    async def test_block_media_and_fonts(self):
        """Test media and font blocking (lines 83-89)."""
        blocker = ResourceBlocker(block_media=True)
        
        # 1. Media
        mock_route = AsyncMock()
        mock_route.request.resource_type = "media"
        mock_route.request.url = "http://example.com/video.mp4"
        await blocker.handle_route(mock_route)
        mock_route.abort.assert_called_once()
        
        # 2. Font
        mock_route.reset_mock()
        mock_route.request.resource_type = "font"
        await blocker.handle_route(mock_route)
        mock_route.abort.assert_called_once()
        
        # 3. Media blocking disabled
        blocker.block_media = False
        mock_route.reset_mock()
        await blocker.handle_route(mock_route)
        mock_route.continue_.assert_called_once()

    @pytest.mark.asyncio
    async def test_block_ad_domains(self):
        """Test blocking by domain (lines 91-96)."""
        blocker = ResourceBlocker()
        
        # 1. Blocked domain
        mock_route = AsyncMock()
        mock_route.request.resource_type = "script"
        mock_route.request.url = "http://googlesyndication.com/ads.js"
        await blocker.handle_route(mock_route)
        mock_route.abort.assert_called_once()
        
        # 2. Another blocked domain (crypto ads)
        mock_route.reset_mock()
        mock_route.request.url = "https://a-ads.com/unit.js"
        await blocker.handle_route(mock_route)
        mock_route.abort.assert_called_once()

    @pytest.mark.asyncio
    async def test_allow_legit_resources(self):
        """Test allowing legitimate resources (lines 98-99)."""
        blocker = ResourceBlocker(block_images=True)
        mock_route = AsyncMock()
        mock_route.request.resource_type = "script"
        mock_route.request.url = "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"
        
        await blocker.handle_route(mock_route)
        mock_route.continue_.assert_called_once()

    @pytest.mark.asyncio
    async def test_stylesheet_logic(self):
        """Test that stylesheets are NOT blocked even if block_media is True (lines 83-90)."""
        # Current logic:
        # if self.block_media and resource_type in ["media", "font", "stylesheet"]:
        #    if resource_type in ["media", "font"]:
        #        await route.abort()
        #        return
        # This means stylesheets pass through (unless they match an ad domain later)
        blocker = ResourceBlocker(block_media=True)
        mock_route = AsyncMock()
        mock_route.request.resource_type = "stylesheet"
        mock_route.request.url = "http://example.com/style.css"
        
        await blocker.handle_route(mock_route)
        mock_route.continue_.assert_called_once()

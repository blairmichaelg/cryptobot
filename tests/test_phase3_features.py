"""
Tests for Phase 3-4 enhancement features:
- Enhanced Cloudflare detection
- Proxy health monitoring  
- Daily report generation
"""

import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch
from core.analytics import set_test_mode


@pytest.fixture(autouse=True)
def enable_test_mode():
    """Automatically enable test mode for all analytics tests."""
    set_test_mode(True)
    yield
    set_test_mode(False)


class TestCloudflareDetection:
    """Tests for enhanced Cloudflare challenge detection."""
    
    @pytest.mark.asyncio
    async def test_handle_cloudflare_no_challenge(self):
        """Test that normal pages pass through quickly."""
        from faucets.base import FaucetBot
        
        page = AsyncMock()
        page.title = AsyncMock(return_value="Normal Page Title")
        page.locator = MagicMock(return_value=AsyncMock(is_visible=AsyncMock(return_value=False)))
        page.viewport_size = {'width': 1920, 'height': 1080}
        
        settings = MagicMock()
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "test"
        
        bot = FaucetBot(settings, page)
        result = await bot.handle_cloudflare(max_wait_seconds=5)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_handle_cloudflare_detects_challenge(self):
        """Test that Cloudflare challenges are detected by title."""
        from faucets.base import FaucetBot
        
        call_count = [0]
        
        async def mock_title():
            call_count[0] += 1
            if call_count[0] < 3:
                return "Just a moment..."
            return "Normal Page"
        
        page = AsyncMock()
        page.title = mock_title
        page.locator = MagicMock(return_value=AsyncMock(is_visible=AsyncMock(return_value=False)))
        page.viewport_size = {'width': 1920, 'height': 1080}
        page.mouse.move = AsyncMock()
        
        settings = MagicMock()
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "test"
        
        bot = FaucetBot(settings, page)
        result = await bot.handle_cloudflare(max_wait_seconds=30)
        
        assert result is True
        assert call_count[0] >= 3
    
    @pytest.mark.asyncio
    async def test_detect_page_crash_healthy(self):
        """Test page crash detection on healthy page."""
        from faucets.base import FaucetBot
        
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value="complete")
        
        settings = MagicMock()
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "test"
        
        bot = FaucetBot(settings, page)
        result = await bot.detect_page_crash()
        
        assert result is True


class TestProxyHealthMonitoring:
    """Tests for proxy latency tracking and health checks."""
    
    def test_proxy_key_generation(self):
        """Test unique proxy key generation."""
        from core.proxy_manager import ProxyManager, Proxy
        from core.config import BotSettings
        
        settings = BotSettings()
        pm = ProxyManager(settings)
        
        proxy = Proxy(ip="1.2.3.4", port=8080, username="", password="")
        key = pm._proxy_key(proxy)
        
        assert key == "1.2.3.4:8080"
    
    def test_record_failure_marks_dead(self):
        """Test that repeated failures mark proxy as dead."""
        from core.proxy_manager import ProxyManager
        from core.config import BotSettings
        
        settings = BotSettings()
        pm = ProxyManager(settings)
        
        proxy_key = "test:1234"
        
        # Record failures up to threshold
        for _ in range(pm.DEAD_PROXY_FAILURE_COUNT):
            pm.record_failure(proxy_key)
        
        assert proxy_key in pm.dead_proxies
    
    def test_get_proxy_stats_empty(self):
        """Test stats for proxy with no measurements."""
        from core.proxy_manager import ProxyManager, Proxy
        from core.config import BotSettings
        
        settings = BotSettings()
        pm = ProxyManager(settings)
        
        proxy = Proxy(ip="1.2.3.4", port=8080, username="", password="")
        stats = pm.get_proxy_stats(proxy)
        
        assert stats["avg_latency"] is None
        assert stats["measurement_count"] == 0


class TestDailyReports:
    """Tests for automated daily report generation."""
    
    def test_get_trending_analysis_empty(self, tmp_path):
        """Test trending analysis with no data."""
        from core.analytics import EarningsTracker
        
        # Use a temporary file to ensure it's empty
        temp_file = tmp_path / "empty_analytics.json"
        tracker = EarningsTracker(storage_file=str(temp_file))
        trends = tracker.get_trending_analysis(7)
        
        assert trends == {}
    
    def test_get_trending_analysis_with_data(self, tmp_path):
        """Test trending analysis with sample data."""
        from core.analytics import EarningsTracker
        
        # Use a temporary file
        temp_file = tmp_path / "data_analytics.json"
        tracker = EarningsTracker(storage_file=str(temp_file))
        
        # Add some claims
        for i in range(5):
            tracker.record_claim(
                faucet="TestFaucet",
                success=True,
                amount=100,
                currency="satoshi"
            )
        
        trends = tracker.get_trending_analysis(7)
        
        assert "TestFaucet" in trends
        assert "daily_earnings" in trends["TestFaucet"]
        assert "growth_rate" in trends["TestFaucet"]
    
    def test_generate_automated_report(self):
        """Test automated report generation."""
        from core.analytics import EarningsTracker
        
        tracker = EarningsTracker()
        tracker.record_claim("Faucet1", True, 50, "satoshi")
        tracker.record_claim("Faucet2", True, 100, "satoshi")
        tracker.record_claim("Faucet3", False, 0, "satoshi")
        
        report = tracker.generate_automated_report(save_to_file=False)
        
        assert "CRYPTOBOT DAILY REPORT" in report
        assert "SESSION OVERVIEW" in report
        assert "EARNINGS BY CURRENCY" in report

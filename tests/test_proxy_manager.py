import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
from core.proxy_manager import ProxyManager, Proxy
from core.config import BotSettings, AccountProfile
import aiohttp

@pytest.fixture
def settings():
    s = BotSettings()
    s.twocaptcha_api_key = "test_key"
    s.use_2captcha_proxies = True
    return s

class TestProxyManager:
    @patch("builtins.open", new_callable=mock_open, read_data="http://u1:p1@1.1.1.1:8080\nuser2:pass2@2.2.2.2:9090")
    @patch("os.path.exists", return_value=True)
    def test_load_proxies_from_file(self, mock_exists, mock_file, settings):
        manager = ProxyManager(settings)
        
        # Should have loaded 2 proxies from the mock file (called in __init__)
        assert len(manager.proxies) == 2
        assert manager.proxies[0].ip == "1.1.1.1"
        assert manager.proxies[0].port == 8080
        assert manager.proxies[0].username == "u1"
        assert manager.proxies[0].password == "p1"
        
        assert manager.proxies[1].ip == "2.2.2.2"
        assert manager.proxies[1].port == 9090
        assert manager.proxies[1].username == "user2"
        assert manager.proxies[1].password == "pass2"

    @patch("builtins.open", new_callable=mock_open, read_data="http://u1:p1@1.1.1.1:8080")
    @patch("os.path.exists", return_value=True)
    async def test_fetch_proxies_generates_sessions(self, mock_exists, mock_file, settings):
        manager = ProxyManager(settings)
        # Should start with 1 proxy
        assert len(manager.proxies) == 1
        
        # Calling fetch_proxies should generate sessions and increase count
        # method returns total count of proxies (base + generated) or just generated?
        # My implementation returns len(new_proxies) which includes base.
        success = await manager.fetch_proxies(count=5)
        
        # fetch_proxies returns bool
        assert success is True
        # Base (1) + Generated (5) = 6
        assert len(manager.proxies) == 6
        assert manager.proxies[0].username == "u1"
        assert "-session-" in manager.proxies[1].username
        
def test_assign_proxies_fallback(settings):
    manager = ProxyManager(settings)
    # Manually populate proxies to test assignment logic
    manager.proxies = [
        Proxy(ip="1.1.1.1", port=80, username="u1", password="p1"),
        Proxy(ip="2.2.2.2", port=80, username="u2", password="p2")
    ]
    
    profiles = [
        AccountProfile(faucet="fire", username="user1", password="pw"),
        AccountProfile(faucet="coin", username="user2", password="pw"),
        AccountProfile(faucet="free", username="user3", password="pw")
    ]
    
    manager.assign_proxies(profiles)
    
    # Check 1:1 assignment and wrapping
    assert profiles[0].proxy == "http://u1:p1@1.1.1.1:80"
    assert profiles[1].proxy == "http://u2:p2@2.2.2.2:80"
    assert profiles[2].proxy == "http://u1:p1@1.1.1.1:80" # Wrap around

class TestProxyFetching:
    """Test 2Captcha API proxy fetching functionality"""
    
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_fetch_proxy_config_from_2captcha_success(self, mock_get, settings):
        """Test successful API response with proxy config"""
        # Mock API response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": 1,
            "request": "testuser:testpass@proxy.2captcha.com:8080"
        })
        mock_get.return_value.__aenter__.return_value = mock_response
        
        manager = ProxyManager(settings)
        proxy = await manager.fetch_proxy_config_from_2captcha()
        
        assert proxy is not None
        assert proxy.ip == "proxy.2captcha.com"
        assert proxy.port == 8080
        assert proxy.username == "testuser"
        assert proxy.password == "testpass"
    
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_fetch_proxy_config_from_2captcha_with_data_field(self, mock_get, settings):
        """Test API response with data field containing proxy list"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": "OK",
            "data": ["proxyuser:proxypass@gw.2captcha.com:9090"]
        })
        mock_get.return_value.__aenter__.return_value = mock_response
        
        manager = ProxyManager(settings)
        proxy = await manager.fetch_proxy_config_from_2captcha()
        
        assert proxy is not None
        assert proxy.ip == "gw.2captcha.com"
        assert proxy.port == 9090
        assert proxy.username == "proxyuser"
        assert proxy.password == "proxypass"
    
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_fetch_proxy_config_from_2captcha_failure(self, mock_get, settings):
        """Test failed API response"""
        mock_response = AsyncMock()
        mock_response.status = 403
        mock_get.return_value.__aenter__.return_value = mock_response
        
        manager = ProxyManager(settings)
        proxy = await manager.fetch_proxy_config_from_2captcha()
        
        assert proxy is None
    
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.path.exists", return_value=False)
    @patch("os.path.abspath", return_value="/test/proxies.txt")
    async def test_fetch_proxies_from_api_with_api_fallback(self, mock_abs, mock_exists, mock_file, mock_get, settings):
        """Test that fetch_proxies_from_api falls back to API when file is empty"""
        # Mock API response to provide base proxy
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": 1,
            "request": "apiuser:apipass@api.proxy.com:8080"
        })
        mock_get.return_value.__aenter__.return_value = mock_response
        
        manager = ProxyManager(settings)
        # Simulate empty proxies
        manager.proxies = []
        manager.all_proxies = []
        
        count = await manager.fetch_proxies_from_api(quantity=5)
        
        # Should have fetched base + generated sessions
        assert count == 6  # 1 base + 5 generated
        assert len(manager.proxies) == 6
        assert manager.proxies[0].username == "apiuser"
        # Check session rotation
        assert "-session-" in manager.proxies[1].username
    
    @pytest.mark.asyncio
    async def test_fetch_proxy_config_no_api_key(self, settings):
        """Test that fetching fails gracefully without API key"""
        settings.twocaptcha_api_key = None
        manager = ProxyManager(settings)
        
        proxy = await manager.fetch_proxy_config_from_2captcha()
        assert proxy is None

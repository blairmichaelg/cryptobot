import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock, mock_open
from core.proxy_manager import ProxyManager, Proxy
from core.config import BotSettings, AccountProfile

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
    async def test_fetch_proxies_calls_load(self, mock_exists, mock_file, settings):
        manager = ProxyManager(settings)
        # fetch_proxies is deprecated but should still work by calling load
        result = await manager.fetch_proxies()
        assert result is True
        assert len(manager.proxies) == 1
        
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

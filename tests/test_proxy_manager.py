import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from core.proxy_manager import ProxyManager, Proxy
from core.config import BotSettings, AccountProfile

@pytest.fixture
def settings():
    s = BotSettings()
    s.twocaptcha_api_key = "test_key"
    s.use_2captcha_proxies = True
    return s

@pytest.mark.asyncio
async def test_fetch_proxies_success(settings):
    manager = ProxyManager(settings)
    
    # Mock aiohttp responses for multiple calls:
    # 1. ipify (detector)
    # 2. balance check
    # 3. proxy generate
    
    mock_ip_resp = {"ip": "1.2.3.4"}
    mock_balance_resp = {"status": 1, "request": "10.00"}
    mock_proxy_resp = {"status": 1, "request": ["1.1.1.1:8080", "2.2.2.2:8080"]}
    
    mock_responses = [
        {"json": mock_ip_resp, "text": "{\"ip\": \"1.2.3.4\"}"},
        {"json": mock_balance_resp, "text": "{\"status\": 1, \"request\": \"10.00\"}"},
        {"json": mock_proxy_resp, "text": "{\"status\": 1, \"request\": [\"1.1.1.1:8080\", \"2.2.2.2:8080\"]}"}
    ]
    
    with patch("aiohttp.ClientSession.get") as mock_get:
        # Side effect to handle multiple calls
        class MockResponse:
            def __init__(self, data):
                self._data = data
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def json(self): return self._data["json"]
            async def text(self): return self._data["text"]
        
        mock_get.side_effect = [MockResponse(r) for r in mock_responses]
        
        success = await manager.fetch_proxies(count=2)
        assert success is True
        assert len(manager.proxies) == 2
        assert manager.proxies[0].ip == "1.1.1.1"
        
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

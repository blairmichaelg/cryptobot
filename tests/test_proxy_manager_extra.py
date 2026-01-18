import pytest
import asyncio
import aiohttp
import json
from unittest.mock import AsyncMock, MagicMock, patch
from core.proxy_manager import ProxyManager, Proxy
from core.config import BotSettings, AccountProfile

@pytest.fixture
def mock_settings():
    s = BotSettings()
    s.twocaptcha_api_key = "test_key"
    return s

class TestProxyManagerExtra:
    
    @pytest.mark.asyncio
    async def test_proxy_to_strings(self):
        """Cover Proxy.to_string and to_2captcha_string (lines 22-29)."""
        p_auth = Proxy(ip="1.2.3.4", port=8080, username="u", password="p")
        assert p_auth.to_string() == "http://u:p@1.2.3.4:8080"
        assert p_auth.to_2captcha_string() == "u:p@1.2.3.4:8080"
        
        p_no_auth = Proxy(ip="1.2.3.4", port=8080, username="", password="")
        assert p_no_auth.to_string() == "http://1.2.3.4:8080"
        assert p_no_auth.to_2captcha_string() == "1.2.3.4:8080"

    @pytest.mark.asyncio
    async def test_validate_proxy_scenarios(self, mock_settings):
        """Cover validate_proxy scenarios (lines 58-78)."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.1.1.1", port=80, username="", password="")
        
        def make_mock_resp(json_data=None, status=200):
            mock = AsyncMock()
            mock.status = status
            mock.json = AsyncMock(return_value=json_data)
            mock.__aenter__ = AsyncMock(return_value=mock)
            mock.__aexit__ = AsyncMock(return_value=None)
            return mock

        # 1. Success (67-69)
        with patch("aiohttp.ClientSession.get", return_value=make_mock_resp({"origin": "1.1.1.1"})):
            assert await manager.validate_proxy(proxy) is True

        # 2. Status Error (71-72)
        with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(status=403)):
            assert await manager.validate_proxy(proxy) is False

        # 3. Timeout (73-75)
        with patch("aiohttp.ClientSession.get", side_effect=asyncio.TimeoutError()):
            assert await manager.validate_proxy(proxy) is False

        # 4. Exception (76-78)
        with patch("aiohttp.ClientSession.get", side_effect=Exception("Error")):
            assert await manager.validate_proxy(proxy) is False

    @pytest.mark.asyncio
    async def test_validate_all_proxies(self, mock_settings):
        """Cover validate_all_proxies (lines 87-106)."""
        # Patch load_proxies_from_file to do nothing so we start empty
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            manager = ProxyManager(mock_settings)
            # Empty (87-88)
            assert await manager.validate_all_proxies() == 0
            
            manager.proxies = [Proxy(ip=f"1.1.1.{i}", port=80, username="", password="") for i in range(5)]
            
            with patch.object(ProxyManager, "validate_proxy", side_effect=[True, False, True, False, True]):
                valid_count = await manager.validate_all_proxies()
                assert valid_count == 3
                assert len(manager.validated_proxies) == 3

    @pytest.mark.asyncio
    async def test_fetch_proxies_wrapper(self, mock_settings):
        """
        Cover fetch_proxies wrapper (lines 349-356).
        The old complex logic is deprecated/removed, so we just test that it delegates to load_proxies_from_file.
        """
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            manager = ProxyManager(mock_settings)

        # 1. Success (loaded > 0)
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=5):
            assert await manager.fetch_proxies() is True
        
        # 2. Failure (loaded == 0)
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            assert await manager.fetch_proxies() is False

    def test_assign_proxies_fallback(self, mock_settings):
        """Cover assign_proxies fallback (lines 212-213)."""
        manager = ProxyManager(mock_settings)
        manager.assign_proxies([]) # Should log warning and return

    def test_get_proxy_for_solver(self, mock_settings):
        """Cover get_proxy_for_solver (lines 235-236)."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        manager.assignments["user1"] = proxy
        
        assert manager.get_proxy_for_solver("user1") == "u:p@1.1.1.1:80"
        assert manager.get_proxy_for_solver("unknown") is None

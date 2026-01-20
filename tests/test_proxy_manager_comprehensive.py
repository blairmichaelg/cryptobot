"""
Additional comprehensive tests for core.proxy_manager that achieve 100% coverage.
"""
import pytest
import asyncio
import aiohttp
import random
import time
import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from core.proxy_manager import ProxyManager, Proxy
from core.config import BotSettings, AccountProfile


@pytest.fixture
def mock_settings():
    s = BotSettings()
    s.twocaptcha_api_key = "test_key"
    s.residential_proxies_file = "/tmp/test_proxies.txt"
    return s


class TestProxyManagerComprehensive:
    
    def test_proxy_key(self, mock_settings):
        """Test _proxy_key method."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.2.3.4", port=8080, username="u", password="p")
        # New key logic includes credentials
        assert manager._proxy_key(proxy) == "u:p@1.2.3.4:8080"
    
    @pytest.mark.asyncio
    async def test_measure_proxy_latency_success(self, mock_settings):
        """Test measure_proxy_latency success path."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        
        # Mock successful response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()
        
        with patch("aiohttp.ClientSession.get", return_value=mock_resp):
            latency = await manager.measure_proxy_latency(proxy)
            assert latency is not None
            assert latency > 0
            
            # Check latency was recorded
            proxy_key = manager._proxy_key(proxy)
            assert proxy_key in manager.proxy_latency
            assert len(manager.proxy_latency[proxy_key]) == 1
    
    def test_record_failure(self, mock_settings):
        """Test record_failure method."""
        manager = ProxyManager(mock_settings)
        
        # Test simple failure recording
        manager.record_failure("http://u:p@1.1.1.1:8080")
        assert manager.proxy_failures.get("u:p@1.1.1.1:8080", 0) == 1
        
        # Test detected failure (more severe)
        manager.record_failure("http://u:p@1.2.3.4:9090", detected=True)
        proxy_key = "u:p@1.2.3.4:9090"
        assert manager.proxy_failures[proxy_key] >= manager.DEAD_PROXY_FAILURE_COUNT
        assert proxy_key in manager.dead_proxies
    
    def test_remove_dead_proxies(self, mock_settings):
        """Test remove_dead_proxies method."""
        manager = ProxyManager(mock_settings)
        # Force reset all potentially shared state
        manager.proxy_latency = {}
        manager.proxy_failures = {}
        manager.proxy_cooldowns = {}
        manager.dead_proxies = []
        
        proxies = [
            Proxy(ip="10.1.1.1", port=80, username="u1", password="p"),
            Proxy(ip="10.2.2.2", port=80, username="u2", password="p"),
            Proxy(ip="10.3.3.3", port=80, username="u3", password="p"),
        ]
        manager.all_proxies = list(proxies)
        manager.proxies = list(proxies)
        manager.validated_proxies = list(proxies)
        
        # Mark one as dead (cooldown)
        dead_key = manager._proxy_key(manager.proxies[1]) # u2:p@10.2.2.2:80
        manager.proxy_cooldowns[dead_key] = time.time() + 3600 # 1 hour cooldown
        
        removed = manager.remove_dead_proxies()
        assert removed == 1
        assert len(manager.proxies) == 2
        assert all(manager._proxy_key(p) != dead_key for p in manager.proxies)

    @pytest.mark.asyncio
    async def test_measure_proxy_latency_history_truncation(self, mock_settings):
        """Test measure_proxy_latency history truncation."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        proxy_key = manager._proxy_key(proxy)
        
        # Add more than LATENCY_HISTORY_MAX measurements
        manager.proxy_latency[proxy_key] = [100.0] * (manager.LATENCY_HISTORY_MAX + 5)
        
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()
        
        with patch("aiohttp.ClientSession.get", return_value=mock_resp):
            await manager.measure_proxy_latency(proxy)
            # Should have truncated to LATENCY_HISTORY_MAX
            assert len(manager.proxy_latency[proxy_key]) == manager.LATENCY_HISTORY_MAX

    def test_rotate_proxy_current_dead(self, mock_settings):
        """Test rotate_proxy when current proxy is dead."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [
            Proxy(ip="1.1.1.1", port=80, username="u1", password="p"),
            Proxy(ip="2.2.2.2", port=80, username="u2", password="p"),
        ]
        manager.dead_proxies = ["u1:p@1.1.1.1:80"]
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        profile.proxy = "http://u1:p@1.1.1.1:80"
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is not None
        assert "2.2.2.2" in new_proxy

    def test_rotate_proxy_no_healthy_proxies(self, mock_settings):
        """Test rotate_proxy when no healthy proxies available."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [Proxy(ip="1.1.1.1", port=80, username="u", password="p")]
        manager.dead_proxies = ["u:p@1.1.1.1:80"]
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        profile.proxy = "http://u:p@1.1.1.1:80"
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is None

    def test_rotate_proxy_with_protocol_in_current(self, mock_settings):
        """Test rotate_proxy with protocol in current proxy string."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [
            Proxy(ip="1.1.1.1", port=80, username="u1", password="p"),
            Proxy(ip="2.2.2.2", port=80, username="u2", password="p"),
        ]
        manager.dead_proxies = ["u1:p@1.1.1.1:80"]
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        profile.proxy = "http://u1:p@1.1.1.1:80"
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is not None
        assert "2.2.2.2" in new_proxy

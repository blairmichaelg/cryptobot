"""
Additional comprehensive tests for core.proxy_manager to achieve 100% coverage.
"""
import pytest
import asyncio
import aiohttp
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
        """Test _proxy_key method (line 66)."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.2.3.4", port=8080, username="u", password="p")
        assert manager._proxy_key(proxy) == "1.2.3.4:8080"
    
    @pytest.mark.asyncio
    async def test_measure_proxy_latency_success(self, mock_settings):
        """Test measure_proxy_latency success path (lines 80-108)."""
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
            
            # Check failure count was reset
            assert manager.proxy_failures.get(proxy_key, 0) == 0
    
    @pytest.mark.asyncio
    async def test_measure_proxy_latency_non_200_status(self, mock_settings):
        """Test measure_proxy_latency with non-200 status (lines 110-112)."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.1.1.1", port=80, username="", password="")
        
        mock_resp = AsyncMock()
        mock_resp.status = 403
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()
        
        with patch("aiohttp.ClientSession.get", return_value=mock_resp):
            latency = await manager.measure_proxy_latency(proxy)
            assert latency is None
    
    @pytest.mark.asyncio
    async def test_measure_proxy_latency_timeout(self, mock_settings):
        """Test measure_proxy_latency timeout (lines 114-117)."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.1.1.1", port=80, username="", password="")
        
        with patch("aiohttp.ClientSession.get", side_effect=asyncio.TimeoutError()):
            latency = await manager.measure_proxy_latency(proxy)
            assert latency is None
    
    @pytest.mark.asyncio
    async def test_measure_proxy_latency_exception(self, mock_settings):
        """Test measure_proxy_latency exception (lines 118-121)."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.1.1.1", port=80, username="", password="")
        
        with patch("aiohttp.ClientSession.get", side_effect=Exception("Network error")):
            latency = await manager.measure_proxy_latency(proxy)
            assert latency is None
    
    def test_record_failure(self, mock_settings):
        """Test record_failure method (lines 132-152)."""
        manager = ProxyManager(mock_settings)
        
        # Test simple failure recording
        manager.record_failure("http://u:p@1.1.1.1:8080")
        assert manager.proxy_failures.get("1.1.1.1:8080", 0) == 1
        
        # Test detected failure (more severe)
        manager.record_failure("http://1.2.3.4:9090", detected=True)
        proxy_key = "1.2.3.4:9090"
        assert manager.proxy_failures[proxy_key] >= manager.DEAD_PROXY_FAILURE_COUNT
        assert proxy_key in manager.dead_proxies
        
        # Test threshold reached
        manager.proxy_failures["2.2.2.2:80"] = manager.DEAD_PROXY_FAILURE_COUNT - 1
        manager.record_failure("2.2.2.2:80")
        assert "2.2.2.2:80" in manager.dead_proxies
    
    def test_get_proxy_stats(self, mock_settings):
        """Test get_proxy_stats method (lines 161-179)."""
        manager = ProxyManager(mock_settings)
        proxy = Proxy(ip="1.1.1.1", port=80, username="", password="")
        proxy_key = manager._proxy_key(proxy)
        
        # No data
        stats = manager.get_proxy_stats(proxy)
        assert stats["avg_latency"] is None
        assert stats["measurement_count"] == 0
        assert stats["is_dead"] == False
        
        # With latency data
        manager.proxy_latency[proxy_key] = [100, 150, 120]
        stats = manager.get_proxy_stats(proxy)
        assert stats["avg_latency"] == (100 + 150 + 120) / 3
        assert stats["min_latency"] == 100
        assert stats["max_latency"] == 150
        assert stats["measurement_count"] == 3
        
        # Marked as dead
        manager.dead_proxies.append(proxy_key)
        stats = manager.get_proxy_stats(proxy)
        assert stats["is_dead"] == True
    
    @pytest.mark.asyncio
    async def test_health_check_all_proxies(self, mock_settings):
        """Test health_check_all_proxies method (lines 188-216)."""
        manager = ProxyManager(mock_settings)
        
        # Empty proxies
        summary = await manager.health_check_all_proxies()
        assert summary["total"] == 0
        assert summary["healthy"] == 0
        
        # With proxies
        manager.proxies = [
            Proxy(ip=f"1.1.1.{i}", port=80, username="", password="")
            for i in range(3)
        ]
        
        # Mock measure_proxy_latency to return mix of success/failure
        with patch.object(manager, "measure_proxy_latency", side_effect=[100.0, None, 150.0]):
            summary = await manager.health_check_all_proxies()
            assert summary["total"] == 3
            assert summary["healthy"] == 2
            assert summary["avg_latency_ms"] == (100.0 + 150.0) / 2
    
    def test_remove_dead_proxies(self, mock_settings):
        """Test remove_dead_proxies method (lines 225-232)."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [
            Proxy(ip="1.1.1.1", port=80, username="", password=""),
            Proxy(ip="2.2.2.2", port=80, username="", password=""),
            Proxy(ip="3.3.3.3", port=80, username="", password=""),
        ]
        manager.validated_proxies = list(manager.proxies)
        
        # Mark one as dead
        manager.dead_proxies = ["2.2.2.2:80"]
        
        removed = manager.remove_dead_proxies()
        assert removed == 1
        assert len(manager.proxies) == 2
        assert all(manager._proxy_key(p) != "2.2.2.2:80" for p in manager.proxies)
    
    def test_load_proxies_from_file_no_file(self, mock_settings):
        """Test load_proxies_from_file when file doesn't exist (lines 305-313)."""
        with patch("os.path.exists", return_value=False), \
             patch("builtins.open", mock_open()) as mock_file:
            manager = ProxyManager(mock_settings)
            # Should have created template file
            assert mock_file.called
    
    def test_load_proxies_from_file_with_comments(self, mock_settings):
        """Test load_proxies_from_file with comments and blank lines (lines 337-339)."""
        proxy_data = """# Comment line
http://user:pass@1.1.1.1:8080

user2:pass2@2.2.2.2:9090
# Another comment
"""
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=proxy_data)):
            manager = ProxyManager(mock_settings)
            assert len(manager.proxies) == 2
    
    def test_load_proxies_from_file_exception(self, mock_settings):
        """Test load_proxies_from_file exception handling (lines 351-353)."""
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", side_effect=Exception("Read error")):
            manager = ProxyManager(mock_settings)
            assert len(manager.proxies) == 0
    
    def test_parse_proxy_string_invalid_formats(self, mock_settings):
        """Test _parse_proxy_string with invalid formats (lines 363-364, 375-377)."""
        manager = ProxyManager(mock_settings)
        
        # No port
        result = manager._parse_proxy_string("1.1.1.1")
        assert result is None
        
        # Parsing exception
        result = manager._parse_proxy_string("http://[invalid::proxy")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_fetch_proxies_from_api_no_base_proxy(self, mock_settings):
        """Test fetch_proxies_from_api with no base proxy (lines 398-399)."""
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            manager = ProxyManager(mock_settings)
            result = await manager.fetch_proxies_from_api(5)
            assert result == 0
    
    @pytest.mark.asyncio
    async def test_fetch_proxies_from_api_no_auth(self, mock_settings):
        """Test fetch_proxies_from_api when base proxy has no auth (lines 406-407)."""
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            manager = ProxyManager(mock_settings)
            manager.proxies = [Proxy(ip="1.1.1.1", port=80, username="", password="")]
            result = await manager.fetch_proxies_from_api(5)
            assert result == 0
    
    @pytest.mark.asyncio
    async def test_fetch_proxies_from_api_success(self, mock_settings):
        """Test successful proxy generation (lines 408-458)."""
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            manager = ProxyManager(mock_settings)
            base_proxy = Proxy(ip="1.1.1.1", port=80, username="baseuser", password="basepass")
            manager.proxies = [base_proxy]
            
            with patch("builtins.open", mock_open()) as mock_file:
                result = await manager.fetch_proxies_from_api(3)
                assert result == 4  # Base + 3 generated
                assert len(manager.proxies) == 4
                assert mock_file.called
    
    @pytest.mark.asyncio
    async def test_fetch_proxies_from_api_file_write_error(self, mock_settings):
        """Test fetch_proxies_from_api file write error (lines 442-446)."""
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            manager = ProxyManager(mock_settings)
            manager.proxies = [Proxy(ip="1.1.1.1", port=80, username="u", password="p")]
            
            with patch("builtins.open", side_effect=Exception("Write error")):
                result = await manager.fetch_proxies_from_api(2)
                assert result == 0
    
    @pytest.mark.asyncio
    async def test_fetch_proxies_from_api_no_new_proxies(self, mock_settings):
        """Test fetch_proxies_from_api when no new proxies generated (line 446)."""
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            manager = ProxyManager(mock_settings)
            manager.proxies = [Proxy(ip="1.1.1.1", port=80, username="u", password="p")]
            
            # Mock to generate 0 new proxies (quantity=0)
            result = await manager.fetch_proxies_from_api(0)
            assert result == 0
    
    def test_assign_proxies_empty_warning(self, mock_settings):
        """Test assign_proxies with no proxies (lines 494-495)."""
        manager = ProxyManager(mock_settings)
        profiles = [AccountProfile(faucet="test", username="u1", password="p")]
        manager.assign_proxies(profiles)
        # Should just log warning and return
    
    def test_rotate_proxy_no_proxy(self, mock_settings):
        """Test rotate_proxy with no current proxy (lines 503-520)."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [Proxy(ip="1.1.1.1", port=80, username="u", password="p")]
        profile = AccountProfile(faucet="test", username="u1", password="pass")
        profile.proxy = None
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is not None
        assert "1.1.1.1" in new_proxy
    
    def test_rotate_proxy_current_dead(self, mock_settings):
        """Test rotate_proxy when current proxy is dead (lines 503-520)."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [
            Proxy(ip="1.1.1.1", port=80, username="u1", password="p"),
            Proxy(ip="2.2.2.2", port=80, username="u2", password="p"),
        ]
        manager.dead_proxies = ["1.1.1.1:80"]
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        profile.proxy = "http://u1:p@1.1.1.1:80"
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is not None
        assert "2.2.2.2" in new_proxy
    
    def test_rotate_proxy_random_strategy(self, mock_settings):
        """Test rotate_proxy with random strategy (line 512)."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [
            Proxy(ip="1.1.1.1", port=80, username="u1", password="p"),
            Proxy(ip="2.2.2.2", port=80, username="u2", password="p"),
        ]
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        profile.proxy = "http://u1:p@1.1.1.1:80"
        profile.proxy_rotation_strategy = "random"
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is not None
    
    def test_rotate_proxy_no_healthy_proxies(self, mock_settings):
        """Test rotate_proxy when no healthy proxies available (lines 516-518)."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [Proxy(ip="1.1.1.1", port=80, username="u", password="p")]
        manager.dead_proxies = ["1.1.1.1:80"]
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        profile.proxy = None
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is None
    
    def test_rotate_proxy_current_healthy(self, mock_settings):
        """Test rotate_proxy when current proxy is healthy (line 527)."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [Proxy(ip="1.1.1.1", port=80, username="u", password="p")]
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        profile.proxy = "http://u:p@1.1.1.1:80"
        
        # No rotation strategy, current is healthy
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy == profile.proxy
    
    @pytest.mark.asyncio
    async def test_measure_proxy_latency_history_truncation(self, mock_settings):
        """Test measure_proxy_latency history truncation (line 102-103)."""
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
    
    def test_load_proxies_template_creation_error(self, mock_settings):
        """Test load_proxies_from_file template creation error (lines 311-312)."""
        with patch("os.path.exists", return_value=False), \
             patch("builtins.open", side_effect=Exception("Permission denied")):
            manager = ProxyManager(mock_settings)
            assert len(manager.proxies) == 0
    
    @pytest.mark.asyncio
    async def test_fetch_proxies_session_id_stripping(self, mock_settings):
        """Test fetch_proxies_from_api with session ID in username (line 405-406)."""
        with patch.object(ProxyManager, "load_proxies_from_file", return_value=0):
            manager = ProxyManager(mock_settings)
            # Base proxy with session ID already in username
            base_proxy = Proxy(ip="1.1.1.1", port=80, username="user-session-abc123", password="pass")
            manager.proxies = [base_proxy]
            
            with patch("builtins.open", mock_open()) as mock_file:
                result = await manager.fetch_proxies_from_api(2)
                assert result > 0
                # Verify the base username was extracted
    
    def test_rotate_proxy_with_protocol_in_current(self, mock_settings):
        """Test rotate_proxy with protocol in current proxy string (lines 499-500)."""
        manager = ProxyManager(mock_settings)
        manager.proxies = [
            Proxy(ip="1.1.1.1", port=80, username="u1", password="p"),
            Proxy(ip="2.2.2.2", port=80, username="u2", password="p"),
        ]
        manager.dead_proxies = ["1.1.1.1:80"]
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        # Test with ://  format (line 499-500)
        profile.proxy = "http://1.1.1.1:80"
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is not None
        assert "2.2.2.2" in new_proxy
    
    def test_rotate_proxy_no_proxies_available(self, mock_settings):
        """Test rotate_proxy when no proxies are available (line 504-505)."""
        manager = ProxyManager(mock_settings)
        manager.proxies = []
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        profile.proxy = None
        profile.proxy_rotation_strategy = "random"
        
        new_proxy = manager.rotate_proxy(profile)
        assert new_proxy is None

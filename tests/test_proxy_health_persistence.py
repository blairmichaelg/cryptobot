import pytest
import json
import os
import time
from unittest.mock import patch, MagicMock
from core.proxy_manager import ProxyManager, Proxy
from core.config import BotSettings


@pytest.fixture
def temp_health_file(tmp_path):
    """Fixture for temporary health file."""
    return str(tmp_path / "proxy_health.json")


@pytest.fixture
def mock_settings(temp_health_file):
    """Mock BotSettings."""
    settings = MagicMock(spec=BotSettings)
    settings.twocaptcha_api_key = "test_key"
    settings.residential_proxies_file = "/tmp/proxies.txt"
    settings.use_2captcha_proxies = False
    return settings


class TestProxyHealthPersistence:
    
    def test_save_and_load_health_data(self, mock_settings, temp_health_file, tmp_path):
        """Test saving and loading proxy health data."""
        # Create manager with temp health file
        with patch("core.config.CONFIG_DIR", tmp_path):
            manager = ProxyManager(mock_settings)
            manager.health_file = temp_health_file
            
            # Add some health data
            manager.proxy_latency = {
                "proxy1:8080": [100.0, 150.0, 120.0],
                "proxy2:8080": [200.0, 250.0]
            }
            manager.proxy_failures = {"proxy1:8080": 1, "proxy2:8080": 2}
            manager.dead_proxies = ["proxy3:8080"]
            manager.proxy_cooldowns = {"proxy2:8080": time.time() + 300}
            
            # Save
            manager._save_health_data()
            
            # Verify file exists
            assert os.path.exists(temp_health_file)
            
            # Load in new manager
            manager2 = ProxyManager(mock_settings)
            manager2.health_file = temp_health_file
            manager2._load_health_data()
            
            # Verify data was loaded
            assert manager2.proxy_latency == manager.proxy_latency
            assert manager2.proxy_failures == manager.proxy_failures
            assert manager2.dead_proxies == manager.dead_proxies
            assert "proxy2:8080" in manager2.proxy_cooldowns
    
    def test_version_mismatch_ignores_data(self, mock_settings, temp_health_file, tmp_path):
        """Test that version mismatch causes data to be ignored."""
        # Create file with wrong version
        with open(temp_health_file, "w") as f:
            json.dump({
                "version": 999,
                "timestamp": time.time(),
                "proxy_latency": {"test": [100.0]}
            }, f)
        
        with patch("core.config.CONFIG_DIR", tmp_path):
            manager = ProxyManager(mock_settings)
            manager.health_file = temp_health_file
            manager._load_health_data()
            
            # Should be empty due to version mismatch
            assert manager.proxy_latency == {}
    
    def test_stale_data_ignored(self, mock_settings, temp_health_file, tmp_path):
        """Test that stale data is ignored."""
        # Create file with old timestamp
        with open(temp_health_file, "w") as f:
            json.dump({
                "version": 1,
                "timestamp": time.time() - (86400 * 8),  # 8 days old
                "proxy_latency": {"test": [100.0]}
            }, f)
        
        with patch("core.config.CONFIG_DIR", tmp_path):
            manager = ProxyManager(mock_settings)
            manager.health_file = temp_health_file
            manager._load_health_data()
            
            # Should be empty due to stale data
            assert manager.proxy_latency == {}
    
    def test_expired_cooldowns_cleaned(self, mock_settings, temp_health_file, tmp_path):
        """Test that expired cooldowns are cleaned on load."""
        # Create file with expired cooldown
        with open(temp_health_file, "w") as f:
            json.dump({
                "version": 1,
                "timestamp": time.time(),
                "proxy_latency": {},
                "proxy_failures": {},
                "dead_proxies": [],
                "proxy_cooldowns": {
                    "expired:8080": time.time() - 100,  # Expired
                    "active:8080": time.time() + 300     # Still active
                }
            }, f)
        
        with patch("core.config.CONFIG_DIR", tmp_path):
            manager = ProxyManager(mock_settings)
            manager.health_file = temp_health_file
            manager._load_health_data()
            
            # Expired should be removed, active should remain
            assert "expired:8080" not in manager.proxy_cooldowns
            assert "active:8080" in manager.proxy_cooldowns
    
    def test_corrupt_file_handled_gracefully(self, mock_settings, temp_health_file, tmp_path):
        """Test that corrupt file doesn't crash."""
        # Create corrupt file
        with open(temp_health_file, "w") as f:
            f.write("not valid json{")
        
        with patch("core.config.CONFIG_DIR", tmp_path):
            manager = ProxyManager(mock_settings)
            manager.health_file = temp_health_file
            # Should not raise exception
            manager._load_health_data()
            
            # Should start with empty data
            assert manager.proxy_latency == {}

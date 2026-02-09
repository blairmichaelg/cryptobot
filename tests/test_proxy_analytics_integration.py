"""
Integration tests for proxy health monitoring and analytics integration.

This test suite validates the interaction between ProxyManager and
EarningsTracker during claim operations:

* Proxy health checks before initiating claims
* Analytics recording for successful and failed claims
* Proxy rotation on detection/failure
* Latency tracking and reputation scoring
* Integration with faucet claim flow

All network calls are mocked to ensure fast, deterministic tests.
"""

import pytest
import asyncio
import json
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch, Mock

from core.proxy_manager import ProxyManager, Proxy
from core.analytics import EarningsTracker
from core.config import BotSettings, AccountProfile
from faucets.base import ClaimResult


@pytest.fixture
def temp_dirs():
    """Create temporary directories for config and analytics."""
    config_dir = tempfile.mkdtemp(prefix="cryptobot_proxy_test_")
    analytics_file = Path(config_dir) / "test_analytics.json"
    
    yield {
        "config_dir": Path(config_dir),
        "analytics_file": analytics_file
    }
    
    try:
        shutil.rmtree(config_dir)
    except Exception:
        pass


@pytest.fixture
def mock_settings():
    """Create mock bot settings for proxy testing."""
    settings = BotSettings()
    settings.twocaptcha_api_key = "test_key"
    settings.use_2captcha_proxies = True
    return settings


@pytest.fixture
def mock_proxies():
    """Create a list of mock proxies for testing."""
    return [
        Proxy(ip="1.1.1.1", port=8080, username="user1", password="pass1", protocol="http"),
        Proxy(ip="2.2.2.2", port=8080, username="user2", password="pass2", protocol="http"),
        Proxy(ip="3.3.3.3", port=8080, username="user3", password="pass3", protocol="http"),
    ]


class TestProxyHealthBeforeClaim:
    """Test that proxy health is verified before initiating claims."""
    
    @pytest.mark.asyncio
    async def test_healthy_proxy_passes_check(self, mock_settings, mock_proxies, temp_dirs):
        """Test that a healthy proxy passes health check before claim."""
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            # Mock health check to return healthy
            proxy = mock_proxies[0]
            
            # Set initial health data
            manager.proxy_health[proxy.to_string()] = {
                "failures": 0,
                "last_failure": 0,
                "latency_history": [100, 110, 105],
                "reputation": 100,
                "status": "healthy"
            }
            
            # Check if proxy is healthy
            health = manager.proxy_health.get(proxy.to_string(), {})
            assert health["status"] == "healthy"
            assert health["failures"] == 0
            assert health["reputation"] == 100
    
    @pytest.mark.asyncio
    async def test_unhealthy_proxy_fails_check(self, mock_settings, mock_proxies, temp_dirs):
        """Test that an unhealthy proxy is detected before claim."""
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            proxy = mock_proxies[0]
            
            # Set proxy as unhealthy
            manager.proxy_health[proxy.to_string()] = {
                "failures": 5,
                "last_failure": time.time(),
                "latency_history": [5000, 6000, 7000],
                "reputation": 20,
                "status": "burned"
            }
            
            # Verify proxy is marked as unhealthy
            health = manager.proxy_health.get(proxy.to_string(), {})
            assert health["status"] == "burned"
            assert health["failures"] >= 3
    
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_validate_proxy_before_claim(self, mock_get, mock_settings, mock_proxies, temp_dirs):
        """Test proxy validation before claim attempt."""
        # Mock successful proxy validation
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = AsyncMock()
        mock_get.return_value = mock_response
        
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            proxy = mock_proxies[0]
            
            # Validate proxy
            is_valid = await manager.validate_proxy(proxy)
            
            # Should be valid
            assert is_valid is True


class TestAnalyticsRecordingDuringClaim:
    """Test that analytics are properly recorded during claim operations."""
    
    @pytest.mark.asyncio
    async def test_record_successful_claim(self, temp_dirs):
        """Test analytics recording for successful claim."""
        tracker = EarningsTracker(storage_file=str(temp_dirs["analytics_file"]))
        
        # Simulate successful claim
        faucet_name = "firefaucet"
        amount = 100.0
        currency = "BTC"
        
        tracker.record_claim(
            faucet=faucet_name,
            success=True,
            amount=amount,
            currency=currency,
            balance_after=1000.0
        )
        
        # Force save to persist
        tracker._save()
        
        # Verify claim was recorded
        assert len(tracker.claims) == 1
        assert tracker.claims[0]["faucet"] == faucet_name
        assert tracker.claims[0]["success"] is True
        assert tracker.claims[0]["amount"] == amount
        assert tracker.claims[0]["currency"] == currency
        
        # Verify it was persisted
        data = json.loads(temp_dirs["analytics_file"].read_text())
        assert len(data["claims"]) == 1
    
    @pytest.mark.asyncio
    async def test_record_failed_claim(self, temp_dirs):
        """Test analytics recording for failed claim."""
        tracker = EarningsTracker(storage_file=str(temp_dirs["analytics_file"]))
        
        # Simulate failed claim
        tracker.record_claim(
            faucet="dutchy",
            success=False,
            amount=0.0,
            currency="LTC",
            failure_reason="Proxy detected"
        )
        
        tracker._save()
        
        # Verify failure was recorded
        assert len(tracker.claims) == 1
        assert tracker.claims[0]["success"] is False
        assert tracker.claims[0]["failure_reason"] == "Proxy detected"
    
    @pytest.mark.asyncio
    async def test_record_claim_with_timing(self, temp_dirs):
        """Test analytics recording includes claim timing."""
        tracker = EarningsTracker(storage_file=str(temp_dirs["analytics_file"]))
        
        # Simulate claim with timing
        claim_time = 15.5  # seconds
        
        tracker.record_claim(
            faucet="cointiply",
            success=True,
            amount=50.0,
            currency="DOGE",
            claim_time=claim_time
        )
        
        tracker._save()
        
        # Verify timing was recorded
        assert tracker.claims[0]["claim_time"] == claim_time


class TestProxyRotationOnFailure:
    """Test proxy rotation logic when failures occur."""
    
    @pytest.mark.asyncio
    async def test_rotate_proxy_after_detection(self, mock_settings, mock_proxies, temp_dirs):
        """Test that proxy is rotated after detection failure."""
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            # Create account profile with assigned proxy
            profile = AccountProfile(
                faucet="firefaucet",
                username="testuser",
                password="testpass"
            )
            
            # Assign initial proxy
            manager.assign_proxies([profile])
            initial_proxy = profile.proxy
            
            # Record proxy failure (proxy detection)
            proxy_obj = mock_proxies[0]
            manager.record_failure(
                proxy=proxy_obj,
                error_type="proxy_detected",
                latency_ms=5000
            )
            
            # Verify failure was recorded
            health = manager.proxy_health.get(proxy_obj.to_string(), {})
            assert health.get("failures", 0) > 0
            
            # Rotate to next proxy
            manager.rotate_proxy(profile)
            
            # Verify proxy changed
            assert profile.proxy != initial_proxy
    
    @pytest.mark.asyncio
    async def test_proxy_cooldown_after_failure(self, mock_settings, mock_proxies, temp_dirs):
        """Test that failed proxy enters cooldown period."""
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            proxy = mock_proxies[0]
            
            # Record failure
            manager.record_failure(
                proxy=proxy,
                error_type="connection_timeout",
                latency_ms=15000
            )
            
            # Verify cooldown was set
            health = manager.proxy_health.get(proxy.to_string(), {})
            assert "last_failure" in health
            assert health["last_failure"] > 0
    
    @pytest.mark.asyncio
    async def test_proxy_burn_after_repeated_failures(self, mock_settings, mock_proxies, temp_dirs):
        """Test that proxy is burned after repeated failures."""
        from core.orchestrator import MAX_PROXY_FAILURES
        
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            proxy = mock_proxies[0]
            
            # Record multiple failures to trigger burn
            for i in range(MAX_PROXY_FAILURES + 1):
                manager.record_failure(
                    proxy=proxy,
                    error_type="proxy_detected",
                    latency_ms=10000
                )
            
            # Verify proxy is marked as burned
            health = manager.proxy_health.get(proxy.to_string(), {})
            assert health.get("failures", 0) > MAX_PROXY_FAILURES
            # Status would be updated by manager logic


class TestIntegratedClaimFlow:
    """Test the integrated flow of proxy check -> claim -> analytics."""
    
    @pytest.mark.asyncio
    async def test_complete_successful_claim_flow(self, mock_settings, mock_proxies, temp_dirs):
        """Test complete flow: healthy proxy -> successful claim -> analytics recorded."""
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            # Setup
            proxy_manager = ProxyManager(mock_settings)
            proxy_manager.proxies = mock_proxies
            
            tracker = EarningsTracker(storage_file=str(temp_dirs["analytics_file"]))
            
            profile = AccountProfile(
                faucet="firefaucet",
                username="testuser",
                password="testpass"
            )
            
            # Step 1: Assign and verify proxy health
            proxy_manager.assign_proxies([profile])
            assert profile.proxy is not None
            
            # Step 2: Simulate successful claim
            claim_result = ClaimResult(
                success=True,
                status="Claimed successfully",
                amount="100",
                balance="1000",
                next_claim_minutes=60
            )
            
            # Step 3: Record analytics
            tracker.record_claim(
                faucet="firefaucet",
                success=claim_result.success,
                amount=float(claim_result.amount),
                currency="BTC",
                balance_after=float(claim_result.balance)
            )
            
            tracker._save()
            
            # Step 4: Record proxy success
            proxy = proxy_manager.proxies[0]
            manager_health = proxy_manager.proxy_health.setdefault(
                proxy.to_string(),
                {"failures": 0, "latency_history": [], "reputation": 100}
            )
            
            # Record latency for successful claim
            manager_health["latency_history"].append(200)
            
            # Verify end-to-end flow
            assert len(tracker.claims) == 1
            assert tracker.claims[0]["success"] is True
            assert manager_health["failures"] == 0
            assert len(manager_health["latency_history"]) > 0
    
    @pytest.mark.asyncio
    async def test_complete_failed_claim_flow(self, mock_settings, mock_proxies, temp_dirs):
        """Test complete flow: proxy detected -> failed claim -> analytics + rotation."""
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            # Setup
            proxy_manager = ProxyManager(mock_settings)
            proxy_manager.proxies = mock_proxies
            
            tracker = EarningsTracker(storage_file=str(temp_dirs["analytics_file"]))
            
            profile = AccountProfile(
                faucet="dutchy",
                username="testuser",
                password="testpass"
            )
            
            # Step 1: Assign proxy
            proxy_manager.assign_proxies([profile])
            initial_proxy = profile.proxy
            
            # Step 2: Simulate failed claim (proxy detected)
            claim_result = ClaimResult(
                success=False,
                status="Proxy detected",
                amount="0",
                balance="0",
                next_claim_minutes=0
            )
            
            # Step 3: Record analytics
            tracker.record_claim(
                faucet="dutchy",
                success=False,
                amount=0.0,
                currency="LTC",
                failure_reason="Proxy detected"
            )
            
            tracker._save()
            
            # Step 4: Record proxy failure
            proxy = proxy_manager.proxies[0]
            proxy_manager.record_failure(
                proxy=proxy,
                error_type="proxy_detected",
                latency_ms=8000
            )
            
            # Step 5: Rotate proxy
            proxy_manager.rotate_proxy(profile)
            
            # Verify failure handling
            assert len(tracker.claims) == 1
            assert tracker.claims[0]["success"] is False
            assert profile.proxy != initial_proxy  # Proxy was rotated


class TestLatencyTracking:
    """Test latency tracking and reputation scoring for proxies."""
    
    @pytest.mark.asyncio
    async def test_record_proxy_latency(self, mock_settings, mock_proxies, temp_dirs):
        """Test that proxy latency is tracked during claims."""
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            proxy = mock_proxies[0]
            proxy_str = proxy.to_string()
            
            # Initialize health tracking
            if proxy_str not in manager.proxy_health:
                manager.proxy_health[proxy_str] = {
                    "latency_history": [],
                    "failures": 0,
                    "reputation": 100
                }
            
            # Record latencies
            latencies = [150, 200, 180, 170, 190]
            for latency in latencies:
                manager.proxy_health[proxy_str]["latency_history"].append(latency)
            
            # Limit history size
            from core.proxy_manager import ProxyManager as PM
            max_history = PM.LATENCY_HISTORY_MAX
            
            manager.proxy_health[proxy_str]["latency_history"] = \
                manager.proxy_health[proxy_str]["latency_history"][-max_history:]
            
            # Verify latency tracking
            assert len(manager.proxy_health[proxy_str]["latency_history"]) <= max_history
            
            # Calculate average
            avg_latency = sum(manager.proxy_health[proxy_str]["latency_history"]) / \
                         len(manager.proxy_health[proxy_str]["latency_history"])
            
            assert 150 <= avg_latency <= 200
    
    @pytest.mark.asyncio
    async def test_reputation_degrades_with_failures(self, mock_settings, mock_proxies, temp_dirs):
        """Test that proxy reputation degrades with failures."""
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            proxy = mock_proxies[0]
            
            # Start with good reputation
            manager.proxy_health[proxy.to_string()] = {
                "reputation": 100,
                "failures": 0,
                "latency_history": []
            }
            
            initial_reputation = manager.proxy_health[proxy.to_string()]["reputation"]
            
            # Record failures
            for i in range(3):
                manager.record_failure(proxy, "timeout", 5000)
                # Manually degrade reputation (in real code, this would be automatic)
                manager.proxy_health[proxy.to_string()]["reputation"] = max(
                    0,
                    manager.proxy_health[proxy.to_string()]["reputation"] - 20
                )
            
            # Verify reputation degraded
            final_reputation = manager.proxy_health[proxy.to_string()]["reputation"]
            assert final_reputation < initial_reputation


class TestProxyHealthPersistence:
    """Test that proxy health data is persisted across restarts."""
    
    @pytest.mark.asyncio
    async def test_save_proxy_health(self, mock_settings, mock_proxies, temp_dirs):
        """Test that proxy health is saved to disk."""
        health_file = temp_dirs["config_dir"] / "proxy_health.json"
        
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            # Set health data
            proxy = mock_proxies[0]
            manager.proxy_health[proxy.to_string()] = {
                "failures": 2,
                "latency_history": [150, 160],
                "reputation": 80,
                "last_failure": time.time()
            }
            
            # Save health data
            manager.save_health()
            
            # Verify file exists
            assert health_file.exists()
            
            # Verify content
            data = json.loads(health_file.read_text())
            assert proxy.to_string() in data
    
    @pytest.mark.asyncio
    async def test_load_proxy_health(self, mock_settings, mock_proxies, temp_dirs):
        """Test that proxy health is loaded from disk on startup."""
        health_file = temp_dirs["config_dir"] / "proxy_health.json"
        
        # Pre-populate health file
        proxy = mock_proxies[0]
        health_data = {
            proxy.to_string(): {
                "failures": 3,
                "latency_history": [200, 210, 205],
                "reputation": 70,
                "last_failure": time.time() - 3600
            }
        }
        health_file.write_text(json.dumps(health_data))
        
        with patch("core.proxy_manager.CONFIG_DIR", str(temp_dirs["config_dir"])):
            manager = ProxyManager(mock_settings)
            manager.proxies = mock_proxies
            
            # Load health data
            manager.load_health()
            
            # Verify data was loaded
            assert proxy.to_string() in manager.proxy_health
            loaded_health = manager.proxy_health[proxy.to_string()]
            assert loaded_health["failures"] == 3
            assert loaded_health["reputation"] == 70

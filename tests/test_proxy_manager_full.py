"""Comprehensive tests for core.proxy_manager covering all uncovered methods
and edge cases not present in existing test files.

Focuses on: Proxy dataclass edge cases, internal helpers, health data
persistence, parsing, reputation/signals, geolocation, assignment edge
cases, rotation strategies, auto-provisioning, and refresh logic.
"""
import asyncio
import json
import os
import random
import time
from unittest.mock import (
    AsyncMock,
    MagicMock,
    mock_open,
    patch,
)

import pytest

from core.proxy_manager import Proxy, ProxyManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(**overrides):
    """Create a mock BotSettings with sensible defaults."""
    s = MagicMock()
    s.twocaptcha_api_key = overrides.get("twocaptcha_api_key", "test_api_key")
    s.use_2captcha_proxies = overrides.get("use_2captcha_proxies", True)
    s.proxy_provider = overrides.get("proxy_provider", "2captcha")
    s.residential_proxies_file = overrides.get(
        "residential_proxies_file", "config/proxies.txt",
    )
    s.azure_proxies_file = overrides.get(
        "azure_proxies_file", "config/azure_proxies.txt",
    )
    s.digitalocean_proxies_file = overrides.get(
        "digitalocean_proxies_file", "config/do_proxies.txt",
    )
    s.use_azure_proxies = overrides.get("use_azure_proxies", False)
    s.use_digitalocean_proxies = overrides.get("use_digitalocean_proxies", False)
    s.zyte_api_key = overrides.get("zyte_api_key", None)
    s.zyte_proxy_host = overrides.get("zyte_proxy_host", "api.zyte.com")
    s.zyte_proxy_port = overrides.get("zyte_proxy_port", 8011)
    s.zyte_proxy_protocol = overrides.get("zyte_proxy_protocol", "http")
    s.zyte_pool_size = overrides.get("zyte_pool_size", 20)
    s.proxy_validation_timeout_seconds = overrides.get(
        "proxy_validation_timeout_seconds", 15,
    )
    s.proxy_validation_url = overrides.get(
        "proxy_validation_url", "https://www.google.com",
    )
    s.proxy_bypass_faucets = overrides.get(
        "proxy_bypass_faucets", ["freebitcoin"],
    )
    s.proxy_reputation_enabled = overrides.get(
        "proxy_reputation_enabled", True,
    )
    s.proxy_reputation_min_score = overrides.get(
        "proxy_reputation_min_score", 20.0,
    )
    s.webshare_api_key = overrides.get("webshare_api_key", None)
    s.webshare_page_size = overrides.get("webshare_page_size", 50)
    return s


def _make_manager(**settings_overrides):
    """Instantiate ProxyManager with file/health IO mocked out."""
    settings = _make_settings(**settings_overrides)
    with patch.object(ProxyManager, "load_proxies_from_file", return_value=0), \
         patch.object(ProxyManager, "_load_health_data"):
        mgr = ProxyManager(settings)
    return mgr


def _make_profile(faucet="test", username="user1", password="pw", **kw):
    """Create a mock AccountProfile."""
    p = MagicMock()
    p.faucet = faucet
    p.username = username
    p.password = password
    p.proxy = kw.get("proxy", None)
    p.residential_proxy = kw.get("residential_proxy", False)
    p.proxy_rotation_strategy = kw.get("proxy_rotation_strategy", "round_robin")
    return p


# ===================================================================
# 1. Proxy dataclass edge cases
# ===================================================================

class TestProxyDataclass:
    """Edge-case tests for the Proxy dataclass formatting methods."""

    def test_to_string_with_username_no_password(self):
        """to_string should include 'user:@ip:port' when password is empty."""
        p = Proxy(ip="host.com", port=8080, username="apikey", password="")
        result = p.to_string()
        assert result == "http://apikey:@host.com:8080"

    def test_to_string_with_https_protocol(self):
        p = Proxy(ip="s.io", port=443, username="u", password="p", protocol="https")
        assert result := p.to_string()
        assert result.startswith("https://")

    def test_to_2captcha_string_username_only(self):
        """If username is set but password is empty, to_2captcha_string
        should return ip:port only (both username AND password required)."""
        p = Proxy(ip="1.2.3.4", port=80, username="user", password="")
        assert p.to_2captcha_string() == "1.2.3.4:80"

    def test_to_2captcha_string_password_only(self):
        """If password is set but username is empty, return ip:port."""
        p = Proxy(ip="1.2.3.4", port=80, username="", password="secret")
        assert p.to_2captcha_string() == "1.2.3.4:80"

    def test_to_string_no_auth(self):
        p = Proxy(ip="10.0.0.1", port=3128, username="", password="")
        assert p.to_string() == "http://10.0.0.1:3128"

    def test_to_2captcha_string_full_auth(self):
        p = Proxy(ip="x.com", port=9000, username="a", password="b")
        assert p.to_2captcha_string() == "a:b@x.com:9000"


# ===================================================================
# 2. _mask_proxy_key
# ===================================================================

class TestMaskProxyKey:
    def test_mask_zyte_api_key(self):
        mgr = _make_manager(proxy_provider="zyte", zyte_api_key="ZYTEKEY123")
        result = mgr._mask_proxy_key("ZYTEKEY123:@api.zyte.com:8011")
        assert "ZYTEKEY123" not in result
        assert "***" in result

    def test_mask_2captcha_api_key(self):
        mgr = _make_manager(
            proxy_provider="2captcha",
            twocaptcha_api_key="CAP_KEY_XYZ",
        )
        result = mgr._mask_proxy_key("CAP_KEY_XYZ:pass@host:80")
        assert "CAP_KEY_XYZ" not in result
        assert "***" in result

    def test_mask_no_match(self):
        mgr = _make_manager(proxy_provider="2captcha", twocaptcha_api_key="KEY")
        result = mgr._mask_proxy_key("someuser:pass@host:80")
        assert result == "someuser:pass@host:80"

    def test_mask_none_api_key(self):
        mgr = _make_manager(proxy_provider="2captcha", twocaptcha_api_key=None)
        # api_key is None so should pass through
        result = mgr._mask_proxy_key("u:p@h:80")
        assert result == "u:p@h:80"

    def test_mask_zyte_no_key(self):
        mgr = _make_manager(proxy_provider="zyte", zyte_api_key=None)
        result = mgr._mask_proxy_key("u:p@h:80")
        assert result == "u:p@h:80"


# ===================================================================
# 3. _proxy_host_port_from_str
# ===================================================================

class TestProxyHostPortFromStr:
    def test_full_url(self):
        mgr = _make_manager()
        assert mgr._proxy_host_port_from_str("http://u:p@1.2.3.4:8080") == "1.2.3.4:8080"

    def test_bare_host_port(self):
        mgr = _make_manager()
        assert mgr._proxy_host_port_from_str("10.0.0.1:3128") == "10.0.0.1:3128"

    def test_with_auth_no_protocol(self):
        mgr = _make_manager()
        assert mgr._proxy_host_port_from_str("user:pass@host.com:8080") == "host.com:8080"

    def test_empty_string(self):
        mgr = _make_manager()
        assert mgr._proxy_host_port_from_str("") == ""

    def test_none_input(self):
        mgr = _make_manager()
        assert mgr._proxy_host_port_from_str(None) == ""

    def test_no_port(self):
        mgr = _make_manager()
        # urlparse with no port returns None, so result is empty
        assert mgr._proxy_host_port_from_str("http://host.com") == ""

    def test_https_protocol(self):
        mgr = _make_manager()
        assert mgr._proxy_host_port_from_str("https://h:443") == "h:443"


# ===================================================================
# 4. _proxy_host_port (from Proxy object)
# ===================================================================

class TestProxyHostPort:
    def test_basic(self):
        mgr = _make_manager()
        p = Proxy(ip="1.2.3.4", port=8080, username="", password="")
        assert mgr._proxy_host_port(p) == "1.2.3.4:8080"


# ===================================================================
# 5. _load_health_data
# ===================================================================

class TestLoadHealthData:
    def test_no_file(self):
        """Should silently skip when no health file exists."""
        mgr = _make_manager()
        with patch("os.path.exists", return_value=False):
            mgr._load_health_data()
        assert mgr.proxy_latency == {}

    def test_version_mismatch(self):
        """Should ignore data with a different version number."""
        mgr = _make_manager()
        bad_data = {"version": 999, "timestamp": time.time()}
        with patch("os.path.exists", return_value=True), \
             patch("core.proxy_manager.safe_json_read", return_value=bad_data):
            mgr._load_health_data()
        assert mgr.proxy_latency == {}

    def test_stale_data(self):
        """Should ignore data older than HEALTH_DATA_MAX_AGE."""
        mgr = _make_manager()
        old_ts = time.time() - (mgr.HEALTH_DATA_MAX_AGE + 100)
        stale_data = {"version": 1, "timestamp": old_ts}
        with patch("os.path.exists", return_value=True), \
             patch("core.proxy_manager.safe_json_read", return_value=stale_data):
            mgr._load_health_data()
        assert mgr.proxy_latency == {}

    def test_successful_load(self):
        """Should populate manager state from valid data."""
        mgr = _make_manager()
        now = time.time()
        health = {
            "version": 1,
            "timestamp": now,
            "proxy_latency": {"k1": [100.0]},
            "proxy_failures": {"k1": 2},
            "dead_proxies": ["k2"],
            "proxy_cooldowns": {"k3": now + 3600},
            "proxy_reputation": {"k1": 80.0},
            "proxy_soft_signals": {"k1": {"blocked": 1}},
            "proxy_host_failures": {"h:80": 1},
        }
        with patch("os.path.exists", return_value=True), \
             patch("core.proxy_manager.safe_json_read", return_value=health):
            mgr._load_health_data()
        assert mgr.proxy_latency == {"k1": [100.0]}
        assert mgr.proxy_failures == {"k1": 2}
        assert mgr.dead_proxies == ["k2"]
        assert "k3" in mgr.proxy_cooldowns
        assert mgr.proxy_reputation == {"k1": 80.0}
        assert mgr.proxy_soft_signals == {"k1": {"blocked": 1}}
        assert mgr.proxy_host_failures == {"h:80": 1}

    def test_expired_cooldowns_cleaned(self):
        """Expired cooldowns should be removed during load."""
        mgr = _make_manager()
        now = time.time()
        health = {
            "version": 1,
            "timestamp": now,
            "proxy_latency": {},
            "proxy_failures": {},
            "dead_proxies": [],
            "proxy_cooldowns": {
                "expired": now - 100,    # expired
                "active": now + 9999,    # still active
            },
            "proxy_reputation": {},
            "proxy_soft_signals": {},
            "proxy_host_failures": {},
        }
        with patch("os.path.exists", return_value=True), \
             patch("core.proxy_manager.safe_json_read", return_value=health):
            mgr._load_health_data()
        assert "expired" not in mgr.proxy_cooldowns
        assert "active" in mgr.proxy_cooldowns

    def test_empty_data_returned(self):
        """safe_json_read returning None/empty dict should be handled."""
        mgr = _make_manager()
        with patch("os.path.exists", return_value=True), \
             patch("core.proxy_manager.safe_json_read", return_value=None):
            mgr._load_health_data()  # should not raise
        assert mgr.proxy_latency == {}

    def test_json_corruption(self):
        """Should handle JSON decode errors gracefully."""
        mgr = _make_manager()
        with patch("os.path.exists", return_value=True), \
             patch("core.proxy_manager.safe_json_read", side_effect=json.JSONDecodeError("bad", "", 0)):
            # The method catches JSONDecodeError internally; safe_json_read
            # itself handles corruption, but if the error propagates,
            # _load_health_data catches it.
            mgr._load_health_data()
        assert mgr.proxy_latency == {}


# ===================================================================
# 6. _save_health_data
# ===================================================================

class TestSaveHealthData:
    def test_basic_save(self):
        mgr = _make_manager()
        mgr.proxy_latency = {"k": [100.0]}
        mgr.proxy_failures = {"k": 1}
        mgr.dead_proxies = ["d"]
        with patch("core.proxy_manager.safe_json_write") as mock_write:
            mgr._save_health_data()
            mock_write.assert_called_once()
            saved_data = mock_write.call_args[0][1]
            assert saved_data["version"] == mgr.HEALTH_FILE_VERSION
            assert "timestamp" in saved_data
            assert saved_data["proxy_latency"] == {"k": [100.0]}
            assert saved_data["dead_proxies"] == ["d"]

    def test_save_exception_handled(self):
        mgr = _make_manager()
        with patch("core.proxy_manager.safe_json_write", side_effect=OSError("disk full")):
            mgr._save_health_data()  # should not raise


# ===================================================================
# 7. _prune_health_data_for_active_proxies
# ===================================================================

class TestPruneHealthData:
    def test_empty_list_no_op(self):
        mgr = _make_manager()
        mgr.proxy_latency = {"stale_key": [200]}
        mgr._prune_health_data_for_active_proxies([])
        # No active proxies => early return, data untouched
        assert "stale_key" in mgr.proxy_latency

    def test_prunes_stale_keys(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        key = mgr._proxy_key(p)
        mgr.proxy_latency = {key: [100], "stale": [200]}
        mgr.proxy_failures = {key: 0, "stale": 5}
        mgr.dead_proxies = [key, "stale"]
        with patch("core.proxy_manager.safe_json_write"):
            mgr._prune_health_data_for_active_proxies([p])
        assert "stale" not in mgr.proxy_latency
        assert "stale" not in mgr.proxy_failures
        assert "stale" not in mgr.dead_proxies
        assert key in mgr.proxy_latency

    def test_all_in_cooldown_releases_one(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        k2 = mgr._proxy_key(p2)
        now = time.time()
        mgr.proxy_cooldowns = {k1: now + 100, k2: now + 200}
        mgr.proxy_failures = {k1: 3, k2: 5}
        with patch("core.proxy_manager.safe_json_write"):
            mgr._prune_health_data_for_active_proxies([p1, p2])
        # The oldest cooldown (k1) should have been released
        assert k1 not in mgr.proxy_cooldowns
        assert mgr.proxy_failures.get(k1) == 0


# ===================================================================
# 8. _parse_proxy_string
# ===================================================================

class TestParseProxyString:
    def test_full_http_url(self):
        mgr = _make_manager()
        p = mgr._parse_proxy_string("http://user:pass@host.com:8080")
        assert p is not None
        assert p.ip == "host.com"
        assert p.port == 8080
        assert p.username == "user"
        assert p.password == "pass"
        assert p.protocol == "http"

    def test_https_url(self):
        mgr = _make_manager()
        p = mgr._parse_proxy_string("https://u:p@s.io:443")
        assert p is not None
        assert p.protocol == "https"
        assert p.port == 443

    def test_no_protocol(self):
        mgr = _make_manager()
        p = mgr._parse_proxy_string("user:pass@1.2.3.4:3128")
        assert p is not None
        assert p.protocol == "http"
        assert p.username == "user"
        assert p.password == "pass"

    def test_no_auth(self):
        mgr = _make_manager()
        p = mgr._parse_proxy_string("http://10.0.0.1:9090")
        assert p is not None
        assert p.username == ""
        assert p.password == ""
        assert p.ip == "10.0.0.1"
        assert p.port == 9090

    def test_bare_host_port(self):
        mgr = _make_manager()
        p = mgr._parse_proxy_string("5.5.5.5:1080")
        assert p is not None
        assert p.ip == "5.5.5.5"
        assert p.port == 1080
        assert p.username == ""

    def test_invalid_no_port(self):
        mgr = _make_manager()
        p = mgr._parse_proxy_string("http://host.com")
        assert p is None

    def test_invalid_garbage(self):
        mgr = _make_manager()
        p = mgr._parse_proxy_string("not_a_proxy")
        assert p is None

    def test_password_with_colon(self):
        mgr = _make_manager()
        p = mgr._parse_proxy_string("http://user:p:a:ss@h:80")
        assert p is not None
        assert p.username == "user"
        assert p.password == "p:a:ss"


# ===================================================================
# 9. record_soft_signal
# ===================================================================

class TestRecordSoftSignal:
    def test_blocked_signal(self):
        mgr = _make_manager()
        with patch("core.proxy_manager.safe_json_write"):
            mgr.record_soft_signal("u:p@h:80", signal_type="blocked")
        assert mgr.proxy_soft_signals["u:p@h:80"]["blocked"] == 1
        assert mgr.proxy_reputation["u:p@h:80"] == 95.0  # 100 - 5

    def test_captcha_spike_signal(self):
        mgr = _make_manager()
        with patch("core.proxy_manager.safe_json_write"):
            mgr.record_soft_signal("k", signal_type="captcha_spike")
        assert mgr.proxy_reputation["k"] == 95.0

    def test_unknown_signal(self):
        mgr = _make_manager()
        with patch("core.proxy_manager.safe_json_write"):
            mgr.record_soft_signal("k", signal_type="slow_response")
        assert mgr.proxy_reputation["k"] == 97.5  # 100 - 2.5

    def test_multiple_signals_accumulate(self):
        mgr = _make_manager()
        with patch("core.proxy_manager.safe_json_write"):
            mgr.record_soft_signal("k", signal_type="blocked")
            mgr.record_soft_signal("k", signal_type="blocked")
        assert mgr.proxy_soft_signals["k"]["blocked"] == 2
        # 100 - 5 (first) -> 95 - 5 (second) -> 90
        assert mgr.proxy_reputation["k"] == 90.0

    def test_signal_strips_protocol(self):
        mgr = _make_manager()
        with patch("core.proxy_manager.safe_json_write"):
            mgr.record_soft_signal("http://u:p@h:80", signal_type="blocked")
        assert "u:p@h:80" in mgr.proxy_soft_signals
        assert "http://u:p@h:80" not in mgr.proxy_soft_signals

    def test_reputation_floor_at_zero(self):
        mgr = _make_manager()
        mgr.proxy_reputation["k"] = 2.0
        with patch("core.proxy_manager.safe_json_write"):
            mgr.record_soft_signal("k", signal_type="blocked")  # -5
        assert mgr.proxy_reputation["k"] == 0.0


# ===================================================================
# 10. get_proxy_reputation
# ===================================================================

class TestGetProxyReputation:
    def test_default_reputation(self):
        mgr = _make_manager()
        score = mgr.get_proxy_reputation("unknown_key")
        assert score == 100.0

    def test_latency_penalty(self):
        mgr = _make_manager()
        mgr.proxy_latency["k"] = [2000.0]  # avg 2000ms -> penalty = min(2000/100, 20) = 20
        score = mgr.get_proxy_reputation("k")
        assert score == 80.0

    def test_failure_penalty(self):
        mgr = _make_manager()
        mgr.proxy_failures["k"] = 4  # penalty = min(4*5, 30) = 20
        score = mgr.get_proxy_reputation("k")
        assert score == 80.0

    def test_soft_signal_penalty(self):
        mgr = _make_manager()
        mgr.proxy_soft_signals["k"] = {"blocked": 4}  # sum=4, penalty = min(4*1.5, 30) = 6
        score = mgr.get_proxy_reputation("k")
        assert score == 94.0

    def test_combined_penalties(self):
        mgr = _make_manager()
        mgr.proxy_latency["k"] = [1000.0]   # -10
        mgr.proxy_failures["k"] = 2          # -10
        mgr.proxy_soft_signals["k"] = {"blocked": 2}  # -3
        score = mgr.get_proxy_reputation("k")
        assert score == 77.0

    def test_strips_protocol(self):
        mgr = _make_manager()
        mgr.proxy_latency["u:p@h:80"] = [500.0]
        score = mgr.get_proxy_reputation("http://u:p@h:80")
        assert score < 100.0

    def test_max_penalties_capped(self):
        mgr = _make_manager()
        mgr.proxy_latency["k"] = [99999.0]
        mgr.proxy_failures["k"] = 100
        mgr.proxy_soft_signals["k"] = {"blocked": 100}
        score = mgr.get_proxy_reputation("k")
        # latency cap 20 + failure cap 30 + signal cap 30 = 80 off from 100
        assert score == 20.0


# ===================================================================
# 11. get_proxy_stats
# ===================================================================

class TestGetProxyStats:
    def test_no_latency_data(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        stats = mgr.get_proxy_stats(p)
        assert stats["avg_latency"] is None
        assert stats["min_latency"] is None
        assert stats["max_latency"] is None
        assert stats["measurement_count"] == 0
        assert stats["is_dead"] is False
        assert "reputation_score" in stats

    def test_with_latency_data(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        key = mgr._proxy_key(p)
        mgr.proxy_latency[key] = [100.0, 200.0, 300.0]
        stats = mgr.get_proxy_stats(p)
        assert stats["avg_latency"] == 200.0
        assert stats["min_latency"] == 100.0
        assert stats["max_latency"] == 300.0
        assert stats["measurement_count"] == 3
        assert stats["is_dead"] is False

    def test_dead_proxy_stat(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        key = mgr._proxy_key(p)
        mgr.dead_proxies.append(key)
        stats = mgr.get_proxy_stats(p)
        assert stats["is_dead"] is True


# ===================================================================
# 12. health_check_all_proxies
# ===================================================================

class TestHealthCheckAllProxies:
    async def test_empty_pool(self):
        mgr = _make_manager()
        mgr.proxies = []
        result = await mgr.health_check_all_proxies()
        assert result == {"total": 0, "healthy": 0, "dead": 0}

    async def test_mixed_results(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        p3 = Proxy(ip="3.3.3.3", port=80, username="u3", password="p")
        mgr.proxies = [p1, p2, p3]

        async def fake_latency(proxy):
            if proxy.ip == "2.2.2.2":
                return None  # failure
            return 100.0

        with patch.object(mgr, "measure_proxy_latency", side_effect=fake_latency):
            result = await mgr.health_check_all_proxies()
        assert result["total"] == 3
        assert result["healthy"] == 2
        assert result["avg_latency_ms"] == 100.0


# ===================================================================
# 13. remove_dead_proxies
# ===================================================================

class TestRemoveDeadProxies:
    def test_salvage_when_all_dead(self):
        """When all proxies are dead, at least one should be salvaged."""
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        k2 = mgr._proxy_key(p2)
        mgr.all_proxies = [p1, p2]
        mgr.proxies = [p1, p2]
        # Put both in cooldown
        now = time.time()
        mgr.proxy_cooldowns = {k1: now + 3600, k2: now + 7200}
        with patch("core.proxy_manager.safe_json_write"):
            mgr.remove_dead_proxies()
        # Should have at least 1 proxy salvaged
        assert len(mgr.proxies) >= 1

    def test_expired_cooldown_restored(self):
        """Expired cooldowns should be cleaned up and proxy restored."""
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        key = mgr._proxy_key(p)
        mgr.all_proxies = [p]
        mgr.proxies = [p]
        mgr.proxy_cooldowns = {key: time.time() - 100}  # expired
        mgr.proxy_failures = {key: 5}
        mgr.remove_dead_proxies()
        assert key not in mgr.proxy_cooldowns
        assert mgr.proxy_failures[key] == 0
        assert len(mgr.proxies) == 1

    def test_slow_proxy_removed(self):
        """Proxies with avg latency above threshold should be removed."""
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        mgr.all_proxies = [p1, p2]
        mgr.proxies = [p1, p2]
        # Give p1 very high latencies (3 measurements required)
        mgr.proxy_latency[k1] = [8000, 9000, 10000]
        removed = mgr.remove_dead_proxies()
        assert removed == 1
        remaining_ips = [p.ip for p in mgr.proxies]
        assert "2.2.2.2" in remaining_ips

    def test_low_reputation_cooldown(self):
        """Proxy with reputation below min should be put in cooldown."""
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        good_p = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        key = mgr._proxy_key(p)
        mgr.all_proxies = [p, good_p]
        mgr.proxies = [p, good_p]
        mgr.proxy_reputation[key] = 5.0  # below min_score=20
        removed = mgr.remove_dead_proxies()
        # p should be in cooldown, good_p stays
        assert removed == 1
        assert len(mgr.proxies) == 1


# ===================================================================
# 14. rotate_session_id
# ===================================================================

class TestRotateSessionId:
    def test_no_existing_session(self):
        mgr = _make_manager()
        result = mgr.rotate_session_id("baseuser")
        assert result.startswith("baseuser-session-")
        session_part = result.split("-session-")[1]
        assert len(session_part) == 8

    def test_existing_session_replaced(self):
        mgr = _make_manager()
        result = mgr.rotate_session_id("baseuser-session-oldid123")
        assert result.startswith("baseuser-session-")
        assert "oldid123" not in result

    def test_generates_unique_ids(self):
        mgr = _make_manager()
        results = {mgr.rotate_session_id("u") for _ in range(20)}
        # Should generate many unique IDs (statistically impossible to get all same)
        assert len(results) > 1


# ===================================================================
# 15. generate_whitelist_proxies - no API key
# ===================================================================

class TestGenerateWhitelistProxies:
    async def test_no_api_key(self):
        mgr = _make_manager(twocaptcha_api_key=None)
        mgr.api_key = None
        result = await mgr.generate_whitelist_proxies()
        assert result is False


# ===================================================================
# 16. fetch_proxies_from_provider
# ===================================================================

class TestFetchProxiesFromProvider:
    async def test_unsupported_provider(self):
        mgr = _make_manager(proxy_provider="azure")
        mgr.proxy_provider = "azure"
        result = await mgr.fetch_proxies_from_provider()
        assert result == 0

    async def test_webshare_no_api_key(self):
        mgr = _make_manager(proxy_provider="webshare", webshare_api_key=None)
        mgr.proxy_provider = "webshare"
        mgr.settings.webshare_api_key = None
        result = await mgr.fetch_proxies_from_provider()
        assert result == 0

    async def test_webshare_success(self):
        mgr = _make_manager(proxy_provider="webshare", webshare_api_key="ws_key")
        mgr.proxy_provider = "webshare"
        mgr.settings.webshare_api_key = "ws_key"
        mgr.settings.webshare_page_size = 50

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "results": [
                {"proxy_address": "1.1.1.1", "port": 8080, "username": "u", "password": "p"},
                {"proxy_address": "2.2.2.2", "port": 9090, "username": "u2", "password": "p2"},
            ]
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session), \
             patch("builtins.open", mock_open()), \
             patch("os.path.abspath", return_value="/tmp/proxies.txt"):
            result = await mgr.fetch_proxies_from_provider(quantity=2)
        assert result == 2
        assert len(mgr.proxies) == 2

    async def test_webshare_api_failure(self):
        mgr = _make_manager(proxy_provider="webshare", webshare_api_key="ws_key")
        mgr.proxy_provider = "webshare"
        mgr.settings.webshare_api_key = "ws_key"
        mgr.settings.webshare_page_size = 50

        mock_resp = AsyncMock()
        mock_resp.status = 403
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.fetch_proxies_from_provider(quantity=5)
        assert result == 0

    async def test_webshare_no_results(self):
        mgr = _make_manager(proxy_provider="webshare", webshare_api_key="ws_key")
        mgr.proxy_provider = "webshare"
        mgr.settings.webshare_api_key = "ws_key"
        mgr.settings.webshare_page_size = 50

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"results": []})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.fetch_proxies_from_provider(quantity=5)
        assert result == 0

    async def test_webshare_network_error(self):
        mgr = _make_manager(proxy_provider="webshare", webshare_api_key="ws_key")
        mgr.proxy_provider = "webshare"
        mgr.settings.webshare_api_key = "ws_key"
        mgr.settings.webshare_page_size = 50

        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=Exception("network error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.fetch_proxies_from_provider(quantity=5)
        assert result == 0


# ===================================================================
# 17. auto_provision_proxies
# ===================================================================

class TestAutoProvisionProxies:
    async def test_above_threshold(self):
        mgr = _make_manager()
        mgr.proxies = [
            Proxy(ip=f"1.1.1.{i}", port=80, username="u", password="p")
            for i in range(15)
        ]
        result = await mgr.auto_provision_proxies(min_threshold=10)
        assert result == 0

    async def test_below_threshold_triggers_fetch(self):
        mgr = _make_manager()
        mgr.proxies = [
            Proxy(ip="1.1.1.1", port=80, username="u", password="p"),
        ]
        with patch.object(mgr, "fetch_proxies_from_api", new_callable=AsyncMock, return_value=5):
            result = await mgr.auto_provision_proxies(min_threshold=10, provision_count=5)
        assert result == 5

    async def test_unsupported_provider(self):
        mgr = _make_manager(proxy_provider="azure")
        mgr.proxy_provider = "azure"
        mgr.proxies = []
        result = await mgr.auto_provision_proxies(min_threshold=10)
        assert result == 0

    async def test_fetch_failure(self):
        mgr = _make_manager()
        mgr.proxies = []
        with patch.object(mgr, "fetch_proxies_from_api", new_callable=AsyncMock, side_effect=Exception("fail")):
            result = await mgr.auto_provision_proxies(min_threshold=10)
        assert result == 0


# ===================================================================
# 18. auto_remove_dead_proxies
# ===================================================================

class TestAutoRemoveDeadProxies:
    async def test_removes_dead(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        mgr.proxies = [p1, p2]
        mgr.dead_proxies = [k1]
        with patch("core.proxy_manager.safe_json_write"):
            removed = await mgr.auto_remove_dead_proxies()
        assert removed == 1
        assert len(mgr.proxies) == 1

    async def test_removes_by_failure_count(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        key = mgr._proxy_key(p)
        mgr.proxies = [p]
        mgr.proxy_failures = {key: 5}
        with patch("core.proxy_manager.safe_json_write"):
            removed = await mgr.auto_remove_dead_proxies(failure_threshold=3)
        assert removed == 1
        assert len(mgr.proxies) == 0
        assert key in mgr.dead_proxies

    async def test_no_removals(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.proxies = [p]
        mgr.dead_proxies = []
        removed = await mgr.auto_remove_dead_proxies()
        assert removed == 0


# ===================================================================
# 19. auto_refresh_proxies
# ===================================================================

class TestAutoRefreshProxies:
    async def test_non_2captcha_skips(self):
        mgr = _make_manager(proxy_provider="zyte")
        mgr.proxy_provider = "zyte"
        result = await mgr.auto_refresh_proxies()
        assert result is True

    async def test_healthy_pool_no_refresh(self):
        mgr = _make_manager()
        with patch.object(mgr, "health_check_all_proxies", new_callable=AsyncMock,
                          return_value={"healthy": 60, "total": 60}):
            result = await mgr.auto_refresh_proxies(min_healthy_count=50)
        assert result is True

    async def test_low_pool_triggers_refresh(self):
        mgr = _make_manager()
        health_call_count = 0

        async def fake_health():
            nonlocal health_call_count
            health_call_count += 1
            if health_call_count == 1:
                return {"healthy": 10, "total": 20}
            return {"healthy": 80, "total": 100}

        with patch.object(mgr, "health_check_all_proxies", new_callable=AsyncMock, side_effect=fake_health), \
             patch.object(mgr, "fetch_2captcha_proxies", new_callable=AsyncMock, return_value=50), \
             patch("core.proxy_manager.safe_json_write"):
            result = await mgr.auto_refresh_proxies(min_healthy_count=50, target_count=100)
        assert result is True

    async def test_refresh_fetch_fails(self):
        mgr = _make_manager()
        with patch.object(mgr, "health_check_all_proxies", new_callable=AsyncMock,
                          return_value={"healthy": 5, "total": 10}), \
             patch.object(mgr, "fetch_2captcha_proxies", new_callable=AsyncMock, return_value=0):
            result = await mgr.auto_refresh_proxies(min_healthy_count=50)
        assert result is False

    async def test_refresh_exception(self):
        mgr = _make_manager()
        with patch.object(mgr, "health_check_all_proxies", new_callable=AsyncMock,
                          return_value={"healthy": 5, "total": 10}), \
             patch.object(mgr, "fetch_2captcha_proxies", new_callable=AsyncMock,
                          side_effect=Exception("network error")):
            result = await mgr.auto_refresh_proxies(min_healthy_count=50)
        assert result is False


# ===================================================================
# 20. get_refresh_schedule_info
# ===================================================================

class TestGetRefreshScheduleInfo:
    def test_2captcha_provider(self):
        mgr = _make_manager(proxy_provider="2captcha")
        info = mgr.get_refresh_schedule_info()
        assert info["enabled"] is True
        assert info["provider"] == "2captcha"
        assert info["recommended_interval_hours"] == 24
        assert "health_file" in info

    def test_zyte_provider(self):
        mgr = _make_manager(proxy_provider="zyte")
        mgr.proxy_provider = "zyte"
        info = mgr.get_refresh_schedule_info()
        assert info["enabled"] is False
        assert info["provider"] == "zyte"


# ===================================================================
# 21. get_proxy_geolocation
# ===================================================================

class TestGetProxyGeolocation:
    async def test_success_us(self):
        mgr = _make_manager()
        p = Proxy(ip="1.2.3.4", port=80, username="", password="")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "timezone": "America/New_York",
            "countryCode": "US",
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.get_proxy_geolocation(p)
        assert result == ("America/New_York", "en-US")

    async def test_success_de(self):
        mgr = _make_manager()
        p = Proxy(ip="5.5.5.5", port=80, username="", password="")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "timezone": "Europe/Berlin",
            "countryCode": "DE",
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.get_proxy_geolocation(p)
        assert result == ("Europe/Berlin", "de-DE")

    async def test_success_unknown_country(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="", password="")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "timezone": "Africa/Lagos",
            "countryCode": "NG",
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.get_proxy_geolocation(p)
        assert result == ("Africa/Lagos", "en-US")

    async def test_failure_non_200(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="", password="")

        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.get_proxy_geolocation(p)
        assert result is None

    async def test_network_exception(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="", password="")

        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=Exception("timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.get_proxy_geolocation(p)
        assert result is None

    async def test_no_timezone_in_response(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="", password="")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "countryCode": "US",
        })
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await mgr.get_proxy_geolocation(p)
        assert result is None


# ===================================================================
# 22. get_geolocation_for_proxy
# ===================================================================

class TestGetGeolocationForProxy:
    async def test_none_input(self):
        mgr = _make_manager()
        result = await mgr.get_geolocation_for_proxy(None)
        assert result is None

    async def test_empty_string(self):
        mgr = _make_manager()
        result = await mgr.get_geolocation_for_proxy("")
        assert result is None

    async def test_full_url(self):
        mgr = _make_manager()
        with patch.object(mgr, "get_proxy_geolocation", new_callable=AsyncMock,
                          return_value=("America/Chicago", "en-US")):
            result = await mgr.get_geolocation_for_proxy("http://u:p@1.2.3.4:8080")
        assert result == ("America/Chicago", "en-US")

    async def test_bare_host_port(self):
        mgr = _make_manager()
        with patch.object(mgr, "get_proxy_geolocation", new_callable=AsyncMock,
                          return_value=("Europe/London", "en-GB")):
            result = await mgr.get_geolocation_for_proxy("10.0.0.1:3128")
        assert result == ("Europe/London", "en-GB")

    async def test_auth_no_protocol(self):
        mgr = _make_manager()
        with patch.object(mgr, "get_proxy_geolocation", new_callable=AsyncMock,
                          return_value=("Asia/Tokyo", "ja-JP")):
            result = await mgr.get_geolocation_for_proxy("user:pass@jp.proxy.com:9090")
        assert result == ("Asia/Tokyo", "ja-JP")


# ===================================================================
# 23. assign_proxies edge cases
# ===================================================================

class TestAssignProxiesEdgeCases:
    def test_no_proxies_loaded(self):
        mgr = _make_manager()
        mgr.proxies = []
        profiles = [_make_profile()]
        mgr.assign_proxies(profiles)
        # No crash; proxy should remain unchanged
        assert profiles[0].proxy is None

    def test_bypass_faucet(self):
        mgr = _make_manager(proxy_bypass_faucets=["freebitcoin"])
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.proxies = [p]
        profile = _make_profile(faucet="freebitcoin", username="user1")
        mgr.assign_proxies([profile])
        assert profile.proxy is None
        assert profile.residential_proxy is False

    def test_dead_proxies_filtered(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        mgr.proxies = [p1, p2]
        mgr.dead_proxies = [k1]
        profile = _make_profile(faucet="test", username="user1")
        mgr.assign_proxies([profile])
        assert "2.2.2.2" in profile.proxy

    def test_cooldown_proxies_filtered(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        mgr.proxies = [p1, p2]
        mgr.proxy_cooldowns = {k1: time.time() + 9999}
        profile = _make_profile(faucet="test", username="user1")
        mgr.assign_proxies([profile])
        assert "2.2.2.2" in profile.proxy

    def test_session_proxies_preferred(self):
        mgr = _make_manager()
        p_normal = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p_session = Proxy(ip="2.2.2.2", port=80, username="u1-session-abc123", password="p")
        mgr.proxies = [p_normal, p_session]
        profile = _make_profile(faucet="test", username="user1")
        mgr.assign_proxies([profile])
        assert "-session-" in profile.proxy

    def test_all_dead_no_assignment(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        key = mgr._proxy_key(p)
        mgr.proxies = [p]
        mgr.dead_proxies = [key]
        profile = _make_profile(faucet="test", username="user1")
        mgr.assign_proxies([profile])
        # proxy field should remain None (not assigned)
        assert profile.proxy is None

    def test_host_level_cooldown_filtered(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        host_port = mgr._proxy_host_port(p)
        mgr.proxies = [p, p2]
        mgr.proxy_cooldowns = {host_port: time.time() + 9999}
        profile = _make_profile(faucet="test", username="user1")
        mgr.assign_proxies([profile])
        assert "2.2.2.2" in profile.proxy

    def test_round_robin_wraps(self):
        mgr = _make_manager(proxy_bypass_faucets=[])
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        mgr.proxies = [p1, p2]
        profiles = [
            _make_profile(faucet="a", username="user1"),
            _make_profile(faucet="b", username="user2"),
            _make_profile(faucet="c", username="user3"),
        ]
        mgr.assign_proxies(profiles)
        assert "1.1.1.1" in profiles[0].proxy
        assert "2.2.2.2" in profiles[1].proxy
        assert "1.1.1.1" in profiles[2].proxy  # wraps around


# ===================================================================
# 24. record_failure edge cases
# ===================================================================

class TestRecordFailureEdgeCases:
    def test_detection_cooldown(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.all_proxies = [p]
        mgr.proxies = [p]
        with patch("core.proxy_manager.safe_json_write"), \
             patch("asyncio.create_task"):
            mgr.record_failure("http://u:p@1.1.1.1:80", detected=True)
        key = "u:p@1.1.1.1:80"
        assert key in mgr.proxy_cooldowns
        assert mgr.proxy_cooldowns[key] > time.time()

    def test_403_triggers_cooldown(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.all_proxies = [p]
        mgr.proxies = [p]
        with patch("core.proxy_manager.safe_json_write"), \
             patch("asyncio.create_task"):
            mgr.record_failure("http://u:p@1.1.1.1:80", status_code=403)
        key = "u:p@1.1.1.1:80"
        assert key in mgr.proxy_cooldowns

    def test_host_level_cooldown_after_threshold(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.all_proxies = [p]
        mgr.proxies = [p]
        host = "1.1.1.1:80"
        with patch("core.proxy_manager.safe_json_write"), \
             patch("asyncio.create_task"):
            for _ in range(mgr.HOST_DETECTION_THRESHOLD):
                mgr.record_failure("http://u:p@1.1.1.1:80", detected=True)
        assert host in mgr.proxy_cooldowns

    def test_dead_proxy_after_failures(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.all_proxies = [p]
        mgr.proxies = [p]
        with patch("core.proxy_manager.safe_json_write"), \
             patch("asyncio.create_task"):
            for _ in range(mgr.DEAD_PROXY_FAILURE_COUNT):
                mgr.record_failure("http://u:p@1.1.1.1:80")
        key = "u:p@1.1.1.1:80"
        assert key in mgr.dead_proxies

    def test_reputation_penalty_detected(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.all_proxies = [p]
        mgr.proxies = [p]
        with patch("core.proxy_manager.safe_json_write"), \
             patch("asyncio.create_task"):
            mgr.record_failure("http://u:p@1.1.1.1:80", detected=True)
        key = "u:p@1.1.1.1:80"
        assert mgr.proxy_reputation[key] == 85.0  # 100 - 15

    def test_reputation_penalty_normal(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.all_proxies = [p]
        mgr.proxies = [p]
        with patch("core.proxy_manager.safe_json_write"), \
             patch("asyncio.create_task"):
            mgr.record_failure("http://u:p@1.1.1.1:80")
        key = "u:p@1.1.1.1:80"
        assert mgr.proxy_reputation[key] == 95.0  # 100 - 5

    def test_pool_replenishment_triggered(self):
        mgr = _make_manager()
        mgr.proxies = []  # critically low
        mgr.settings.use_2captcha_proxies = True
        with patch("core.proxy_manager.safe_json_write"), \
             patch("asyncio.create_task") as mock_task:
            mgr.record_failure("http://u:p@1.1.1.1:80")
        mock_task.assert_called_once()

    def test_pool_replenishment_not_triggered_above_threshold(self):
        mgr = _make_manager()
        mgr.proxies = [
            Proxy(ip=f"1.1.1.{i}", port=80, username="u", password="p")
            for i in range(5)
        ]
        mgr.all_proxies = list(mgr.proxies)
        with patch("core.proxy_manager.safe_json_write"), \
             patch("asyncio.create_task") as mock_task:
            mgr.record_failure("http://u:p@1.1.1.1:80")
        mock_task.assert_not_called()


# ===================================================================
# 25. rotate_proxy strategies
# ===================================================================

class TestRotateProxy:
    def test_no_rotation_needed(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.proxies = [p]
        profile = _make_profile(proxy="http://u:p@1.1.1.1:80")
        profile.proxy_rotation_strategy = "round_robin"
        result = mgr.rotate_proxy(profile)
        assert result == "http://u:p@1.1.1.1:80"

    def test_health_based_strategy(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        mgr.proxies = [p1, p2]
        k1 = mgr._proxy_key(p1)
        k2 = mgr._proxy_key(p2)
        # Give p2 a better reputation
        mgr.proxy_reputation[k1] = 30.0
        mgr.proxy_reputation[k2] = 90.0
        profile = _make_profile(proxy=None)
        profile.proxy_rotation_strategy = "health_based"
        result = mgr.rotate_proxy(profile)
        assert result is not None
        assert "2.2.2.2" in result

    def test_random_strategy(self):
        mgr = _make_manager()
        proxies = [
            Proxy(ip=f"1.1.1.{i}", port=80, username=f"u{i}", password="p")
            for i in range(10)
        ]
        mgr.proxies = proxies
        profile = _make_profile(proxy="http://u0:p@1.1.1.0:80")
        profile.proxy_rotation_strategy = "random"
        result = mgr.rotate_proxy(profile)
        assert result is not None

    def test_rotate_when_dead(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        mgr.proxies = [p1, p2]
        mgr.dead_proxies = [k1]
        profile = _make_profile(proxy="http://u1:p@1.1.1.1:80")
        profile.proxy_rotation_strategy = "round_robin"
        result = mgr.rotate_proxy(profile)
        assert result is not None
        assert "2.2.2.2" in result

    def test_rotate_no_healthy(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        key = mgr._proxy_key(p)
        mgr.proxies = [p]
        mgr.dead_proxies = [key]
        profile = _make_profile(proxy="http://u:p@1.1.1.1:80")
        profile.proxy_rotation_strategy = "round_robin"
        result = mgr.rotate_proxy(profile)
        assert result is None
        assert profile.proxy is None

    def test_rotate_no_proxies_at_all(self):
        mgr = _make_manager()
        mgr.proxies = []
        profile = _make_profile(proxy=None)
        profile.proxy_rotation_strategy = "round_robin"
        result = mgr.rotate_proxy(profile)
        assert result is None

    def test_rotate_in_cooldown(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        mgr.proxies = [p1, p2]
        mgr.proxy_cooldowns = {k1: time.time() + 9999}
        profile = _make_profile(proxy="http://u1:p@1.1.1.1:80")
        profile.proxy_rotation_strategy = "round_robin"
        result = mgr.rotate_proxy(profile)
        assert result is not None
        assert "2.2.2.2" in result

    def test_rotate_low_reputation(self):
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        p2 = Proxy(ip="2.2.2.2", port=80, username="u2", password="p")
        k1 = mgr._proxy_key(p1)
        mgr.proxies = [p1, p2]
        mgr.proxy_reputation[k1] = 5.0  # below min 20
        profile = _make_profile(proxy="http://u1:p@1.1.1.1:80")
        profile.proxy_rotation_strategy = "round_robin"
        result = mgr.rotate_proxy(profile)
        assert result is not None
        assert "2.2.2.2" in result

    def test_rotate_cooldown_salvage(self):
        """When all healthy proxies are in cooldown, salvage info is reported."""
        mgr = _make_manager()
        p1 = Proxy(ip="1.1.1.1", port=80, username="u1", password="p")
        k1 = mgr._proxy_key(p1)
        mgr.proxies = [p1]
        mgr.proxy_cooldowns = {k1: time.time() + 9999}
        # Current proxy is also in cooldown
        profile = _make_profile(proxy="http://u1:p@1.1.1.1:80")
        profile.proxy_rotation_strategy = "round_robin"
        result = mgr.rotate_proxy(profile)
        assert result is None


# ===================================================================
# Extra: _build_zyte_proxies
# ===================================================================

class TestBuildZyteProxies:
    def test_no_api_key(self):
        mgr = _make_manager(proxy_provider="zyte", zyte_api_key=None)
        mgr.zyte_api_key = None
        result = mgr._build_zyte_proxies(5)
        assert result == 0

    def test_builds_proxies(self):
        mgr = _make_manager(proxy_provider="zyte", zyte_api_key="ZYTEKEY")
        mgr.zyte_api_key = "ZYTEKEY"
        with patch("core.proxy_manager.safe_json_write"):
            result = mgr._build_zyte_proxies(3)
        assert result == 3
        assert len(mgr.proxies) == 3
        assert mgr.proxies[0].username == "ZYTEKEY"
        assert mgr.proxies[0].password == ""

    def test_minimum_one(self):
        mgr = _make_manager(proxy_provider="zyte", zyte_api_key="KEY")
        mgr.zyte_api_key = "KEY"
        with patch("core.proxy_manager.safe_json_write"):
            result = mgr._build_zyte_proxies(0)
        assert result == 1


# ===================================================================
# Extra: get_proxy_for_solver
# ===================================================================

class TestGetProxyForSolver:
    def test_non_2captcha_returns_none(self):
        mgr = _make_manager(proxy_provider="zyte")
        mgr.proxy_provider = "zyte"
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.assignments["user1"] = p
        assert mgr.get_proxy_for_solver("user1") is None

    def test_existing_assignment(self):
        mgr = _make_manager()
        p = Proxy(ip="1.1.1.1", port=80, username="u", password="p")
        mgr.assignments["user1"] = p
        assert mgr.get_proxy_for_solver("user1") == "u:p@1.1.1.1:80"

    def test_unknown_user(self):
        mgr = _make_manager()
        assert mgr.get_proxy_for_solver("nonexistent") is None


# ===================================================================
# Extra: _proxy_key
# ===================================================================

class TestProxyKey:
    def test_with_auth(self):
        mgr = _make_manager()
        p = Proxy(ip="h.com", port=80, username="u", password="p")
        assert mgr._proxy_key(p) == "u:p@h.com:80"

    def test_no_auth(self):
        mgr = _make_manager()
        p = Proxy(ip="h.com", port=80, username="", password="")
        assert mgr._proxy_key(p) == "h.com:80"

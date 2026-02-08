"""
Comprehensive test suite for browser/instance.py BrowserManager class.

Fills coverage gaps not addressed by test_browser_instance_coverage.py.
Focuses on:
- _safe_json_write backup rotation edge cases
- _safe_json_read fallback chains
- _normalize_proxy_key with various URL schemes
- _proxy_host_port extraction
- _is_proxy_blacklisted with dead proxies, cooldowns, edge cases
- save_proxy_binding / load_proxy_binding / remove_proxy_binding
- save_profile_fingerprint / load_profile_fingerprint with deterministic seeds
- _seed_cookie_jar realistic cookie generation
- safe_close_context with alive/dead/timed-out contexts
- check_page_alive with various page states
- check_page_status HTTP status detection
- check_context_alive with alive/closed/frozen contexts
- safe_new_page with health pre-check
- create_context with proxies, fingerprints, locale/timezone overrides
- launch with GeoIP error fallback
- close, check_health, restart, new_page, save_cookies, load_cookies
- create_stealth_browser factory helper
"""

import pytest
import asyncio
import json
import os
import tempfile
import shutil
import time
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def safe_tmp_path():
    """Create a temp directory in user's temp folder to avoid Windows PermissionError."""
    temp_dir = tempfile.mkdtemp(prefix="cryptobot_test_full_")
    yield Path(temp_dir)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


@pytest.fixture
def manager():
    """Return a BrowserManager with encrypted cookies disabled (avoids Fernet init)."""
    from browser.instance import BrowserManager
    return BrowserManager(use_encrypted_cookies=False)


@pytest.fixture
def manager_with_tmp(safe_tmp_path):
    """Return a BrowserManager that uses safe_tmp_path as CONFIG_DIR."""
    from browser.instance import BrowserManager
    mgr = BrowserManager(use_encrypted_cookies=False)
    return mgr, safe_tmp_path


# ===========================================================================
# 1. _safe_json_write -- backup rotation details
# ===========================================================================

class TestSafeJsonWriteBackupRotation:
    """Test backup creation, rotation limits, and verification step."""

    def test_backup_contents_match_previous_primary(self, safe_tmp_path):
        """After two writes, backup.1 should hold the first write's data."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        fp = str(safe_tmp_path / "data.json")

        mgr._safe_json_write(fp, {"v": 1})
        mgr._safe_json_write(fp, {"v": 2})

        with open(fp + ".backup.1", "r", encoding="utf-8") as f:
            assert json.load(f) == {"v": 1}
        with open(fp, "r", encoding="utf-8") as f:
            assert json.load(f) == {"v": 2}

    def test_backup_rotation_chain_three_generations(self, safe_tmp_path):
        """Writing four times should produce backup.1=v3, backup.2=v2, backup.3=v1."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        fp = str(safe_tmp_path / "data.json")

        for v in range(1, 5):
            mgr._safe_json_write(fp, {"v": v})

        with open(fp, "r", encoding="utf-8") as f:
            assert json.load(f) == {"v": 4}
        with open(fp + ".backup.1", "r", encoding="utf-8") as f:
            assert json.load(f) == {"v": 3}
        with open(fp + ".backup.2", "r", encoding="utf-8") as f:
            assert json.load(f) == {"v": 2}
        with open(fp + ".backup.3", "r", encoding="utf-8") as f:
            assert json.load(f) == {"v": 1}

    def test_backup_rotation_custom_max_backups(self, safe_tmp_path):
        """Respect a custom max_backups=2 (only .backup.1 and .backup.2)."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        fp = str(safe_tmp_path / "data.json")

        for v in range(1, 6):
            mgr._safe_json_write(fp, {"v": v}, max_backups=2)

        assert os.path.exists(fp + ".backup.1")
        assert os.path.exists(fp + ".backup.2")
        # backup.3 should NOT exist when max_backups=2
        assert not os.path.exists(fp + ".backup.3")

    def test_temp_file_cleaned_up(self, safe_tmp_path):
        """After a successful write, no .tmp file should remain."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        fp = str(safe_tmp_path / "data.json")

        mgr._safe_json_write(fp, {"ok": True})

        assert not os.path.exists(fp + ".tmp")
        assert os.path.exists(fp)

    def test_write_error_does_not_raise(self, safe_tmp_path):
        """Writing to invalid path should log error, not raise."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        # Use a path that will trigger os.makedirs to fail on Windows
        # by writing to a file as if it were a directory
        blocker_file = str(safe_tmp_path / "blocker")
        with open(blocker_file, "w") as f:
            f.write("x")
        bad_path = os.path.join(blocker_file, "sub", "data.json")
        # Should not raise
        mgr._safe_json_write(bad_path, {"x": 1})


# ===========================================================================
# 2. _safe_json_read -- fallback chain details
# ===========================================================================

class TestSafeJsonReadFallback:
    """Test fallback through backup chain and custom max_backups."""

    def test_fallback_to_backup_2(self, safe_tmp_path):
        """When primary and backup.1 are corrupt, fall back to backup.2."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        fp = str(safe_tmp_path / "data.json")

        with open(fp, "w") as f:
            f.write("bad")
        with open(fp + ".backup.1", "w") as f:
            f.write("also bad")
        with open(fp + ".backup.2", "w") as f:
            json.dump({"source": "backup2"}, f)

        result = mgr._safe_json_read(fp)
        assert result == {"source": "backup2"}

    def test_fallback_to_backup_3(self, safe_tmp_path):
        """When primary, backup.1, backup.2 are corrupt, fall back to backup.3."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        fp = str(safe_tmp_path / "data.json")

        for suffix in ["", ".backup.1", ".backup.2"]:
            with open(fp + suffix, "w") as f:
                f.write("{corrupt")
        with open(fp + ".backup.3", "w") as f:
            json.dump({"source": "backup3"}, f)

        result = mgr._safe_json_read(fp)
        assert result == {"source": "backup3"}

    def test_custom_max_backups_limits_search(self, safe_tmp_path):
        """With max_backups=1, only primary and backup.1 are tried."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        fp = str(safe_tmp_path / "data.json")

        with open(fp, "w") as f:
            f.write("bad")
        with open(fp + ".backup.1", "w") as f:
            f.write("bad")
        # This would be found with max_backups=2 but not max_backups=1
        with open(fp + ".backup.2", "w") as f:
            json.dump({"source": "backup2"}, f)

        result = mgr._safe_json_read(fp, max_backups=1)
        assert result is None

    def test_read_returns_first_valid_candidate(self, safe_tmp_path):
        """When primary is valid, backups are not even attempted."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        fp = str(safe_tmp_path / "data.json")

        with open(fp, "w") as f:
            json.dump({"primary": True}, f)
        with open(fp + ".backup.1", "w") as f:
            json.dump({"backup": True}, f)

        result = mgr._safe_json_read(fp)
        assert result == {"primary": True}


# ===========================================================================
# 3. _normalize_proxy_key
# ===========================================================================

class TestNormalizeProxyKey:
    """Test scheme stripping from proxy URLs."""

    def test_http_scheme(self, manager):
        assert manager._normalize_proxy_key("http://user:pass@host:8080") == "user:pass@host:8080"

    def test_https_scheme(self, manager):
        assert manager._normalize_proxy_key("https://host:443") == "host:443"

    def test_socks5_scheme(self, manager):
        assert manager._normalize_proxy_key("socks5://proxy:1080") == "proxy:1080"

    def test_no_scheme(self, manager):
        assert manager._normalize_proxy_key("user:pass@host:8080") == "user:pass@host:8080"

    def test_empty_string(self, manager):
        assert manager._normalize_proxy_key("") == ""

    def test_none_input(self, manager):
        assert manager._normalize_proxy_key(None) == ""

    def test_double_scheme(self, manager):
        """Only the first :// should be split on."""
        result = manager._normalize_proxy_key("http://a://b")
        assert result == "a://b"


# ===========================================================================
# 4. _proxy_host_port
# ===========================================================================

class TestProxyHostPort:
    """Test host:port extraction from various proxy URL formats."""

    def test_full_http_url(self, manager):
        result = manager._proxy_host_port("http://user:pass@1.2.3.4:8080")
        assert result == "1.2.3.4:8080"

    def test_plain_host_port(self, manager):
        """Without scheme, the method prepends http:// internally."""
        result = manager._proxy_host_port("user:pass@10.0.0.1:3128")
        assert result == "10.0.0.1:3128"

    def test_socks5_url(self, manager):
        result = manager._proxy_host_port("socks5://proxy.example.com:1080")
        assert result == "proxy.example.com:1080"

    def test_empty_string(self, manager):
        assert manager._proxy_host_port("") == ""

    def test_none_input(self, manager):
        assert manager._proxy_host_port(None) == ""

    def test_no_port_returns_empty(self, manager):
        """URL without explicit port -> parsed.port is None -> empty."""
        result = manager._proxy_host_port("http://example.com")
        assert result == ""

    def test_hostname_only_no_scheme(self, manager):
        """Plain hostname without port should return empty."""
        result = manager._proxy_host_port("example.com")
        assert result == ""


# ===========================================================================
# 5. _is_proxy_blacklisted
# ===========================================================================

class TestIsProxyBlacklisted:
    """Test proxy health checking against proxy_health.json."""

    def test_no_health_file_returns_false(self, manager, safe_tmp_path):
        """When no proxy_health.json exists, proxy is not blacklisted."""
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            assert manager._is_proxy_blacklisted("http://a:b@host:1080") is False

    def test_empty_health_data_returns_false(self, manager, safe_tmp_path):
        """Empty health file -> not blacklisted."""
        health_file = safe_tmp_path / "proxy_health.json"
        with open(str(health_file), "w") as f:
            json.dump({}, f)
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            assert manager._is_proxy_blacklisted("http://host:1080") is False

    def test_dead_proxy_by_key(self, manager, safe_tmp_path):
        """Proxy listed in dead_proxies by normalized key is blacklisted."""
        health_file = safe_tmp_path / "proxy_health.json"
        with open(str(health_file), "w") as f:
            json.dump({"dead_proxies": ["user:pass@host:1080"]}, f)
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            assert manager._is_proxy_blacklisted("http://user:pass@host:1080") is True

    def test_dead_proxy_by_host_port(self, manager, safe_tmp_path):
        """Proxy listed in dead_proxies by host:port is blacklisted."""
        health_file = safe_tmp_path / "proxy_health.json"
        with open(str(health_file), "w") as f:
            json.dump({"dead_proxies": ["host:1080"]}, f)
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            assert manager._is_proxy_blacklisted("http://user:pass@host:1080") is True

    def test_active_cooldown_is_blacklisted(self, manager, safe_tmp_path):
        """Proxy with a future cooldown timestamp is blacklisted."""
        health_file = safe_tmp_path / "proxy_health.json"
        future_ts = time.time() + 3600
        with open(str(health_file), "w") as f:
            json.dump({"proxy_cooldowns": {"user:pass@host:1080": future_ts}}, f)
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            assert manager._is_proxy_blacklisted("http://user:pass@host:1080") is True

    def test_expired_cooldown_not_blacklisted(self, manager, safe_tmp_path):
        """Proxy with a past cooldown timestamp is NOT blacklisted."""
        health_file = safe_tmp_path / "proxy_health.json"
        past_ts = time.time() - 3600
        with open(str(health_file), "w") as f:
            json.dump({"proxy_cooldowns": {"user:pass@host:1080": past_ts}}, f)
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            assert manager._is_proxy_blacklisted("http://user:pass@host:1080") is False

    def test_cooldown_by_host_port(self, manager, safe_tmp_path):
        """Cooldown keyed by host:port also triggers blacklist."""
        health_file = safe_tmp_path / "proxy_health.json"
        future_ts = time.time() + 3600
        with open(str(health_file), "w") as f:
            json.dump({"proxy_cooldowns": {"host:1080": future_ts}}, f)
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            assert manager._is_proxy_blacklisted("http://user:pass@host:1080") is True

    def test_empty_proxy_string_returns_false(self, manager, safe_tmp_path):
        """Empty proxy key after normalization -> not blacklisted."""
        health_file = safe_tmp_path / "proxy_health.json"
        with open(str(health_file), "w") as f:
            json.dump({"dead_proxies": ["some:proxy"]}, f)
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            assert manager._is_proxy_blacklisted("") is False


# ===========================================================================
# 6. Proxy binding persistence
# ===========================================================================

class TestProxyBindingPersistence:
    """Test save/load/remove proxy binding round-trip."""

    @pytest.fixture(autouse=True)
    def _patch_config_dir(self, safe_tmp_path):
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            self.tmp = safe_tmp_path
            yield

    async def test_save_and_load_binding(self, manager):
        await manager.save_proxy_binding("profile_a", "http://p:p@h:1080")
        result = await manager.load_proxy_binding("profile_a")
        assert result == "http://p:p@h:1080"

    async def test_load_missing_binding_returns_none(self, manager):
        result = await manager.load_proxy_binding("nonexistent")
        assert result is None

    async def test_remove_binding(self, manager):
        await manager.save_proxy_binding("rm_me", "http://proxy:1080")
        await manager.remove_proxy_binding("rm_me")
        result = await manager.load_proxy_binding("rm_me")
        assert result is None

    async def test_remove_nonexistent_binding_is_noop(self, manager):
        """Removing a key that does not exist should not raise."""
        await manager.remove_proxy_binding("nope")

    async def test_remove_when_no_file_is_noop(self, manager):
        """Removing when proxy_bindings.json does not exist should not raise."""
        await manager.remove_proxy_binding("anything")

    async def test_multiple_profiles_independent(self, manager):
        await manager.save_proxy_binding("alpha", "http://alpha:1080")
        await manager.save_proxy_binding("beta", "http://beta:1080")

        assert await manager.load_proxy_binding("alpha") == "http://alpha:1080"
        assert await manager.load_proxy_binding("beta") == "http://beta:1080"

        await manager.remove_proxy_binding("alpha")
        assert await manager.load_proxy_binding("alpha") is None
        assert await manager.load_proxy_binding("beta") == "http://beta:1080"


# ===========================================================================
# 7. Fingerprint persistence
# ===========================================================================

class TestFingerprintPersistence:
    """Test save/load profile fingerprint with deterministic defaults."""

    @pytest.fixture(autouse=True)
    def _patch_config_dir(self, safe_tmp_path):
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            self.tmp = safe_tmp_path
            yield

    async def test_save_and_load_fingerprint(self, manager):
        await manager.save_profile_fingerprint(
            "test_profile", "en-US", "America/New_York",
            canvas_seed=42, gpu_index=3, audio_seed=99,
        )
        fp = await manager.load_profile_fingerprint("test_profile")
        assert fp is not None
        assert fp["locale"] == "en-US"
        assert fp["timezone_id"] == "America/New_York"
        assert fp["canvas_seed"] == 42
        assert fp["gpu_index"] == 3
        assert fp["audio_seed"] == 99

    async def test_deterministic_defaults_from_profile_name(self, manager):
        """When canvas_seed/gpu_index/audio_seed are None, they derive from profile name hash."""
        await manager.save_profile_fingerprint(
            "myprofile", "en-GB", "Europe/London",
        )
        fp = await manager.load_profile_fingerprint("myprofile")
        assert fp is not None
        assert fp["canvas_seed"] == hash("myprofile") % 1000000
        assert fp["gpu_index"] == hash("myprofile_gpu") % 17
        assert fp["audio_seed"] == hash("myprofile_audio") % 1000000
        assert fp["platform"] == "Win32"
        assert fp["languages"] == ["en-GB", "en"]

    async def test_load_missing_profile_returns_none(self, manager):
        result = await manager.load_profile_fingerprint("nope")
        assert result is None

    async def test_load_no_file_returns_none(self, manager):
        result = await manager.load_profile_fingerprint("nope")
        assert result is None

    async def test_viewport_dimensions_saved(self, manager):
        await manager.save_profile_fingerprint(
            "vp_profile", "en-US", "America/Chicago",
            viewport_width=1920, viewport_height=1080,
            device_scale_factor=1.5,
        )
        fp = await manager.load_profile_fingerprint("vp_profile")
        assert fp["viewport_width"] == 1920
        assert fp["viewport_height"] == 1080
        assert fp["device_scale_factor"] == 1.5

    async def test_overwrite_existing_profile(self, manager):
        await manager.save_profile_fingerprint(
            "overwrite_me", "en-US", "America/New_York",
            canvas_seed=1,
        )
        await manager.save_profile_fingerprint(
            "overwrite_me", "de-DE", "Europe/Berlin",
            canvas_seed=2,
        )
        fp = await manager.load_profile_fingerprint("overwrite_me")
        assert fp["locale"] == "de-DE"
        assert fp["canvas_seed"] == 2


# ===========================================================================
# 8. _seed_cookie_jar
# ===========================================================================

class TestSeedCookieJar:
    """Test realistic cookie seeding into a mock context."""

    @pytest.fixture(autouse=True)
    def _patch_config_dir(self, safe_tmp_path):
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            self.tmp = safe_tmp_path
            yield

    async def test_seeds_cookies_into_context(self, manager):
        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()
        await manager._seed_cookie_jar(ctx, "seed_test")
        ctx.add_cookies.assert_called_once()
        cookies = ctx.add_cookies.call_args[0][0]
        assert len(cookies) > 0

    async def test_cookie_has_required_fields(self, manager):
        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()
        await manager._seed_cookie_jar(ctx, "field_test")
        cookies = ctx.add_cookies.call_args[0][0]
        for c in cookies:
            assert "name" in c
            assert "value" in c
            assert "domain" in c
            assert "path" in c
            assert "expires" in c

    async def test_saves_cookie_profile_metadata(self, manager):
        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()
        await manager._seed_cookie_jar(ctx, "meta_test")

        profile_file = self.tmp / "cookie_profiles.json"
        assert os.path.exists(profile_file)
        with open(str(profile_file), "r") as f:
            data = json.load(f)
        assert "meta_test" in data
        assert "created_at" in data["meta_test"]
        assert "cookie_count" in data["meta_test"]

    async def test_no_duplicate_domain_name_combos(self, manager):
        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()
        await manager._seed_cookie_jar(ctx, "dedup_test")
        cookies = ctx.add_cookies.call_args[0][0]
        combos = [(c["domain"], c["name"]) for c in cookies]
        assert len(combos) == len(set(combos)), "Duplicate domain+name combos found"

    async def test_reuses_existing_profile_metadata(self, manager):
        """Second call should reuse created_at from first call."""
        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()
        await manager._seed_cookie_jar(ctx, "reuse_test")

        profile_file = self.tmp / "cookie_profiles.json"
        with open(str(profile_file), "r") as f:
            data1 = json.load(f)
        created_at_1 = data1["reuse_test"]["created_at"]

        await manager._seed_cookie_jar(ctx, "reuse_test")
        with open(str(profile_file), "r") as f:
            data2 = json.load(f)
        assert data2["reuse_test"]["created_at"] == created_at_1


# ===========================================================================
# 9. safe_close_context
# ===========================================================================

class TestSafeCloseContext:
    """Test context closing with alive/dead/timed-out contexts."""

    async def test_close_alive_context(self, manager):
        ctx = MagicMock()
        ctx.close = AsyncMock()
        ctx.new_page = AsyncMock()
        test_page = MagicMock()
        test_page.close = AsyncMock()
        ctx.new_page.return_value = test_page

        result = await manager.safe_close_context(ctx)
        assert result is True
        assert id(ctx) in manager._closed_contexts

    async def test_close_none_context_returns_false(self, manager):
        result = await manager.safe_close_context(None)
        assert result is False

    async def test_double_close_returns_false(self, manager):
        ctx = MagicMock()
        ctx.close = AsyncMock()
        ctx.new_page = AsyncMock()
        test_page = MagicMock()
        test_page.close = AsyncMock()
        ctx.new_page.return_value = test_page

        await manager.safe_close_context(ctx)
        result = await manager.safe_close_context(ctx)
        assert result is False

    async def test_close_dead_context_skips_close_call(self, manager):
        """When check_context_alive returns False, context.close() is not called."""
        ctx = MagicMock()
        ctx.close = AsyncMock()
        ctx.new_page = AsyncMock(side_effect=Exception("Target closed"))

        result = await manager.safe_close_context(ctx)
        assert result is True
        ctx.close.assert_not_called()

    async def test_close_with_profile_saves_cookies(self, manager):
        ctx = MagicMock()
        ctx.close = AsyncMock()
        ctx.new_page = AsyncMock()
        ctx.cookies = AsyncMock(return_value=[{"name": "a", "value": "b"}])
        test_page = MagicMock()
        test_page.close = AsyncMock()
        ctx.new_page.return_value = test_page

        with patch.object(manager, "save_cookies", new_callable=AsyncMock) as mock_save:
            await manager.safe_close_context(ctx, profile_name="prof1")
            mock_save.assert_called_once_with(ctx, "prof1")

    async def test_close_timeout_returns_false(self, manager):
        ctx = MagicMock()
        ctx.new_page = AsyncMock()
        test_page = MagicMock()
        test_page.close = AsyncMock()
        ctx.new_page.return_value = test_page
        ctx.close = AsyncMock(side_effect=asyncio.TimeoutError)

        result = await manager.safe_close_context(ctx)
        assert result is False
        assert id(ctx) in manager._closed_contexts

    async def test_close_generic_exception_returns_false(self, manager):
        ctx = MagicMock()
        ctx.new_page = AsyncMock()
        test_page = MagicMock()
        test_page.close = AsyncMock()
        ctx.new_page.return_value = test_page
        ctx.close = AsyncMock(side_effect=RuntimeError("oops"))

        result = await manager.safe_close_context(ctx)
        assert result is False
        assert id(ctx) in manager._closed_contexts


# ===========================================================================
# 10. check_page_alive
# ===========================================================================

class TestCheckPageAlive:
    """Test page health probe with various states."""

    async def test_alive_page(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=False)
        page.evaluate = AsyncMock(return_value=2)
        assert await manager.check_page_alive(page) is True

    async def test_closed_page(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=True)
        assert await manager.check_page_alive(page) is False

    async def test_none_page(self, manager):
        assert await manager.check_page_alive(None) is False

    async def test_frozen_page_timeout(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=False)

        async def slow_evaluate(*args, **kwargs):
            await asyncio.sleep(10)

        page.evaluate = slow_evaluate
        assert await manager.check_page_alive(page) is False

    async def test_page_evaluate_exception(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=False)
        page.evaluate = AsyncMock(side_effect=RuntimeError("page crashed"))
        assert await manager.check_page_alive(page) is False


# ===========================================================================
# 11. check_page_status
# ===========================================================================

class TestCheckPageStatus:
    """Test HTTP status detection via page JavaScript evaluation."""

    async def test_status_200(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=False)
        page.evaluate = AsyncMock(side_effect=[2, 200])
        result = await manager.check_page_status(page)
        assert result["status"] == 200
        assert result["blocked"] is False
        assert result["network_error"] is False

    async def test_status_403_blocked(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=False)
        page.evaluate = AsyncMock(side_effect=[2, 403])
        result = await manager.check_page_status(page)
        assert result["status"] == 403
        assert result["blocked"] is True

    async def test_status_401_blocked(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=False)
        page.evaluate = AsyncMock(side_effect=[2, 401])
        result = await manager.check_page_status(page)
        assert result["status"] == 401
        assert result["blocked"] is True

    async def test_status_0_network_error(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=False)
        page.evaluate = AsyncMock(side_effect=[2, 0])
        result = await manager.check_page_status(page)
        assert result["status"] == 0
        assert result["network_error"] is True

    async def test_dead_page_returns_network_error(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=True)
        result = await manager.check_page_status(page)
        assert result["status"] == -1
        assert result["network_error"] is True

    async def test_evaluate_exception_returns_minus1(self, manager):
        page = MagicMock()
        page.is_closed = MagicMock(return_value=False)
        page.evaluate = AsyncMock(side_effect=[2, Exception("eval fail")])
        result = await manager.check_page_status(page)
        assert result["status"] == -1


# ===========================================================================
# 12. check_context_alive
# ===========================================================================

class TestCheckContextAlive:
    """Test context health probe with alive/closed/frozen contexts."""

    async def test_alive_context(self, manager):
        ctx = MagicMock()
        test_page = MagicMock()
        test_page.close = AsyncMock()
        ctx.new_page = AsyncMock(return_value=test_page)
        assert await manager.check_context_alive(ctx) is True

    async def test_none_context(self, manager):
        assert await manager.check_context_alive(None) is False

    async def test_context_in_closed_set(self, manager):
        ctx = MagicMock()
        manager._closed_contexts.add(id(ctx))
        assert await manager.check_context_alive(ctx) is False

    async def test_context_new_page_raises(self, manager):
        ctx = MagicMock()
        ctx.new_page = AsyncMock(side_effect=Exception("Target closed"))
        assert await manager.check_context_alive(ctx) is False
        assert id(ctx) in manager._closed_contexts

    async def test_context_frozen_timeout(self, manager):
        ctx = MagicMock()

        async def slow_new_page():
            await asyncio.sleep(10)

        ctx.new_page = slow_new_page
        assert await manager.check_context_alive(ctx) is False
        assert id(ctx) in manager._closed_contexts


# ===========================================================================
# 13. safe_new_page
# ===========================================================================

class TestSafeNewPage:
    """Test safe page creation with context health pre-check."""

    async def test_healthy_context_returns_page(self, manager):
        ctx = MagicMock()
        new_page_mock = MagicMock()
        # First new_page call is for health check (returns test page)
        test_page = MagicMock()
        test_page.close = AsyncMock()
        # Second new_page call is the actual page creation
        ctx.new_page = AsyncMock(side_effect=[test_page, new_page_mock])

        result = await manager.safe_new_page(ctx)
        assert result is new_page_mock

    async def test_dead_context_returns_none(self, manager):
        ctx = MagicMock()
        ctx.new_page = AsyncMock(side_effect=Exception("Target closed"))
        result = await manager.safe_new_page(ctx)
        assert result is None

    async def test_context_closes_during_creation(self, manager):
        ctx = MagicMock()
        test_page = MagicMock()
        test_page.close = AsyncMock()
        # Health check succeeds, but second new_page fails
        ctx.new_page = AsyncMock(
            side_effect=[test_page, Exception("Target closed connection")]
        )
        result = await manager.safe_new_page(ctx)
        assert result is None


# ===========================================================================
# 14. check_health
# ===========================================================================

class TestCheckHealth:
    """Test browser-level health check."""

    async def test_no_browser_returns_false(self, manager):
        manager.browser = None
        assert await manager.check_health() is False

    async def test_healthy_browser(self, manager):
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.close = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_ctx)
        manager.browser = mock_browser
        assert await manager.check_health() is True

    async def test_unhealthy_browser(self, manager):
        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(side_effect=RuntimeError("dead"))
        manager.browser = mock_browser
        assert await manager.check_health() is False


# ===========================================================================
# 15. close
# ===========================================================================

class TestClose:
    """Test browser shutdown."""

    async def test_close_clears_state(self, manager):
        mock_camoufox = MagicMock()
        mock_camoufox.__aexit__ = AsyncMock()
        manager.browser = MagicMock()
        manager.camoufox = mock_camoufox
        manager._closed_contexts.add(12345)

        await manager.close()

        assert manager.browser is None
        assert len(manager._closed_contexts) == 0
        mock_camoufox.__aexit__.assert_called_once()

    async def test_close_without_browser_is_noop(self, manager):
        manager.browser = None
        await manager.close()
        assert manager.browser is None

    async def test_close_handles_exit_error(self, manager):
        mock_camoufox = MagicMock()
        mock_camoufox.__aexit__ = AsyncMock(side_effect=RuntimeError("exit error"))
        manager.browser = MagicMock()
        manager.camoufox = mock_camoufox

        await manager.close()
        assert manager.browser is None


# ===========================================================================
# 16. new_page
# ===========================================================================

class TestNewPage:
    """Test new_page with and without context."""

    async def test_new_page_with_context(self, manager):
        ctx = MagicMock()
        mock_page = MagicMock()
        test_page = MagicMock()
        test_page.close = AsyncMock()
        ctx.new_page = AsyncMock(side_effect=[test_page, mock_page])
        manager.browser = MagicMock()

        page = await manager.new_page(context=ctx)
        assert page is mock_page

    async def test_new_page_with_dead_context_raises(self, manager):
        ctx = MagicMock()
        ctx.new_page = AsyncMock(side_effect=Exception("Target closed"))
        manager.browser = MagicMock()

        with pytest.raises(RuntimeError, match="context is closed"):
            await manager.new_page(context=ctx)

    async def test_new_page_without_context_uses_browser(self, manager):
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.route = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        manager.browser = mock_browser

        page = await manager.new_page()
        assert page is mock_page
        mock_page.route.assert_called_once()


# ===========================================================================
# 17. launch
# ===========================================================================

class TestLaunch:
    """Test browser launch with normal and GeoIP-error scenarios."""

    async def test_launch_success(self, manager):
        mock_browser = MagicMock()
        with patch("browser.instance.AsyncCamoufox") as MockCamoufox:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=mock_browser)
            MockCamoufox.return_value = instance

            result = await manager.launch()
            assert result is manager
            assert manager.browser is mock_browser

    async def test_launch_geoip_error_fallback(self, manager):
        """When GeoIP database error occurs, retry with geoip=False."""
        mock_browser = MagicMock()
        call_count = 0

        with patch("browser.instance.AsyncCamoufox") as MockCamoufox:
            # First call raises GeoIP error, second succeeds
            instance_fail = MagicMock()
            instance_fail.__aenter__ = AsyncMock(
                side_effect=Exception("GeoLite2-City.mmdb is invalid")
            )
            instance_ok = MagicMock()
            instance_ok.__aenter__ = AsyncMock(return_value=mock_browser)
            MockCamoufox.side_effect = [instance_fail, instance_ok]

            result = await manager.launch()
            assert result is manager
            assert manager.browser is mock_browser
            # AsyncCamoufox should have been called twice
            assert MockCamoufox.call_count == 2
            # Second call should have geoip=False
            second_call_kwargs = MockCamoufox.call_args_list[1][1]
            assert second_call_kwargs["geoip"] is False

    async def test_launch_non_geoip_error_raises(self, manager):
        """Non-GeoIP errors should propagate."""
        with patch("browser.instance.AsyncCamoufox") as MockCamoufox:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(
                side_effect=RuntimeError("browser binary not found")
            )
            MockCamoufox.return_value = instance

            with pytest.raises(RuntimeError, match="browser binary not found"):
                await manager.launch()


# ===========================================================================
# 18. restart
# ===========================================================================

class TestRestart:
    """Test browser restart (close + launch)."""

    async def test_restart_calls_close_then_launch(self, manager):
        with patch.object(manager, "close", new_callable=AsyncMock) as mock_close, \
             patch.object(manager, "launch", new_callable=AsyncMock) as mock_launch:
            await manager.restart()
            mock_close.assert_called_once()
            mock_launch.assert_called_once()


# ===========================================================================
# 19. save_cookies / load_cookies
# ===========================================================================

class TestCookiePersistence:
    """Test cookie save/load with encrypted and unencrypted paths."""

    @pytest.fixture(autouse=True)
    def _patch_config_dir(self, safe_tmp_path):
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            self.tmp = safe_tmp_path
            yield

    async def test_save_cookies_unencrypted(self, manager):
        ctx = MagicMock()
        ctx.cookies = AsyncMock(return_value=[
            {"name": "sid", "value": "abc123"},
        ])
        await manager.save_cookies(ctx, "unenc_profile")

        cookie_file = self.tmp / "cookies" / "unenc_profile.json"
        assert os.path.exists(cookie_file)
        with open(str(cookie_file), "r") as f:
            data = json.load(f)
        assert data[0]["name"] == "sid"

    async def test_load_cookies_unencrypted(self, manager):
        cookies_dir = self.tmp / "cookies"
        cookies_dir.mkdir(exist_ok=True)
        cookie_file = cookies_dir / "load_profile.json"
        with open(str(cookie_file), "w") as f:
            json.dump([{"name": "test", "value": "val"}], f)

        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()
        manager.seed_cookie_jar = False

        result = await manager.load_cookies(ctx, "load_profile")
        assert result is True
        ctx.add_cookies.assert_called_once()

    async def test_load_cookies_seeds_when_no_cookies(self, manager):
        """When no cookies exist and seed_cookie_jar is True, seed is called."""
        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()
        manager.seed_cookie_jar = True

        with patch.object(manager, "_seed_cookie_jar", new_callable=AsyncMock) as mock_seed:
            result = await manager.load_cookies(ctx, "new_profile")
            assert result is True
            mock_seed.assert_called_once_with(ctx, "new_profile")

    async def test_load_cookies_no_cookies_no_seed(self, manager):
        """When no cookies and seed_cookie_jar is False, return False."""
        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()
        manager.seed_cookie_jar = False

        result = await manager.load_cookies(ctx, "empty_profile")
        assert result is False

    async def test_save_cookies_encrypted(self, safe_tmp_path):
        """When _secure_storage is set, save_cookies uses it."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        mock_storage = MagicMock()
        mock_storage.save_cookies = AsyncMock()
        mgr._secure_storage = mock_storage

        ctx = MagicMock()
        ctx.cookies = AsyncMock(return_value=[{"name": "a", "value": "b"}])

        await mgr.save_cookies(ctx, "enc_profile")
        mock_storage.save_cookies.assert_called_once()

    async def test_load_cookies_encrypted(self, safe_tmp_path):
        """When _secure_storage returns cookies, they are added to context."""
        from browser.instance import BrowserManager
        mgr = BrowserManager(use_encrypted_cookies=False)
        mock_storage = MagicMock()
        mock_storage.load_cookies = AsyncMock(
            return_value=[{"name": "enc", "value": "data"}]
        )
        mgr._secure_storage = mock_storage

        ctx = MagicMock()
        ctx.add_cookies = AsyncMock()

        result = await mgr.load_cookies(ctx, "enc_profile")
        assert result is True
        ctx.add_cookies.assert_called_once()

    async def test_save_cookies_exception_handled(self, manager):
        ctx = MagicMock()
        ctx.cookies = AsyncMock(side_effect=RuntimeError("no cookies"))
        # Should not raise
        await manager.save_cookies(ctx, "error_profile")

    async def test_load_cookies_exception_returns_false(self, manager):
        ctx = MagicMock()
        ctx.add_cookies = AsyncMock(side_effect=RuntimeError("fail"))
        # Create a cookie file that will be found but add_cookies will fail
        cookies_dir = self.tmp / "cookies"
        cookies_dir.mkdir(exist_ok=True)
        with open(str(cookies_dir / "err_profile.json"), "w") as f:
            json.dump([{"name": "x"}], f)

        result = await manager.load_cookies(ctx, "err_profile")
        assert result is False


# ===========================================================================
# 20. _load_cookie_profile / _save_cookie_profile
# ===========================================================================

class TestCookieProfileHelpers:
    """Test cookie profile metadata read/write."""

    @pytest.fixture(autouse=True)
    def _patch_config_dir(self, safe_tmp_path):
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            self.tmp = safe_tmp_path
            yield

    def test_load_missing_file_returns_empty_dict(self, manager):
        result = manager._load_cookie_profile()
        assert result == {}

    def test_save_then_load(self, manager):
        data = {"profile_x": {"created_at": 1234567890, "cookie_count": 15}}
        manager._save_cookie_profile(data)
        loaded = manager._load_cookie_profile()
        assert loaded == data


# ===========================================================================
# 21. create_context
# ===========================================================================

class TestCreateContext:
    """Test context creation with various configurations."""

    @pytest.fixture(autouse=True)
    def _patch_config_dir(self, safe_tmp_path):
        with patch("browser.instance.CONFIG_DIR", safe_tmp_path):
            self.tmp = safe_tmp_path
            yield

    async def test_no_browser_raises_runtime_error(self, manager):
        manager.browser = None
        with pytest.raises(RuntimeError, match="Browser not launched"):
            await manager.create_context()

    @patch("browser.instance.StealthHub")
    @patch("browser.instance.ResourceBlocker")
    async def test_basic_context_creation(self, MockBlocker, MockStealth, manager):
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.route = AsyncMock()
        mock_ctx.add_init_script = AsyncMock()
        mock_ctx.set_default_timeout = MagicMock()
        mock_ctx.add_cookies = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_ctx)
        manager.browser = mock_browser

        MockStealth.get_random_dimensions.return_value = {
            "width": 1920, "height": 1080,
            "screen": {"width": 1920, "height": 1080},
        }
        MockStealth.get_human_ua.return_value = "Mozilla/5.0 Test"
        MockStealth.get_consistent_locale_timezone.return_value = "America/New_York"
        MockStealth.get_consistent_platform_for_ua.return_value = "Win32"
        MockStealth.get_stealth_script.return_value = "// stealth"

        blocker_instance = MagicMock()
        MockBlocker.return_value = blocker_instance

        ctx = await manager.create_context()

        assert ctx is mock_ctx
        mock_browser.new_context.assert_called_once()
        mock_ctx.add_init_script.assert_called_once()
        mock_ctx.route.assert_called_once()

    @patch("browser.instance.StealthHub")
    @patch("browser.instance.ResourceBlocker")
    async def test_context_with_proxy_url(self, MockBlocker, MockStealth, manager):
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.route = AsyncMock()
        mock_ctx.add_init_script = AsyncMock()
        mock_ctx.set_default_timeout = MagicMock()
        mock_ctx.add_cookies = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_ctx)
        manager.browser = mock_browser

        MockStealth.get_random_dimensions.return_value = {
            "width": 1920, "height": 1080,
            "screen": {"width": 1920, "height": 1080},
        }
        MockStealth.get_human_ua.return_value = "Mozilla/5.0 Test"
        MockStealth.get_consistent_locale_timezone.return_value = "America/New_York"
        MockStealth.get_consistent_platform_for_ua.return_value = "Win32"
        MockStealth.get_stealth_script.return_value = "// stealth"
        MockBlocker.return_value = MagicMock()

        ctx = await manager.create_context(
            proxy="http://user:pass@proxy.example.com:8080",
        )

        call_kwargs = mock_browser.new_context.call_args[1]
        assert "proxy" in call_kwargs
        assert call_kwargs["proxy"]["server"] == "http://proxy.example.com:8080"
        assert call_kwargs["proxy"]["username"] == "user"
        assert call_kwargs["proxy"]["password"] == "pass"

    @patch("browser.instance.StealthHub")
    @patch("browser.instance.ResourceBlocker")
    async def test_context_with_locale_timezone_override(
        self, MockBlocker, MockStealth, manager,
    ):
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.route = AsyncMock()
        mock_ctx.add_init_script = AsyncMock()
        mock_ctx.set_default_timeout = MagicMock()
        mock_ctx.add_cookies = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_ctx)
        manager.browser = mock_browser

        MockStealth.get_random_dimensions.return_value = {
            "width": 1920, "height": 1080,
            "screen": {"width": 1920, "height": 1080},
        }
        MockStealth.get_human_ua.return_value = "Mozilla/5.0 Test"
        MockStealth.get_consistent_locale_timezone.return_value = "America/New_York"
        MockStealth.get_consistent_platform_for_ua.return_value = "Win32"
        MockStealth.get_stealth_script.return_value = "// stealth"
        MockBlocker.return_value = MagicMock()

        ctx = await manager.create_context(
            profile_name="override_test",
            locale_override="de-DE",
            timezone_override="Europe/Berlin",
        )

        call_kwargs = mock_browser.new_context.call_args[1]
        assert call_kwargs["locale"] == "de-DE"
        assert call_kwargs["timezone_id"] == "Europe/Berlin"

    @patch("browser.instance.StealthHub")
    @patch("browser.instance.ResourceBlocker")
    async def test_context_block_images_override(
        self, MockBlocker, MockStealth, manager,
    ):
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.route = AsyncMock()
        mock_ctx.add_init_script = AsyncMock()
        mock_ctx.set_default_timeout = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_ctx)
        manager.browser = mock_browser

        MockStealth.get_random_dimensions.return_value = {
            "width": 1920, "height": 1080,
            "screen": {"width": 1920, "height": 1080},
        }
        MockStealth.get_human_ua.return_value = "Mozilla/5.0 Test"
        MockStealth.get_consistent_locale_timezone.return_value = "America/New_York"
        MockStealth.get_consistent_platform_for_ua.return_value = "Win32"
        MockStealth.get_stealth_script.return_value = "// stealth"

        # Verify the ResourceBlocker is constructed with overrides
        MockBlocker.return_value = MagicMock()
        manager.block_images = True  # default
        manager.block_media = True

        ctx = await manager.create_context(
            block_images_override=False,
            block_media_override=False,
        )

        MockBlocker.assert_called_once_with(
            block_images=False, block_media=False,
        )

    @patch("browser.instance.StealthHub")
    @patch("browser.instance.ResourceBlocker")
    async def test_context_with_plain_proxy_no_scheme(
        self, MockBlocker, MockStealth, manager,
    ):
        """Proxy without :// should be used as-is in server field."""
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.route = AsyncMock()
        mock_ctx.add_init_script = AsyncMock()
        mock_ctx.set_default_timeout = MagicMock()
        mock_ctx.add_cookies = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_ctx)
        manager.browser = mock_browser

        MockStealth.get_random_dimensions.return_value = {
            "width": 1920, "height": 1080,
            "screen": {"width": 1920, "height": 1080},
        }
        MockStealth.get_human_ua.return_value = "Test UA"
        MockStealth.get_consistent_locale_timezone.return_value = "America/New_York"
        MockStealth.get_consistent_platform_for_ua.return_value = "Win32"
        MockStealth.get_stealth_script.return_value = "// stealth"
        MockBlocker.return_value = MagicMock()

        ctx = await manager.create_context(proxy="host:8080")

        call_kwargs = mock_browser.new_context.call_args[1]
        assert call_kwargs["proxy"] == {"server": "host:8080"}

    @patch("browser.instance.StealthHub")
    @patch("browser.instance.ResourceBlocker")
    async def test_context_disable_sticky_proxy(
        self, MockBlocker, MockStealth, manager,
    ):
        """When allow_sticky_proxy=False, remove_proxy_binding is called."""
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.route = AsyncMock()
        mock_ctx.add_init_script = AsyncMock()
        mock_ctx.set_default_timeout = MagicMock()
        mock_ctx.add_cookies = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_ctx)
        manager.browser = mock_browser

        MockStealth.get_random_dimensions.return_value = {
            "width": 1920, "height": 1080,
            "screen": {"width": 1920, "height": 1080},
        }
        MockStealth.get_human_ua.return_value = "Test"
        MockStealth.get_consistent_locale_timezone.return_value = "America/New_York"
        MockStealth.get_consistent_platform_for_ua.return_value = "Win32"
        MockStealth.get_stealth_script.return_value = "// stealth"
        MockBlocker.return_value = MagicMock()

        with patch.object(
            manager, "remove_proxy_binding", new_callable=AsyncMock,
        ) as mock_remove:
            await manager.create_context(
                profile_name="no_sticky",
                allow_sticky_proxy=False,
            )
            mock_remove.assert_called_once_with("no_sticky")


# ===========================================================================
# 22. create_stealth_browser factory
# ===========================================================================

class TestCreateStealthBrowser:
    """Test the module-level factory helper."""

    async def test_returns_async_camoufox(self):
        with patch("browser.instance.AsyncCamoufox") as MockCamoufox:
            MockCamoufox.return_value = "camoufox_instance"
            from browser.instance import create_stealth_browser
            result = await create_stealth_browser(headless=True)
            MockCamoufox.assert_called_once()
            assert result == "camoufox_instance"

    async def test_proxy_kwarg_forwarded(self):
        with patch("browser.instance.AsyncCamoufox") as MockCamoufox:
            MockCamoufox.return_value = "camoufox_instance"
            from browser.instance import create_stealth_browser
            await create_stealth_browser(proxy="http://host:1080")
            call_kwargs = MockCamoufox.call_args[1]
            assert call_kwargs["proxy"] == {"server": "http://host:1080"}

    async def test_no_proxy_passes_none(self):
        with patch("browser.instance.AsyncCamoufox") as MockCamoufox:
            MockCamoufox.return_value = "camoufox_instance"
            from browser.instance import create_stealth_browser
            await create_stealth_browser()
            call_kwargs = MockCamoufox.call_args[1]
            assert call_kwargs.get("proxy") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

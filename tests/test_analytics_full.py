"""
Comprehensive tests for core.analytics module.

Fills coverage gaps left by test_analytics.py, test_analytics_extra.py,
and test_price_feed.py. Focuses on:
  - CryptoPriceFeed: corrupt cache, API mocking, TTL expiry, edge cases
  - ClaimRecord / CostRecord: dataclass creation and serialization
  - EarningsTracker: input validation, test-faucet filtering, auto-flush,
    cost recording, profitability, hourly ROI, performance alerts,
    safe JSON read/write with backups, _run_async, data truncation
  - ProfitabilityOptimizer: job priorities, underperforming profiles
  - get_tracker / get_price_feed: singleton reset behaviour
"""

import asyncio
import json
import math
import os
import shutil
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.analytics import (
    ANALYTICS_FILE,
    ClaimRecord,
    CostRecord,
    CryptoPriceFeed,
    EarningsTracker,
    ProfitabilityOptimizer,
    get_price_feed,
    get_tracker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tempdir():
    """Create a temporary directory that the test is responsible for cleaning."""
    return tempfile.mkdtemp(prefix="analytics_test_")


def _analytics_file_in(tmpdir):
    return os.path.join(tmpdir, "test_analytics.json")


def _cache_file_in(tmpdir):
    return os.path.join(tmpdir, "price_cache.json")


@pytest.fixture()
def tmpdir():
    d = _make_tempdir()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def tracker(tmpdir):
    """Return a fresh EarningsTracker backed by a temp file."""
    return EarningsTracker(storage_file=_analytics_file_in(tmpdir))


@pytest.fixture()
def price_feed(tmpdir):
    """Return a CryptoPriceFeed whose cache file lives in a temp dir."""
    feed = CryptoPriceFeed.__new__(CryptoPriceFeed)
    feed.cache = {}
    feed.cache_file = _cache_file_in(tmpdir)
    return feed


# ===================================================================
# 1. ClaimRecord dataclass
# ===================================================================

class TestClaimRecord:

    def test_creation_with_all_fields(self):
        """ClaimRecord can be created with every field populated."""
        rec = ClaimRecord(
            timestamp=1000.0,
            faucet="freebitcoin",
            success=True,
            amount=42.5,
            currency="BTC",
            balance_after=100.0,
            claim_time=12.3,
            failure_reason=None,
        )
        assert rec.timestamp == 1000.0
        assert rec.faucet == "freebitcoin"
        assert rec.success is True
        assert rec.amount == 42.5
        assert rec.currency == "BTC"
        assert rec.balance_after == 100.0
        assert rec.claim_time == 12.3
        assert rec.failure_reason is None

    def test_default_values(self):
        """ClaimRecord defaults: amount=0, currency='unknown', etc."""
        rec = ClaimRecord(timestamp=1.0, faucet="f", success=False)
        assert rec.amount == 0.0
        assert rec.currency == "unknown"
        assert rec.balance_after == 0.0
        assert rec.claim_time is None
        assert rec.failure_reason is None

    def test_asdict_roundtrip(self):
        """asdict produces a dict and we can reconstruct from it."""
        rec = ClaimRecord(
            timestamp=99.0,
            faucet="firefaucet",
            success=False,
            amount=10.0,
            currency="DOGE",
            balance_after=200.0,
            claim_time=5.0,
            failure_reason="captcha_failed",
        )
        d = asdict(rec)
        assert isinstance(d, dict)
        assert d["faucet"] == "firefaucet"
        assert d["failure_reason"] == "captcha_failed"

        reconstructed = ClaimRecord(**d)
        assert reconstructed == rec


# ===================================================================
# 2. CostRecord dataclass
# ===================================================================

class TestCostRecord:

    def test_creation_and_asdict(self):
        rec = CostRecord(
            timestamp=500.0,
            type="captcha",
            amount_usd=0.003,
            faucet="faucetcrypto",
        )
        assert rec.type == "captcha"
        d = asdict(rec)
        assert d["amount_usd"] == 0.003
        assert d["faucet"] == "faucetcrypto"

    def test_default_faucet_none(self):
        rec = CostRecord(timestamp=1.0, type="proxy", amount_usd=0.01)
        assert rec.faucet is None


# ===================================================================
# 3. CryptoPriceFeed
# ===================================================================

class TestCryptoPriceFeedMappings:

    def test_currency_ids_all_present(self):
        """Every key in CURRENCY_DECIMALS also exists in CURRENCY_IDS."""
        for key in CryptoPriceFeed.CURRENCY_DECIMALS:
            assert key in CryptoPriceFeed.CURRENCY_IDS, (
                f"{key} missing from CURRENCY_IDS"
            )

    def test_currency_decimals_all_present(self):
        """Every key in CURRENCY_IDS also exists in CURRENCY_DECIMALS."""
        for key in CryptoPriceFeed.CURRENCY_IDS:
            assert key in CryptoPriceFeed.CURRENCY_DECIMALS, (
                f"{key} missing from CURRENCY_DECIMALS"
            )

    def test_specific_decimals(self):
        assert CryptoPriceFeed.CURRENCY_DECIMALS["BTC"] == 8
        assert CryptoPriceFeed.CURRENCY_DECIMALS["ETH"] == 18
        assert CryptoPriceFeed.CURRENCY_DECIMALS["TRX"] == 6
        assert CryptoPriceFeed.CURRENCY_DECIMALS["SOL"] == 9
        assert CryptoPriceFeed.CURRENCY_DECIMALS["USDT"] == 6


class TestCryptoPriceFeedCache:

    def test_load_cache_corrupt_file(self, tmpdir):
        """Corrupt cache file is handled gracefully."""
        cache_path = _cache_file_in(tmpdir)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write("{bad json!!")

        feed = CryptoPriceFeed.__new__(CryptoPriceFeed)
        feed.cache = {}
        feed.cache_file = cache_path
        feed._load_cache()

        assert feed.cache == {}

    def test_load_cache_missing_file(self, tmpdir):
        """Non-existent cache file leaves cache empty."""
        feed = CryptoPriceFeed.__new__(CryptoPriceFeed)
        feed.cache = {}
        feed.cache_file = os.path.join(tmpdir, "nonexistent.json")
        feed._load_cache()
        assert feed.cache == {}

    def test_load_cache_filters_expired(self, tmpdir):
        """Expired entries are dropped, fresh ones kept."""
        cache_path = _cache_file_in(tmpdir)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        now = time.time()
        data = {
            "OLD": {"price": 1.0, "timestamp": now - 600},
            "FRESH": {"price": 2.0, "timestamp": now - 10},
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        feed = CryptoPriceFeed.__new__(CryptoPriceFeed)
        feed.cache = {}
        feed.cache_file = cache_path
        feed._load_cache()

        assert "OLD" not in feed.cache
        assert "FRESH" in feed.cache
        assert feed.cache["FRESH"]["price"] == 2.0

    def test_load_cache_entry_missing_timestamp(self, tmpdir):
        """Entry without a timestamp field is treated as expired."""
        cache_path = _cache_file_in(tmpdir)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        data = {"NO_TS": {"price": 5.0}}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        feed = CryptoPriceFeed.__new__(CryptoPriceFeed)
        feed.cache = {}
        feed.cache_file = cache_path
        feed._load_cache()

        # timestamp defaults to 0 via .get("timestamp", 0), so 0 + 300 < now
        assert "NO_TS" not in feed.cache

    def test_save_cache_creates_dirs(self, tmpdir):
        """_save_cache creates parent directories if needed."""
        nested = os.path.join(tmpdir, "a", "b", "cache.json")
        feed = CryptoPriceFeed.__new__(CryptoPriceFeed)
        feed.cache = {"X": {"price": 9.0, "timestamp": time.time()}}
        feed.cache_file = nested
        feed._save_cache()

        assert os.path.exists(nested)
        with open(nested, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["X"]["price"] == 9.0

    def test_save_cache_write_error(self, tmpdir):
        """_save_cache handles write errors gracefully."""
        feed = CryptoPriceFeed.__new__(CryptoPriceFeed)
        feed.cache = {"A": {"price": 1.0, "timestamp": time.time()}}
        feed.cache_file = _cache_file_in(tmpdir)

        with patch("builtins.open", side_effect=OSError("disk full")):
            # Should not raise
            feed._save_cache()


class TestCryptoPriceFeedGetPrice:

    @pytest.mark.asyncio
    async def test_cache_hit(self, price_feed):
        """get_price returns cached value when TTL is valid."""
        price_feed.cache["LTC"] = {
            "price": 75.0,
            "timestamp": time.time(),
        }
        result = await price_feed.get_price("ltc")
        assert result == 75.0

    @pytest.mark.asyncio
    async def test_cache_expired_triggers_api(self, price_feed):
        """Expired cache entry triggers a fresh API fetch."""
        price_feed.cache["BTC"] = {
            "price": 10000.0,
            "timestamp": time.time() - 600,  # well past TTL
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "bitcoin": {"usd": 62000.0}
        })

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await price_feed.get_price("BTC")

        assert result == 62000.0
        assert price_feed.cache["BTC"]["price"] == 62000.0

    @pytest.mark.asyncio
    async def test_api_non_200_status(self, price_feed):
        """Non-200 API response returns None."""
        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await price_feed.get_price("ETH")

        assert result is None

    @pytest.mark.asyncio
    async def test_api_returns_empty_data(self, price_feed):
        """API returns 200 but the price key is missing."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await price_feed.get_price("BTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_currency_returns_none(self, price_feed):
        """Currency not in CURRENCY_IDS returns None without API call."""
        result = await price_feed.get_price("FAKECOIN")
        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive(self, price_feed):
        """Currency lookup is case-insensitive."""
        price_feed.cache["DOGE"] = {
            "price": 0.08,
            "timestamp": time.time(),
        }
        assert await price_feed.get_price("doge") == 0.08
        assert await price_feed.get_price("Doge") == 0.08


class TestCryptoPriceFeedConvert:

    @pytest.mark.asyncio
    async def test_convert_eth(self, price_feed):
        """Convert 1 ETH (in wei) to USD."""
        price_feed.cache["ETH"] = {
            "price": 3000.0,
            "timestamp": time.time(),
        }
        # 1 ETH = 1e18 wei
        usd = await price_feed.convert_to_usd(10**18, "ETH")
        assert usd == pytest.approx(3000.0)

    @pytest.mark.asyncio
    async def test_convert_trx(self, price_feed):
        """Convert TRX (6 decimals)."""
        price_feed.cache["TRX"] = {
            "price": 0.10,
            "timestamp": time.time(),
        }
        # 1 TRX = 1e6 sun
        usd = await price_feed.convert_to_usd(10**6, "TRX")
        assert usd == pytest.approx(0.10)

    @pytest.mark.asyncio
    async def test_convert_unknown_returns_zero(self, price_feed):
        """convert_to_usd returns 0.0 for unknown currency."""
        usd = await price_feed.convert_to_usd(999999, "NOPE")
        assert usd == 0.0

    @pytest.mark.asyncio
    async def test_convert_usdt(self, price_feed):
        """USDT (6 decimals) at ~$1."""
        price_feed.cache["USDT"] = {
            "price": 1.0,
            "timestamp": time.time(),
        }
        usd = await price_feed.convert_to_usd(5_000_000, "USDT")
        assert usd == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_convert_sol(self, price_feed):
        """SOL (9 decimals)."""
        price_feed.cache["SOL"] = {
            "price": 150.0,
            "timestamp": time.time(),
        }
        # 2 SOL = 2e9 lamports
        usd = await price_feed.convert_to_usd(2 * 10**9, "SOL")
        assert usd == pytest.approx(300.0)


# ===================================================================
# 4. EarningsTracker - record_claim validation
# ===================================================================

class TestRecordClaimValidation:

    def test_test_faucet_filtered_by_default(self, tracker):
        """Claims from 'test_faucet' are silently dropped."""
        tracker.record_claim("test_faucet", True, 100.0, "BTC")
        assert len(tracker.claims) == 0

    def test_test_prefix_filtered(self, tracker):
        """Claims from faucets starting with 'test_' are dropped."""
        tracker.record_claim("test_something", True, 50.0, "LTC")
        assert len(tracker.claims) == 0

    def test_allow_test_bypasses_filter(self, tracker):
        """allow_test=True lets test faucets through."""
        tracker.record_claim(
            "test_faucet", True, 100.0, "BTC", allow_test=True
        )
        assert len(tracker.claims) == 1

    def test_none_amount_sanitized(self, tracker):
        """None amount is replaced with 0.0."""
        tracker.record_claim("real_faucet", True, None, "BTC")
        assert tracker.claims[-1]["amount"] == 0.0

    def test_string_amount_sanitized(self, tracker):
        """Non-numeric amount is replaced with 0.0."""
        tracker.record_claim("faucet_a", True, "not_a_number", "BTC")
        assert tracker.claims[-1]["amount"] == 0.0

    def test_negative_amount_sanitized(self, tracker):
        """Negative amount is sanitized to 0.0."""
        tracker.record_claim("faucet_b", True, -5.0, "BTC")
        assert tracker.claims[-1]["amount"] == 0.0

    def test_huge_amount_sanitized(self, tracker):
        """Amount >= 1e12 is treated as suspicious and reset to 0."""
        tracker.record_claim("faucet_c", True, 1e12, "BTC")
        assert tracker.claims[-1]["amount"] == 0.0

    def test_valid_amount_kept(self, tracker):
        """A normal valid amount passes validation."""
        tracker.record_claim("faucet_d", True, 500.0, "BTC")
        assert tracker.claims[-1]["amount"] == 500.0

    def test_none_balance_after_sanitized(self, tracker):
        tracker.record_claim(
            "faucet_e", True, 10.0, "BTC", balance_after=None
        )
        assert tracker.claims[-1]["balance_after"] == 0.0

    def test_negative_balance_after_sanitized(self, tracker):
        tracker.record_claim(
            "faucet_f", True, 10.0, "BTC", balance_after=-1.0
        )
        assert tracker.claims[-1]["balance_after"] == 0.0

    def test_invalid_currency_sanitized(self, tracker):
        """Empty or non-string currency replaced with 'unknown'."""
        tracker.record_claim("faucet_g", True, 10.0, "")
        assert tracker.claims[-1]["currency"] == "unknown"

        tracker.record_claim("faucet_h", True, 10.0, None)
        assert tracker.claims[-1]["currency"] == "unknown"

    def test_claim_time_and_failure_reason_stored(self, tracker):
        """Optional claim_time and failure_reason are persisted."""
        tracker.record_claim(
            "faucet_i", False, 0.0, "DOGE",
            claim_time=22.5,
            failure_reason="timeout",
        )
        rec = tracker.claims[-1]
        assert rec["claim_time"] == 22.5
        assert rec["failure_reason"] == "timeout"

    def test_success_with_zero_amount_still_recorded(self, tracker):
        """Successful claim with 0 amount is recorded (with a warning)."""
        tracker.record_claim("faucet_j", True, 0.0, "BTC")
        assert len(tracker.claims) == 1
        assert tracker.claims[-1]["success"] is True
        assert tracker.claims[-1]["amount"] == 0.0


# ===================================================================
# 5. EarningsTracker - auto-flush
# ===================================================================

class TestAutoFlush:

    def test_auto_flush_triggered_when_interval_exceeded(self, tracker):
        """record_claim triggers _save when AUTO_FLUSH_INTERVAL elapsed."""
        tracker.last_flush_time = time.time() - 600  # well past 300s

        with patch.object(tracker, "_save") as mock_save:
            tracker.record_claim("faucet_x", True, 10.0, "BTC")
            mock_save.assert_called_once()

    def test_no_flush_before_interval(self, tracker):
        """record_claim does NOT auto-flush if interval not exceeded."""
        tracker.last_flush_time = time.time()  # just now

        with patch.object(tracker, "_save") as mock_save:
            tracker.record_claim("faucet_y", True, 10.0, "BTC")
            mock_save.assert_not_called()


# ===================================================================
# 6. EarningsTracker - record_cost / record_runtime_cost
# ===================================================================

class TestRecordCost:

    def test_record_cost_appends_and_saves(self, tracker):
        """record_cost adds a CostRecord dict and saves."""
        with patch.object(tracker, "_save") as mock_save:
            tracker.record_cost("captcha", 0.003, faucet="fb")
            mock_save.assert_called_once()

        assert len(tracker.costs) == 1
        assert tracker.costs[0]["type"] == "captcha"
        assert tracker.costs[0]["amount_usd"] == 0.003
        assert tracker.costs[0]["faucet"] == "fb"

    def test_record_cost_no_faucet(self, tracker):
        """record_cost without faucet stores None."""
        with patch.object(tracker, "_save"):
            tracker.record_cost("proxy", 0.01)
        assert tracker.costs[0]["faucet"] is None

    def test_record_runtime_cost_time_only(self, tracker):
        """record_runtime_cost records time cost when proxy not used."""
        with patch.object(tracker, "_save"):
            tracker.record_runtime_cost(
                "faucet_a",
                duration_seconds=3600,
                time_cost_per_hour=0.05,
                proxy_cost_per_hour=0.02,
                proxy_used=False,
            )
        # Should record exactly one cost (time), not proxy
        assert len(tracker.costs) == 1
        assert tracker.costs[0]["type"] == "time"
        assert tracker.costs[0]["amount_usd"] == pytest.approx(0.05)

    def test_record_runtime_cost_time_and_proxy(self, tracker):
        """record_runtime_cost records both time and proxy costs."""
        with patch.object(tracker, "_save"):
            tracker.record_runtime_cost(
                "faucet_b",
                duration_seconds=1800,  # 0.5 hours
                time_cost_per_hour=0.10,
                proxy_cost_per_hour=0.04,
                proxy_used=True,
            )
        assert len(tracker.costs) == 2
        types = {c["type"] for c in tracker.costs}
        assert types == {"time", "proxy"}

    def test_record_runtime_cost_negative_duration(self, tracker):
        """Negative duration_seconds is clamped to 0."""
        with patch.object(tracker, "_save"):
            tracker.record_runtime_cost(
                "faucet_c",
                duration_seconds=-100,
                time_cost_per_hour=1.0,
                proxy_cost_per_hour=1.0,
                proxy_used=True,
            )
        # max(-100, 0) / 3600 = 0 => cost = 0
        for c in tracker.costs:
            assert c["amount_usd"] == 0.0

    def test_record_runtime_cost_zero_rates(self, tracker):
        """Zero cost rates produce no cost records."""
        with patch.object(tracker, "_save"):
            tracker.record_runtime_cost(
                "faucet_d",
                duration_seconds=3600,
                time_cost_per_hour=0.0,
                proxy_cost_per_hour=0.0,
                proxy_used=True,
            )
        assert len(tracker.costs) == 0


# ===================================================================
# 7. EarningsTracker - safe JSON write / read with backups
# ===================================================================

class TestSafeJsonWriteRead:

    def test_safe_write_creates_file(self, tmpdir):
        filepath = os.path.join(tmpdir, "data.json")
        tracker = EarningsTracker(storage_file=_analytics_file_in(tmpdir))
        tracker._safe_json_write(filepath, {"key": "value"})

        assert os.path.exists(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            assert json.load(f) == {"key": "value"}

    def test_safe_write_rotates_backups(self, tmpdir):
        """Successive writes create rotating backups."""
        filepath = os.path.join(tmpdir, "data.json")
        tracker = EarningsTracker(storage_file=_analytics_file_in(tmpdir))

        tracker._safe_json_write(filepath, {"v": 1})
        tracker._safe_json_write(filepath, {"v": 2})
        tracker._safe_json_write(filepath, {"v": 3})

        # Current file should have version 3
        with open(filepath, "r", encoding="utf-8") as f:
            assert json.load(f)["v"] == 3

        # backup.1 should have version 2
        backup1 = filepath + ".backup.1"
        assert os.path.exists(backup1)
        with open(backup1, "r", encoding="utf-8") as f:
            assert json.load(f)["v"] == 2

    def test_safe_read_falls_back_to_backup(self, tmpdir):
        """If main file is corrupt, _safe_json_read falls back to backup."""
        filepath = os.path.join(tmpdir, "data.json")
        tracker = EarningsTracker(storage_file=_analytics_file_in(tmpdir))

        # Write a valid backup
        backup1 = filepath + ".backup.1"
        with open(backup1, "w", encoding="utf-8") as f:
            json.dump({"from": "backup"}, f)

        # Write a corrupt main file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("NOT VALID JSON {{{{")

        result = tracker._safe_json_read(filepath)
        assert result == {"from": "backup"}

    def test_safe_read_returns_none_when_all_corrupt(self, tmpdir):
        """Returns None when main file and all backups are corrupt."""
        filepath = os.path.join(tmpdir, "data.json")
        tracker = EarningsTracker(storage_file=_analytics_file_in(tmpdir))

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("BAD")
        for i in range(1, 4):
            with open(f"{filepath}.backup.{i}", "w", encoding="utf-8") as f:
                f.write("BAD")

        result = tracker._safe_json_read(filepath)
        assert result is None

    def test_safe_read_returns_none_when_no_files(self, tmpdir):
        filepath = os.path.join(tmpdir, "nonexistent.json")
        tracker = EarningsTracker(storage_file=_analytics_file_in(tmpdir))
        result = tracker._safe_json_read(filepath)
        assert result is None

    def test_safe_write_handles_os_error(self, tmpdir):
        """_safe_json_write handles OSError without raising."""
        tracker = EarningsTracker(storage_file=_analytics_file_in(tmpdir))

        with patch("builtins.open", side_effect=OSError("fail")):
            # Should not raise
            tracker._safe_json_write(
                os.path.join(tmpdir, "x.json"), {"a": 1}
            )


# ===================================================================
# 8. EarningsTracker - _save truncation
# ===================================================================

class TestSaveTruncation:

    def test_claims_truncated_to_2000(self, tmpdir):
        """_save keeps only the last 2000 claims."""
        tracker = EarningsTracker(storage_file=_analytics_file_in(tmpdir))
        now = time.time()
        tracker.claims = [
            {"timestamp": now, "faucet": f"f{i}", "success": True,
             "amount": 1.0, "currency": "BTC", "balance_after": 0.0,
             "claim_time": None, "failure_reason": None}
            for i in range(2500)
        ]
        tracker._save()

        with open(_analytics_file_in(tmpdir), "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["claims"]) == 2000

    def test_costs_truncated_to_1000(self, tmpdir):
        """_save keeps only the last 1000 costs."""
        tracker = EarningsTracker(storage_file=_analytics_file_in(tmpdir))
        now = time.time()
        tracker.costs = [
            {"timestamp": now, "type": "captcha",
             "amount_usd": 0.001, "faucet": None}
            for _ in range(1200)
        ]
        tracker._save()

        with open(_analytics_file_in(tmpdir), "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["costs"]) == 1000


# ===================================================================
# 9. EarningsTracker - _run_async
# ===================================================================

class TestRunAsync:

    def test_run_async_no_loop(self, tracker):
        """_run_async works when no event loop is running."""
        async def _coro():
            return 42

        result = tracker._run_async(_coro())
        assert result == 42

    def test_run_async_inside_running_loop(self, tracker):
        """_run_async works when called from within a running loop."""
        async def _inner():
            async def _coro():
                return 99
            return tracker._run_async(_coro())

        result = asyncio.run(_inner())
        assert result == 99


# ===================================================================
# 10. EarningsTracker - get_profitability
# ===================================================================

class TestGetProfitability:

    def test_get_profitability_with_mocked_prices(self, tracker):
        """get_profitability converts earnings via price feed."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "f1",
             "success": True, "amount": 100_000_000,
             "currency": "BTC"},  # 1 BTC
        ]
        tracker.costs = [
            {"timestamp": now - 50, "type": "captcha",
             "amount_usd": 0.005, "faucet": "f1"},
        ]

        mock_feed = MagicMock()
        mock_feed.convert_to_usd = AsyncMock(return_value=50000.0)

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_profitability(hours=1)

        assert result["earnings_usd"] == pytest.approx(50000.0)
        assert result["costs_usd"] == pytest.approx(0.005)
        assert result["net_profit_usd"] == pytest.approx(50000.0 - 0.005)
        assert result["roi"] > 0

    def test_get_profitability_no_costs(self, tracker):
        """ROI is 0 when there are no costs."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 10, "faucet": "f1",
             "success": True, "amount": 1000, "currency": "BTC"},
        ]

        mock_feed = MagicMock()
        mock_feed.convert_to_usd = AsyncMock(return_value=0.5)

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_profitability(hours=1)

        assert result["roi"] == 0  # no costs => roi = 0

    def test_get_profitability_empty_tracker(self, tracker):
        """Empty tracker returns zeroes."""
        mock_feed = MagicMock()
        mock_feed.convert_to_usd = AsyncMock(return_value=0.0)

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_profitability(hours=24)

        assert result["earnings_usd"] == 0.0
        assert result["costs_usd"] == 0.0
        assert result["net_profit_usd"] == 0.0

    def test_get_profitability_respects_time_window(self, tracker):
        """Claims outside the time window are excluded."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "f1",
             "success": True, "amount": 1000, "currency": "BTC"},
            {"timestamp": now - 90000, "faucet": "f1",
             "success": True, "amount": 9999, "currency": "BTC"},
        ]

        mock_feed = MagicMock()

        async def _mock_convert(amount, currency):
            return float(amount) / 1e8 * 50000.0
        mock_feed.convert_to_usd = _mock_convert

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_profitability(hours=1)

        # Only the first claim (1000 sats) should be counted
        expected = 1000 / 1e8 * 50000.0
        assert result["earnings_usd"] == pytest.approx(expected)


# ===================================================================
# 11. EarningsTracker - get_faucet_stats edge cases
# ===================================================================

class TestGetFaucetStatsEdge:

    def test_empty_returns_empty(self, tracker):
        stats = tracker.get_faucet_stats(hours=24)
        assert stats == {}

    def test_all_failures(self, tracker):
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 10, "faucet": "bad",
             "success": False, "amount": 0},
            {"timestamp": now - 20, "faucet": "bad",
             "success": False, "amount": 0},
        ]
        stats = tracker.get_faucet_stats(hours=1)
        assert stats["bad"]["success_rate"] == 0.0
        assert stats["bad"]["earnings"] == 0.0


# ===================================================================
# 12. EarningsTracker - get_captcha_costs_since / get_stats_since
# ===================================================================

class TestCostAndStatsSince:

    def test_get_captcha_costs_since(self, tracker):
        now = time.time()
        with patch.object(tracker, "_save"):
            tracker.record_cost("captcha", 0.003, "f1")
            tracker.record_cost("captcha_hcaptcha", 0.005, "f2")
            tracker.record_cost("proxy", 0.01, "f3")  # not captcha

        since = datetime.fromtimestamp(now - 10, tz=timezone.utc)
        total = tracker.get_captcha_costs_since(since)
        assert total == pytest.approx(0.008)

    def test_get_captcha_costs_since_excludes_old(self, tracker):
        """Costs before the cutoff are excluded."""
        now = time.time()
        tracker.costs = [
            {"timestamp": now - 7200, "type": "captcha",
             "amount_usd": 0.1, "faucet": None},
        ]
        since = datetime.fromtimestamp(now - 3600, tz=timezone.utc)
        total = tracker.get_captcha_costs_since(since)
        assert total == 0.0

    def test_get_stats_since(self, tracker):
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 10, "faucet": "f1", "success": True},
            {"timestamp": now - 20, "faucet": "f1", "success": False},
            {"timestamp": now - 30, "faucet": "f1", "success": True},
            {"timestamp": now - 7200, "faucet": "f1", "success": True},
        ]
        since = datetime.fromtimestamp(now - 60, tz=timezone.utc)
        stats = tracker.get_stats_since(since)
        assert stats["total_claims"] == 3
        assert stats["successes"] == 2
        assert stats["failures"] == 1
        assert stats["success_rate"] == pytest.approx(66.666, rel=0.01)

    def test_get_stats_since_empty(self, tracker):
        since = datetime.now(tz=timezone.utc)
        stats = tracker.get_stats_since(since)
        assert stats["total_claims"] == 0
        assert stats["success_rate"] == 0


# ===================================================================
# 13. EarningsTracker - check_performance_alerts
# ===================================================================

class TestPerformanceAlerts:

    def test_low_success_rate_alert(self, tracker):
        """Alert triggered when success rate drops below 40%."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "bad_faucet",
             "success": False, "amount": 0, "currency": "BTC"},
            {"timestamp": now - 200, "faucet": "bad_faucet",
             "success": False, "amount": 0, "currency": "BTC"},
            {"timestamp": now - 300, "faucet": "bad_faucet",
             "success": True, "amount": 10, "currency": "BTC"},
        ]
        alerts = tracker.check_performance_alerts(hours=2)
        low_rate_alerts = [a for a in alerts if "LOW SUCCESS RATE" in a]
        assert len(low_rate_alerts) == 1
        assert "bad_faucet" in low_rate_alerts[0]

    def test_no_alerts_for_good_faucet(self, tracker):
        """No alerts when all faucets have high success rates."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "good",
             "success": True, "amount": 100, "currency": "BTC"},
            {"timestamp": now - 200, "faucet": "good",
             "success": True, "amount": 100, "currency": "BTC"},
        ]
        alerts = tracker.check_performance_alerts(hours=2)
        low_rate_alerts = [a for a in alerts if "LOW SUCCESS RATE" in a]
        assert len(low_rate_alerts) == 0

    def test_skips_faucets_with_few_claims(self, tracker):
        """Faucets with < 2 claims are skipped."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "single",
             "success": False, "amount": 0, "currency": "BTC"},
        ]
        alerts = tracker.check_performance_alerts(hours=2)
        assert all("single" not in a for a in alerts)


# ===================================================================
# 14. EarningsTracker - get_hourly_rate edge cases
# ===================================================================

class TestGetHourlyRateEdge:

    def test_failed_claims_excluded(self, tracker):
        """Only successful claims count toward hourly rate."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "f1",
             "success": False, "amount": 999},
        ]
        rates = tracker.get_hourly_rate(hours=1)
        assert "f1" not in rates

    def test_specific_faucet_filter(self, tracker):
        """Filtering by faucet returns only that faucet's rate."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 10, "faucet": "f1",
             "success": True, "amount": 100},
            {"timestamp": now - 10, "faucet": "f2",
             "success": True, "amount": 200},
        ]
        rates = tracker.get_hourly_rate(faucet="f1", hours=1)
        assert "f1" in rates
        assert "f2" not in rates


# ===================================================================
# 15. EarningsTracker - get_session_stats edge case
# ===================================================================

class TestGetSessionStatsEdge:

    def test_empty_session(self, tracker):
        stats = tracker.get_session_stats()
        assert stats["total_claims"] == 0
        assert stats["successful_claims"] == 0
        assert stats["success_rate"] == 0
        assert stats["earnings_by_currency"] == {}


# ===================================================================
# 16. EarningsTracker - get_hourly_roi
# ===================================================================

class TestGetHourlyROI:

    def test_hourly_roi_calculation(self, tracker):
        """Hourly ROI requires both earnings and costs per hour."""
        now = time.time()
        # Create a claim at a known UTC hour
        dt = datetime.fromtimestamp(now - 100, tz=timezone.utc)
        hour = dt.hour

        tracker.claims = [
            {"timestamp": now - 100, "faucet": "f1",
             "success": True, "amount": 100_000_000,
             "currency": "BTC"},
        ]
        tracker.costs = [
            {"timestamp": now - 100, "type": "captcha",
             "amount_usd": 0.005, "faucet": "f1"},
        ]

        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_hourly_roi(faucet="f1", days=1)

        assert "f1" in result
        assert hour in result["f1"]
        # ROI = (earned - cost) / cost * 100
        assert result["f1"][hour] > 0

    def test_hourly_roi_no_costs(self, tracker):
        """No costs means no ROI entries (division by zero guard)."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "f1",
             "success": True, "amount": 1000, "currency": "BTC"},
        ]

        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_hourly_roi(days=1)

        # No costs => cost <= 0 => skipped
        assert result == {} or all(
            len(hours) == 0 for hours in result.values()
        )

    def test_hourly_roi_no_faucet_filter(self, tracker):
        """Without faucet filter, all faucets are included."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "f1",
             "success": True, "amount": 1000, "currency": "BTC"},
            {"timestamp": now - 100, "faucet": "f2",
             "success": True, "amount": 2000, "currency": "BTC"},
        ]
        tracker.costs = [
            {"timestamp": now - 100, "type": "captcha",
             "amount_usd": 0.001, "faucet": "f1"},
            {"timestamp": now - 100, "type": "captcha",
             "amount_usd": 0.001, "faucet": "f2"},
        ]

        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_hourly_roi(faucet=None, days=1)

        # Both faucets should appear (if they have costs)
        assert "f1" in result or "f2" in result


# ===================================================================
# 17. EarningsTracker - get_faucet_profitability
# ===================================================================

class TestGetFaucetProfitability:

    def test_basic_profitability_metrics(self, tracker):
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "fp",
             "success": True, "amount": 100_000_000,
             "currency": "BTC"},
            {"timestamp": now - 200, "faucet": "fp",
             "success": True, "amount": 50_000_000,
             "currency": "BTC"},
            {"timestamp": now - 300, "faucet": "fp",
             "success": False, "amount": 0, "currency": "BTC"},
        ]
        tracker.costs = [
            {"timestamp": now - 150, "type": "captcha",
             "amount_usd": 0.01, "faucet": "fp"},
        ]

        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_faucet_profitability("fp", days=1)

        assert result["claim_count"] == 3
        assert result["success_count"] == 2
        assert result["success_rate"] == pytest.approx(66.666, rel=0.01)
        assert result["total_cost_usd"] == pytest.approx(0.01)
        assert result["total_earned_usd"] > 0
        assert result["net_profit_usd"] > 0
        assert "profitability_score" in result

    def test_profitability_no_claims(self, tracker):
        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_faucet_profitability("empty", days=1)

        assert result["claim_count"] == 0
        assert result["success_count"] == 0
        assert result["total_earned_usd"] == 0.0

    def test_profitability_score_success_bonus(self, tracker):
        """High success rate adds a bonus to the profitability score."""
        now = time.time()
        # 10 claims, all successful => success_rate = 100% => bonus = 20
        tracker.claims = [
            {"timestamp": now - i * 10, "faucet": "bonus",
             "success": True, "amount": 1000, "currency": "BTC"}
            for i in range(10)
        ]
        tracker.costs = [
            {"timestamp": now - 5, "type": "captcha",
             "amount_usd": 0.001, "faucet": "bonus"},
        ]

        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            result = tracker.get_faucet_profitability("bonus", days=1)

        assert result["success_rate"] == 100.0
        # Score includes success_bonus of 20
        assert result["profitability_score"] >= 20


# ===================================================================
# 18. EarningsTracker - get_profitability_report
# ===================================================================

class TestGetProfitabilityReport:

    def test_report_sorted_by_score(self, tracker):
        now = time.time()
        # Two faucets with different numbers of claims
        for i in range(5):
            tracker.claims.append({
                "timestamp": now - i * 10, "faucet": "top",
                "success": True, "amount": 10000, "currency": "BTC",
            })
        for i in range(5):
            tracker.claims.append({
                "timestamp": now - i * 10, "faucet": "bottom",
                "success": (i < 1), "amount": 100, "currency": "BTC",
            })

        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            report = tracker.get_profitability_report(
                days=1, min_claims=3
            )

        assert len(report) >= 1
        # Sorted descending by profitability_score
        if len(report) >= 2:
            assert (
                report[0]["profitability_score"]
                >= report[1]["profitability_score"]
            )

    def test_report_min_claims_filter(self, tracker):
        """Faucets below min_claims are excluded."""
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 10, "faucet": "few",
             "success": True, "amount": 100, "currency": "BTC"},
        ]

        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            report = tracker.get_profitability_report(
                days=1, min_claims=5
            )

        assert len(report) == 0

    def test_report_empty_tracker(self, tracker):
        mock_feed = MagicMock()
        mock_feed.get_price = AsyncMock(return_value=50000.0)
        mock_feed.CURRENCY_DECIMALS = CryptoPriceFeed.CURRENCY_DECIMALS

        with patch("core.analytics.get_price_feed", return_value=mock_feed):
            report = tracker.get_profitability_report(days=1)

        assert report == []


# ===================================================================
# 19. ProfitabilityOptimizer
# ===================================================================

class TestProfitabilityOptimizer:

    def test_suggest_job_priorities(self, tracker):
        now = time.time()
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "high",
             "success": True, "amount": 1000},
            {"timestamp": now - 200, "faucet": "high",
             "success": True, "amount": 900},
            {"timestamp": now - 100, "faucet": "low",
             "success": True, "amount": 10},
            {"timestamp": now - 200, "faucet": "low",
             "success": False, "amount": 0},
        ]

        optimizer = ProfitabilityOptimizer(tracker)
        priorities = optimizer.suggest_job_priorities()

        assert "high" in priorities
        assert "low" in priorities
        # High performer should have higher priority
        assert priorities["high"] >= priorities["low"]
        # All priorities clamped between 0.5 and 2.0
        for p in priorities.values():
            assert 0.5 <= p <= 2.0

    def test_suggest_job_priorities_empty(self, tracker):
        optimizer = ProfitabilityOptimizer(tracker)
        priorities = optimizer.suggest_job_priorities()
        assert priorities == {}

    def test_get_underperforming_profiles(self, tracker):
        now = time.time()
        # bad_faucet: 1/10 success => 10% rate, total >= 5
        for i in range(10):
            tracker.claims.append({
                "timestamp": now - 100 - i * 10,
                "faucet": "bad_faucet",
                "success": (i == 0),
                "amount": 10 if i == 0 else 0,
            })
        # good_faucet: 9/10 success => 90% rate
        for i in range(10):
            tracker.claims.append({
                "timestamp": now - 100 - i * 10,
                "faucet": "good_faucet",
                "success": (i < 9),
                "amount": 10,
            })

        optimizer = ProfitabilityOptimizer(tracker)
        under = optimizer.get_underperforming_profiles(threshold_sr=30.0)
        assert "bad_faucet" in under
        assert "good_faucet" not in under

    def test_get_underperforming_skips_low_volume(self, tracker):
        """Faucets with < 5 total claims are excluded."""
        now = time.time()
        for i in range(3):
            tracker.claims.append({
                "timestamp": now - 100 - i * 10,
                "faucet": "tiny",
                "success": False,
                "amount": 0,
            })

        optimizer = ProfitabilityOptimizer(tracker)
        under = optimizer.get_underperforming_profiles()
        assert "tiny" not in under


# ===================================================================
# 20. Singleton functions
# ===================================================================

class TestSingletons:

    def test_get_tracker_singleton_reset(self):
        """Deleting the instance attribute forces re-creation."""
        if hasattr(get_tracker, "instance"):
            delattr(get_tracker, "instance")

        t1 = get_tracker()
        t2 = get_tracker()
        assert t1 is t2

        # Clean up
        delattr(get_tracker, "instance")

    def test_get_price_feed_singleton_reset(self):
        if hasattr(get_price_feed, "instance"):
            delattr(get_price_feed, "instance")

        f1 = get_price_feed()
        f2 = get_price_feed()
        assert f1 is f2

        delattr(get_price_feed, "instance")


# ===================================================================
# 21. EarningsTracker - _load with existing claims/costs
# ===================================================================

class TestLoadPersistence:

    def test_load_merges_from_file(self, tmpdir):
        """_load populates claims and costs from a valid file."""
        filepath = _analytics_file_in(tmpdir)
        now = time.time()
        data = {
            "claims": [
                {"timestamp": now, "faucet": "persisted",
                 "success": True, "amount": 77, "currency": "LTC"},
            ],
            "costs": [
                {"timestamp": now, "type": "proxy",
                 "amount_usd": 0.02, "faucet": None},
            ],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)

        tracker = EarningsTracker(storage_file=filepath)
        assert len(tracker.claims) == 1
        assert tracker.claims[0]["faucet"] == "persisted"
        assert len(tracker.costs) == 1
        assert tracker.costs[0]["type"] == "proxy"

    def test_load_corrupt_file_clears_data(self, tmpdir):
        """Corrupt main file with no backups => empty lists."""
        filepath = _analytics_file_in(tmpdir)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("CORRUPT!!!")

        tracker = EarningsTracker(storage_file=filepath)
        # _load calls _safe_json_read which returns None for corrupt
        # The outer try/except keeps claims/costs as []
        assert tracker.claims == []
        assert tracker.costs == []


# ===================================================================
# 22. EarningsTracker - init creates file if missing
# ===================================================================

class TestInitCreatesFile:

    def test_new_file_created_on_init(self, tmpdir):
        filepath = _analytics_file_in(tmpdir)
        assert not os.path.exists(filepath)

        tracker = EarningsTracker(storage_file=filepath)
        assert os.path.exists(filepath)

    def test_default_storage_file(self):
        """When no storage_file given, uses ANALYTICS_FILE."""
        with patch("core.analytics.ANALYTICS_FILE", "dummy_path"):
            with patch.object(EarningsTracker, "_save"):
                with patch.object(EarningsTracker, "_load"):
                    with patch("os.path.exists", return_value=True):
                        tracker = EarningsTracker()
                        assert tracker.storage_file == "dummy_path"


# ===================================================================
# 23. EarningsTracker - get_daily_summary edge cases
# ===================================================================

class TestGetDailySummaryEdge:

    def test_summary_with_multiple_currencies(self, tracker):
        now = time.time()
        tracker.session_start = now - 3600
        tracker.claims = [
            {"timestamp": now - 100, "faucet": "f1",
             "success": True, "amount": 100, "currency": "BTC"},
            {"timestamp": now - 200, "faucet": "f1",
             "success": True, "amount": 200, "currency": "LTC"},
            {"timestamp": now - 300, "faucet": "f2",
             "success": True, "amount": 300, "currency": "DOGE"},
        ]

        summary = tracker.get_daily_summary()
        assert "BTC" in summary
        assert "LTC" in summary
        assert "DOGE" in summary
        assert "EARNINGS SUMMARY" in summary

    def test_summary_with_zero_claims(self, tracker):
        """Empty tracker produces a valid summary string."""
        summary = tracker.get_daily_summary()
        assert isinstance(summary, str)
        assert "Total Claims: 0" in summary
        assert "Success Rate: 0.0%" in summary


# ===================================================================
# 24. EarningsTracker - generate_automated_report
# ===================================================================

class TestGenerateAutomatedReportEdge:

    def test_report_handles_growth_indicators(self, tracker):
        """Report includes growth indicator symbols."""
        now = time.time()
        tracker.session_start = now - 86400
        # Day 0 (today period)
        for i in range(3):
            tracker.claims.append({
                "timestamp": now - 600 - i * 100,
                "faucet": "growing",
                "success": True, "amount": 500,
                "currency": "BTC",
            })
        # Day 1 (yesterday period) - lower earnings
        for i in range(2):
            tracker.claims.append({
                "timestamp": now - 86400 - i * 100,
                "faucet": "growing",
                "success": True, "amount": 100,
                "currency": "BTC",
            })

        report = tracker.generate_automated_report(save_to_file=False)
        assert "CRYPTOBOT DAILY REPORT" in report
        assert "growing" in report


# ===================================================================
# 25. get_trending_analysis - growth rate edge cases
# ===================================================================

class TestTrendingAnalysisGrowth:

    def test_growth_rate_positive(self, tracker):
        """When today > yesterday, growth rate is positive."""
        now = time.time()
        # Today: 200 earned
        tracker.claims.append({
            "timestamp": now - 100,
            "faucet": "trend",
            "success": True,
            "amount": 200,
        })
        # Yesterday: 100 earned
        tracker.claims.append({
            "timestamp": now - 86400 - 100,
            "faucet": "trend",
            "success": True,
            "amount": 100,
        })

        trends = tracker.get_trending_analysis(periods=2)
        assert trends["trend"]["growth_rate"] == pytest.approx(100.0)

    def test_growth_rate_negative(self, tracker):
        """When today < yesterday, growth rate is negative."""
        now = time.time()
        tracker.claims.append({
            "timestamp": now - 100,
            "faucet": "trend",
            "success": True,
            "amount": 50,
        })
        tracker.claims.append({
            "timestamp": now - 86400 - 100,
            "faucet": "trend",
            "success": True,
            "amount": 100,
        })

        trends = tracker.get_trending_analysis(periods=2)
        assert trends["trend"]["growth_rate"] == pytest.approx(-50.0)

    def test_growth_rate_failed_claims_excluded(self, tracker):
        """Failed claims do not contribute to daily_earnings."""
        now = time.time()
        tracker.claims.append({
            "timestamp": now - 100,
            "faucet": "trend",
            "success": False,
            "amount": 999,
        })

        trends = tracker.get_trending_analysis(periods=1)
        assert trends["trend"]["daily_earnings"][0] == 0
        assert trends["trend"]["daily_claims"][0] == 1
        assert trends["trend"]["daily_success"][0] == 0

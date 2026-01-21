import pytest
import json
import os
import time
from unittest.mock import patch, MagicMock, AsyncMock
from core.analytics import CryptoPriceFeed, get_price_feed


@pytest.fixture
def temp_cache_file(tmp_path):
    """Fixture for temporary cache file."""
    return str(tmp_path / "price_cache.json")


class TestCryptoPriceFeed:
    
    def test_cache_initialization(self, temp_cache_file):
        """Test cache loads from disk on init."""
        # Create cache file
        cache_data = {
            "BTC": {"price": 50000.0, "timestamp": time.time()}
        }
        with open(temp_cache_file, "w") as f:
            json.dump(cache_data, f)
        
        feed = CryptoPriceFeed()
        feed.cache_file = temp_cache_file
        feed._load_cache()
        
        assert "BTC" in feed.cache
        assert feed.cache["BTC"]["price"] == 50000.0
    
    def test_cache_expiration(self, temp_cache_file):
        """Test that expired cache entries are ignored."""
        # Create cache file with old data
        cache_data = {
            "BTC": {"price": 50000.0, "timestamp": time.time() - 400},  # Older than TTL (300s)
            "LTC": {"price": 100.0, "timestamp": time.time()}  # Fresh
        }
        with open(temp_cache_file, "w") as f:
            json.dump(cache_data, f)
        
        feed = CryptoPriceFeed()
        feed.cache_file = temp_cache_file
        feed._load_cache()
        
        # Expired entry should not be loaded
        assert "BTC" not in feed.cache
        # Fresh entry should be loaded
        assert "LTC" in feed.cache
    
    @pytest.mark.asyncio
    async def test_get_price_from_cache(self, temp_cache_file):
        """Test getting price from cache."""
        feed = CryptoPriceFeed()
        feed.cache_file = temp_cache_file
        
        # Manually set cache
        feed.cache["BTC"] = {
            "price": 50000.0,
            "timestamp": time.time()
        }
        
        price = await feed.get_price("BTC")
        assert price == 50000.0
    
    @pytest.mark.asyncio
    async def test_get_price_api_failure(self, temp_cache_file):
        """Test handling API failure gracefully."""
        feed = CryptoPriceFeed()
        feed.cache_file = temp_cache_file
        
        # Empty cache, will try API and fail
        with patch("aiohttp.ClientSession") as mock_session_cls:
            # Make session raise an exception
            mock_session_cls.side_effect = Exception("Network error")
            
            price = await feed.get_price("BTC")
            
            # Should return None on failure
            assert price is None
    
    @pytest.mark.asyncio
    async def test_convert_to_usd(self, temp_cache_file):
        """Test converting crypto amount to USD."""
        feed = CryptoPriceFeed()
        feed.cache_file = temp_cache_file
        
        # Set cache
        feed.cache["BTC"] = {
            "price": 50000.0,
            "timestamp": time.time()
        }
        
        # 100,000,000 satoshi = 1 BTC = $50,000
        usd = await feed.convert_to_usd(100_000_000, "BTC")
        assert usd == pytest.approx(50000.0, rel=0.01)
        
        # 50,000,000 satoshi = 0.5 BTC = $25,000
        usd = await feed.convert_to_usd(50_000_000, "BTC")
        assert usd == pytest.approx(25000.0, rel=0.01)
    
    @pytest.mark.asyncio
    async def test_unknown_currency(self, temp_cache_file):
        """Test handling of unknown currency."""
        feed = CryptoPriceFeed()
        feed.cache_file = temp_cache_file
        
        price = await feed.get_price("UNKNOWN")
        assert price is None
    
    def test_save_cache(self, temp_cache_file):
        """Test saving cache to disk."""
        feed = CryptoPriceFeed()
        feed.cache_file = temp_cache_file
        
        feed.cache["BTC"] = {
            "price": 50000.0,
            "timestamp": time.time()
        }
        
        feed._save_cache()
        
        # Verify file was created
        assert os.path.exists(temp_cache_file)
        
        # Verify contents
        with open(temp_cache_file, "r") as f:
            data = json.load(f)
            assert "BTC" in data
            assert data["BTC"]["price"] == 50000.0
    
    def test_singleton_price_feed(self):
        """Test global price feed singleton."""
        feed1 = get_price_feed()
        feed2 = get_price_feed()
        assert feed1 is feed2

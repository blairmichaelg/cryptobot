import pytest
import json
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Mock camoufox before importing BrowserManager
sys.modules['camoufox'] = MagicMock()
sys.modules['camoufox.async_api'] = MagicMock()

from browser.instance import BrowserManager


@pytest.fixture
def temp_fingerprint_file(tmp_path):
    """Fixture for temporary fingerprint file."""
    return tmp_path / "profile_fingerprints.json"


@pytest.mark.asyncio
class TestFingerprintPersistence:
    
    async def test_save_and_load_fingerprint(self, temp_fingerprint_file, tmp_path):
        """Test saving and loading profile fingerprints."""
        with patch("browser.instance.CONFIG_DIR", tmp_path):
            manager = BrowserManager()
            
            # Save fingerprint
            await manager.save_profile_fingerprint("test_profile", "en-US", "America/New_York")
            
            # Verify file was created
            assert os.path.exists(temp_fingerprint_file)
            
            # Load fingerprint
            fingerprint = await manager.load_profile_fingerprint("test_profile")
            
            assert fingerprint is not None
            assert fingerprint["locale"] == "en-US"
            assert fingerprint["timezone_id"] == "America/New_York"
    
    async def test_load_nonexistent_fingerprint(self, tmp_path):
        """Test loading fingerprint that doesn't exist."""
        with patch("browser.instance.CONFIG_DIR", tmp_path):
            manager = BrowserManager()
            
            fingerprint = await manager.load_profile_fingerprint("nonexistent")
            
            assert fingerprint is None
    
    async def test_fingerprint_reuse(self, temp_fingerprint_file, tmp_path):
        """Test that same fingerprint is reused for same profile."""
        with patch("browser.instance.CONFIG_DIR", tmp_path):
            # Create pre-existing fingerprint
            data = {
                "test_profile": {
                    "locale": "en-GB",
                    "timezone_id": "Europe/London"
                }
            }
            with open(temp_fingerprint_file, "w") as f:
                json.dump(data, f)
            
            manager = BrowserManager()
            
            # Load fingerprint
            fingerprint = await manager.load_profile_fingerprint("test_profile")
            
            assert fingerprint["locale"] == "en-GB"
            assert fingerprint["timezone_id"] == "Europe/London"
    
    async def test_multiple_profiles(self, temp_fingerprint_file, tmp_path):
        """Test storing fingerprints for multiple profiles."""
        with patch("browser.instance.CONFIG_DIR", tmp_path):
            manager = BrowserManager()
            
            # Save multiple profiles
            await manager.save_profile_fingerprint("profile1", "en-US", "America/New_York")
            await manager.save_profile_fingerprint("profile2", "en-GB", "Europe/London")
            await manager.save_profile_fingerprint("profile3", "en-AU", "Australia/Sydney")
            
            # Verify all are saved
            fp1 = await manager.load_profile_fingerprint("profile1")
            fp2 = await manager.load_profile_fingerprint("profile2")
            fp3 = await manager.load_profile_fingerprint("profile3")
            
            assert fp1["locale"] == "en-US"
            assert fp2["locale"] == "en-GB"
            assert fp3["locale"] == "en-AU"
    
    async def test_corrupt_fingerprint_file(self, temp_fingerprint_file, tmp_path):
        """Test handling of corrupt fingerprint file."""
        with patch("browser.instance.CONFIG_DIR", tmp_path):
            # Create corrupt file
            with open(temp_fingerprint_file, "w") as f:
                f.write("not valid json{")
            
            manager = BrowserManager()
            
            # Should not crash, should return None
            fingerprint = await manager.load_profile_fingerprint("test_profile")
            assert fingerprint is None
            
            # Should be able to save new fingerprint (overwriting corrupt file)
            await manager.save_profile_fingerprint("test_profile", "en-US", "America/New_York")
            
            # Should now be loadable
            fingerprint = await manager.load_profile_fingerprint("test_profile")
            assert fingerprint is not None

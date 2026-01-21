import pytest
import json
import os
from pathlib import Path


@pytest.fixture
def temp_fingerprint_file(tmp_path):
    """Fixture for temporary fingerprint file."""
    return tmp_path / "profile_fingerprints.json"


class TestFingerprintPersistence:
    """Test fingerprint persistence logic without full BrowserManager."""
    
    async def _save_fingerprint(self, config_dir: Path, profile_name: str, locale: str, timezone_id: str):
        """Helper to save fingerprint (mimics BrowserManager.save_profile_fingerprint)."""
        try:
            fingerprint_file = config_dir / "profile_fingerprints.json"
            data = {}
            if os.path.exists(fingerprint_file):
                with open(fingerprint_file, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            data[profile_name] = {
                "locale": locale,
                "timezone_id": timezone_id
            }
            
            with open(fingerprint_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    async def _load_fingerprint(self, config_dir: Path, profile_name: str):
        """Helper to load fingerprint (mimics BrowserManager.load_profile_fingerprint)."""
        try:
            fingerprint_file = config_dir / "profile_fingerprints.json"
            if os.path.exists(fingerprint_file):
                with open(fingerprint_file, "r") as f:
                    try:
                        data = json.load(f)
                        return data.get(profile_name)
                    except json.JSONDecodeError:
                        pass
            return None
        except Exception:
            return None
    
    @pytest.mark.asyncio
    async def test_save_and_load_fingerprint(self, tmp_path):
        """Test saving and loading profile fingerprints."""
        # Save fingerprint
        await self._save_fingerprint(tmp_path, "test_profile", "en-US", "America/New_York")
        
        # Verify file was created
        fingerprint_file = tmp_path / "profile_fingerprints.json"
        assert os.path.exists(fingerprint_file)
        
        # Load fingerprint
        fingerprint = await self._load_fingerprint(tmp_path, "test_profile")
        
        assert fingerprint is not None
        assert fingerprint["locale"] == "en-US"
        assert fingerprint["timezone_id"] == "America/New_York"
    
    @pytest.mark.asyncio
    async def test_load_nonexistent_fingerprint(self, tmp_path):
        """Test loading fingerprint that doesn't exist."""
        fingerprint = await self._load_fingerprint(tmp_path, "nonexistent")
        assert fingerprint is None
    
    @pytest.mark.asyncio
    async def test_fingerprint_reuse(self, tmp_path):
        """Test that same fingerprint is reused for same profile."""
        # Create pre-existing fingerprint
        fingerprint_file = tmp_path / "profile_fingerprints.json"
        data = {
            "test_profile": {
                "locale": "en-GB",
                "timezone_id": "Europe/London"
            }
        }
        with open(fingerprint_file, "w") as f:
            json.dump(data, f)
        
        # Load fingerprint
        fingerprint = await self._load_fingerprint(tmp_path, "test_profile")
        
        assert fingerprint["locale"] == "en-GB"
        assert fingerprint["timezone_id"] == "Europe/London"
    
    @pytest.mark.asyncio
    async def test_multiple_profiles(self, tmp_path):
        """Test storing fingerprints for multiple profiles."""
        # Save multiple profiles
        await self._save_fingerprint(tmp_path, "profile1", "en-US", "America/New_York")
        await self._save_fingerprint(tmp_path, "profile2", "en-GB", "Europe/London")
        await self._save_fingerprint(tmp_path, "profile3", "en-AU", "Australia/Sydney")
        
        # Verify all are saved
        fp1 = await self._load_fingerprint(tmp_path, "profile1")
        fp2 = await self._load_fingerprint(tmp_path, "profile2")
        fp3 = await self._load_fingerprint(tmp_path, "profile3")
        
        assert fp1["locale"] == "en-US"
        assert fp2["locale"] == "en-GB"
        assert fp3["locale"] == "en-AU"
    
    @pytest.mark.asyncio
    async def test_corrupt_fingerprint_file(self, tmp_path):
        """Test handling of corrupt fingerprint file."""
        fingerprint_file = tmp_path / "profile_fingerprints.json"
        
        # Create corrupt file
        with open(fingerprint_file, "w") as f:
            f.write("not valid json{")
        
        # Should not crash, should return None
        fingerprint = await self._load_fingerprint(tmp_path, "test_profile")
        assert fingerprint is None
        
        # Should be able to save new fingerprint (overwriting corrupt file)
        await self._save_fingerprint(tmp_path, "test_profile", "en-US", "America/New_York")
        
        # Should now be loadable
        fingerprint = await self._load_fingerprint(tmp_path, "test_profile")
        assert fingerprint is not None

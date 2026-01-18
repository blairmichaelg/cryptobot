import pytest
import os
import json
import base64
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet
from browser.secure_storage import SecureCookieStorage, generate_cookie_encryption_key

@pytest.fixture
def temp_storage(tmp_path):
    storage_dir = tmp_path / "secure_cookies"
    storage_dir.mkdir()
    return str(storage_dir)

class TestSecureCookieStorage:
    
    def test_init_without_key(self, temp_storage):
        """Test initialization when no key is in environment."""
        with patch.dict(os.environ, {}, clear=True):
            storage = SecureCookieStorage(storage_dir=temp_storage)
            assert storage._fernet is not None
            assert isinstance(storage._fernet, Fernet)

    def test_init_with_primary_key(self, temp_storage):
        """Test initialization with a primary key."""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": key}):
            storage = SecureCookieStorage(storage_dir=temp_storage)
            assert storage._fernet is not None
            # Check if it can encrypt/decrypt
            data = b"test"
            assert storage._fernet.decrypt(storage._fernet.encrypt(data)) == data

    def test_init_with_key_rotation(self, temp_storage):
        """Test initialization with primary and old keys (MultiFernet)."""
        primary = Fernet.generate_key().decode()
        old = Fernet.generate_key().decode()
        with patch.dict(os.environ, {
            "CRYPTOBOT_COOKIE_KEY": primary,
            "CRYPTOBOT_COOKIE_KEY_OLD": old
        }):
            storage = SecureCookieStorage(storage_dir=temp_storage)
            assert storage._fernet is not None
            # MultiFernet doesn't expose keys directly easily, but we can test functionality
            # It should be able to decrypt data encrypted with the old key
            old_fernet = Fernet(old.encode())
            encrypted_old = old_fernet.encrypt(b"old data")
            assert storage._fernet.decrypt(encrypted_old) == b"old data"

    def test_init_failure(self, temp_storage):
        """Test initialization failure with invalid key."""
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": "invalid"}):
            storage = SecureCookieStorage(storage_dir=temp_storage)
            assert storage._fernet is None

    @pytest.mark.asyncio
    async def test_save_and_load_cookies(self, temp_storage):
        """Test saving and loading cookies."""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": key}):
            storage = SecureCookieStorage(storage_dir=temp_storage)
            cookies = [{"name": "test", "value": "val"}]
            profile = "user123"
            
            # Save
            assert await storage.save_cookies(cookies, profile) is True
            
            # File should exist
            expected_path = os.path.join(temp_storage, f"{profile}.enc")
            assert os.path.exists(expected_path)
            
            # Load
            loaded = await storage.load_cookies(profile)
            assert loaded == cookies

    @pytest.mark.asyncio
    async def test_save_without_fernet(self, temp_storage):
        """Test saving when encryption is not initialized (branch 91)."""
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": "invalid"}):
            storage = SecureCookieStorage(storage_dir=temp_storage)
            assert await storage.save_cookies([], "any") is False

    @pytest.mark.asyncio
    async def test_load_without_fernet(self, temp_storage):
        """Test loading when encryption is not initialized (branch 125)."""
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": "invalid"}):
            storage = SecureCookieStorage(storage_dir=temp_storage)
            assert await storage.load_cookies("any") is None

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, temp_storage):
        """Test loading when file doesn't exist."""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": key}):
            storage = SecureCookieStorage(temp_storage)
            assert await storage.load_cookies("missing") is None

    @pytest.mark.asyncio
    async def test_load_corrupted_invalid_token(self, temp_storage):
        """Test loading corrupted data (InvalidToken)."""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": key}):
            storage = SecureCookieStorage(temp_storage)
            profile = "corrupt"
            cookie_path = os.path.join(temp_storage, f"{profile}.enc")
            
            # Write invalid encrypted data
            with open(cookie_path, "wb") as f:
                f.write(b"not a valid fernet token")
            
            loaded = await storage.load_cookies(profile)
            assert loaded is None
            
            # Should have backed up the file
            assert os.path.exists(f"{cookie_path}.backup")

    @pytest.mark.asyncio
    async def test_load_general_exception(self, temp_storage):
        """Test loading with unexpected exception (branch 153)."""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": key}):
            storage = SecureCookieStorage(temp_storage)
            # Create file but make reading it fail
            profile = "fail_read"
            cookie_path = os.path.join(temp_storage, f"{profile}.enc")
            with open(cookie_path, "wb") as f: f.write(b"data")
            
            with patch("browser.secure_storage.open", side_effect=Exception("Disk fail")):
                assert await storage.load_cookies(profile) is None

    @pytest.mark.asyncio
    async def test_save_exception(self, temp_storage):
        """Test saving with unexpected exception."""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": key}):
            storage = SecureCookieStorage(temp_storage)
            with patch("browser.secure_storage.open", side_effect=Exception("Disk fail")):
                assert await storage.save_cookies([], "any") is False

    def test_delete_cookies(self, temp_storage):
        """Test deleting cookies."""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CRYPTOBOT_COOKIE_KEY": key}):
            storage = SecureCookieStorage(temp_storage)
            profile = "delete_me"
            cookie_path = os.path.join(temp_storage, f"{profile}.enc")
            
            # Create dummy file
            with open(cookie_path, "w") as f: f.write("data")
            
            assert storage.delete_cookies(profile) is True
            assert not os.path.exists(cookie_path)
            
            # Delete non-existent
            assert storage.delete_cookies("not_there") is False

    def test_delete_exception(self, temp_storage):
        """Test delete with exception."""
        storage = SecureCookieStorage(temp_storage)
        with patch("os.path.exists", return_value=True), \
             patch("os.remove", side_effect=Exception("Perm error")):
            assert storage.delete_cookies("any") is False

    def test_profile_name_sanitization(self, temp_storage):
        """Test that profile names are sanitized for filesystem."""
        storage = SecureCookieStorage(temp_storage)
        profile = "user@domain.com/path"
        # Sanitize logic: "".join(c for c in profile_name if c.isalnum() or c in "_-")
        # Expected: "userdomaincompath"
        path = storage._get_cookie_path(profile)
        assert "userdomaincompath.enc" in path

    def test_static_generate_key(self):
        """Test static generate_key method."""
        key = SecureCookieStorage.generate_key()
        assert isinstance(key, str)
        # Should be a valid Fernet key
        Fernet(key.encode())

    def test_convenience_generate_key(self):
        """Test generate_cookie_encryption_key convenience function."""
        with patch("builtins.print"):
            key = generate_cookie_encryption_key()
            assert isinstance(key, str)

    def test_handle_invalid_token_backup_failure(self, temp_storage):
        """Test backup failure during invalid token handling."""
        storage = SecureCookieStorage(temp_storage)
        with patch("os.rename", side_effect=Exception("Rename failed")):
            # Should not crash
            storage._handle_invalid_token("path", "profile")
            
    def test_main_block(self):
        """Test the if __name__ == '__main__': block via subprocess to reach 100%."""
        import subprocess
        import sys
        # Run the module as a script
        result = subprocess.run(
            [sys.executable, "-m", "browser.secure_storage"],
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        assert result.returncode == 0
        assert "CRYPTOBOT_COOKIE_KEY=" in result.stdout

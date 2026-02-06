"""
Secure Cookie Storage Module

Provides encrypted storage for browser cookies using Fernet symmetric encryption.
Keys are managed via environment variables for security.
"""

import os
import json
import logging
import base64
from typing import Optional, List, Dict, Any
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from core.config import CONFIG_DIR

logger = logging.getLogger(__name__)

# Environment variable names for encryption keys
COOKIE_KEY_ENV = "CRYPTOBOT_COOKIE_KEY"
COOKIE_KEY_OLD_ENV = "CRYPTOBOT_COOKIE_KEY_OLD"  # For key rotation


class SecureCookieStorage:
    """
    Handles encrypted storage and retrieval of browser cookies.
    
    Uses Fernet encryption (AES-128-CBC with HMAC) for confidentiality
    and integrity. Supports key rotation via MultiFernet.
    """
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize the secure cookie storage.
        
        Args:
            storage_dir: Directory to store encrypted cookies. 
                        Defaults to 'cookies' in project root.
        """
        self.storage_dir = storage_dir or str(CONFIG_DIR / "cookies_encrypted")
        os.makedirs(self.storage_dir, exist_ok=True)
        
        self._fernet = self._initialize_fernet()
        
    def _initialize_fernet(self) -> Optional[Fernet]:
        """
        Initialize Fernet with keys from environment variables.
        Supports key rotation via MultiFernet.
        
        Note: Requires load_dotenv() to have been called before BrowserManager initialization.
        """
        primary_key = os.environ.get(COOKIE_KEY_ENV)
        old_key = os.environ.get(COOKIE_KEY_OLD_ENV)
        
        if not primary_key:
            # Try loading .env one more time in case it wasn't loaded yet
            try:
                from dotenv import load_dotenv
                # Load .env from project root
                env_path = os.path.join(os.getcwd(), ".env")
                load_dotenv(env_path, override=False) 
                primary_key = os.environ.get(COOKIE_KEY_ENV)
                if primary_key:
                    logger.info(f"Successfully loaded {COOKIE_KEY_ENV} after explicit load_dotenv() from {env_path}")
            except Exception as e:
                logger.debug(f"Auxiliary dotenv load failed: {e}")
        
        if not primary_key:
            # Fix #34: Try loading from persistent file fallback
            key_file = CONFIG_DIR / ".cookie_key"
            if key_file.exists():
                try:
                    primary_key = key_file.read_text().strip()
                    logger.info(f"Loaded {COOKIE_KEY_ENV} from persistent fallback file: {key_file}")
                    # Update environment for other modules
                    os.environ[COOKIE_KEY_ENV] = primary_key
                except Exception as e:
                    logger.warning(f"Failed to read fallback key file: {e}")

        if not primary_key:
            # Generate a new key if still none exists
            generated_key = Fernet.generate_key().decode()
            logger.warning(
                f"⚠️ Generated new cookie encryption key. Persistence will depend on saving this key."
            )
            
            # 1. Save to fallback file
            try:
                key_file = CONFIG_DIR / ".cookie_key"
                key_file.write_text(generated_key)
                logger.info(f"Persisted newly generated key to {key_file}")
            except Exception as e:
                logger.warning(f"Could not persist new key to fallback: {e}")
                
            # 2. Attempt to save to .env
            try:
                env_path = os.path.join(os.getcwd(), ".env")
                if os.path.exists(env_path):
                    with open(env_path, "a") as f:
                        f.write(f"\n{COOKIE_KEY_ENV}={generated_key}\n")
                    logger.info(f"✅ Appended new key to {env_path}")
                else:
                    with open(env_path, "w") as f:
                        f.write(f"{COOKIE_KEY_ENV}={generated_key}\n")
                    logger.info(f"✅ Created new {env_path} with key")
            except Exception as e:
                logger.debug(f"Could not append to .env: {e}")

            primary_key = generated_key
            os.environ[COOKIE_KEY_ENV] = primary_key
        
        try:
            # Support key rotation with MultiFernet
            keys = [Fernet(primary_key.encode())]
            if old_key:
                keys.append(Fernet(old_key.encode()))
                logger.info("Using key rotation with MultiFernet")
            return MultiFernet(keys) if len(keys) > 1 else keys[0]
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            return None
    
    def _get_cookie_path(self, profile_name: str) -> str:
        """Get the encrypted cookie file path for a profile."""
        # Sanitize profile name for filesystem
        safe_name = "".join(c for c in profile_name if c.isalnum() or c in "_-")
        return os.path.join(self.storage_dir, f"{safe_name}.enc")
    
    async def save_cookies(self, cookies: List[Dict[str, Any]], profile_name: str) -> bool:
        """
        Encrypt and save cookies to disk.
        
        Args:
            cookies: List of cookie dictionaries from browser context
            profile_name: Unique identifier for this profile
            
        Returns:
            True if saved successfully, False otherwise
        """
        if not self._fernet:
            logger.error("Encryption not initialized. Cannot save cookies securely.")
            return False
        
        try:
            # Serialize cookies to JSON
            cookie_data = json.dumps(cookies).encode('utf-8')
            
            # Encrypt
            encrypted_data = self._fernet.encrypt(cookie_data)
            
            # Save to file
            cookie_path = self._get_cookie_path(profile_name)
            with open(cookie_path, 'wb') as f:
                f.write(encrypted_data)
            
            logger.debug(f"Saved {len(cookies)} encrypted cookies for {profile_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save encrypted cookies for {profile_name}: {e}")
            return False
    
    async def load_cookies(self, profile_name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Load and decrypt cookies from disk.
        
        Args:
            profile_name: Unique identifier for this profile
            
        Returns:
            List of cookie dictionaries, or None if not found/decryption failed
        """
        if not self._fernet:
            logger.error("Encryption not initialized. Cannot load cookies securely.")
            return None
        
        cookie_path = self._get_cookie_path(profile_name)
        
        if not os.path.exists(cookie_path):
            logger.debug(f"No encrypted cookies found for {profile_name}")
            return None
        
        try:
            # Read encrypted data
            with open(cookie_path, 'rb') as f:
                encrypted_data = f.read()
            
            # Decrypt
            decrypted_data = self._fernet.decrypt(encrypted_data)
            
            # Deserialize
            cookies = json.loads(decrypted_data.decode('utf-8'))
            
            logger.info(f"Loaded {len(cookies)} encrypted cookies for {profile_name}")
            return cookies
            
        except InvalidToken:
            logger.error(f"Failed to decrypt cookies for {profile_name}. Key may have changed.")
            # Optionally delete corrupted file
            self._handle_invalid_token(cookie_path, profile_name)
            return None
        except Exception as e:
            logger.error(f"Failed to load encrypted cookies for {profile_name}: {e}")
            return None
    
    def _handle_invalid_token(self, cookie_path: str, profile_name: str):
        """Handle case where decryption fails due to key mismatch."""
        try:
            # Backup the corrupted file instead of deleting
            backup_path = f"{cookie_path}.backup"
            os.rename(cookie_path, backup_path)
            logger.warning(f"Moved invalid cookie file to {backup_path}")
        except Exception as e:
            logger.warning(f"Could not backup invalid cookie file: {e}")
    
    def delete_cookies(self, profile_name: str) -> bool:
        """
        Delete stored cookies for a profile.
        
        Args:
            profile_name: Unique identifier for this profile
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            cookie_path = self._get_cookie_path(profile_name)
            if os.path.exists(cookie_path):
                os.remove(cookie_path)
                logger.debug(f"Deleted encrypted cookies for {profile_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete cookies for {profile_name}: {e}")
            return False
    
    async def inject_aged_cookies(self, context: Any, profile_name: str) -> bool:
        """
        Add realistic aged cookies to appear as established browser.
        
        Injects 20-50 realistic cookies from common sites with backdated timestamps
        to make the browser appear as a long-established user, not a fresh install.
        
        Args:
            context: Browser context to inject cookies into
            profile_name: Profile identifier for logging
            
        Returns:
            True if cookies injected successfully
        """
        import random
        import secrets
        from datetime import datetime, timedelta
        
        try:
            # Common domains and cookie types
            aged_cookies = []
            
            # Generate 20-50 cookies
            cookie_count = random.randint(20, 50)
            
            # Common cookie templates
            templates = [
                # Google Analytics
                {"name": "_ga", "domain": ".google.com", "value": f"GA1.2.{secrets.randbelow(900000000) + 100000000}.{int(datetime.now().timestamp())}"},
                {"name": "_gid", "domain": ".google.com", "value": f"GA1.2.{secrets.randbelow(900000000) + 100000000}.{int(datetime.now().timestamp())}"},
                {"name": "_ga", "domain": ".youtube.com", "value": f"GA1.2.{secrets.randbelow(900000000) + 100000000}.{int(datetime.now().timestamp())}"},
                
                # Advertising cookies
                {"name": "IDE", "domain": ".doubleclick.net", "value": self._generate_random_id(32)},
                {"name": "test_cookie", "domain": ".doubleclick.net", "value": "CheckForPermission"},
                {"name": "NID", "domain": ".google.com", "value": self._generate_random_id(64)},
                
                # Social media
                {"name": "_fbp", "domain": ".facebook.com", "value": f"fb.1.{int(datetime.now().timestamp() * 1000)}.{secrets.randbelow(900000000) + 100000000}"},
                {"name": "fr", "domain": ".facebook.com", "value": self._generate_random_id(48)},
                {"name": "personalization_id", "domain": ".twitter.com", "value": f"\"{self._generate_random_id(22)}=="},
                
                # E-commerce
                {"name": "session-id", "domain": ".amazon.com", "value": self._generate_random_id(24)},
                {"name": "ubid-main", "domain": ".amazon.com", "value": self._generate_random_id(20)},
                
                # Preferences
                {"name": "PREF", "domain": ".google.com", "value": f"tz=UTC&f4=4000000&f5=20000&f6=40000000"},
                {"name": "CONSENT", "domain": ".google.com", "value": f"YES+cb.20{random.randint(200101, 251231)}-11-p0.en+FX+{random.randint(100, 999)}"},
                
                # Generic tracking
                {"name": "_gcl_au", "domain": ".google.com", "value": f"1.1.{secrets.randbelow(900000000) + 100000000}.{int(datetime.now().timestamp())}"},
                {"name": "_gat_gtag", "domain": ".google.com", "value": "1"},
            ]
            
            # Additional realistic domains
            extra_domains = [
                ".wikipedia.org", ".github.com", ".stackoverflow.com",
                ".reddit.com", ".medium.com", ".cloudflare.com"
            ]
            
            # Randomly select from templates and add extras
            selected_templates = random.sample(templates, min(len(templates), cookie_count - 10))
            
            # Add some random cookies for extra domains
            for domain in random.sample(extra_domains, min(len(extra_domains), 10)):
                selected_templates.append({
                    "name": random.choice(["session_id", "user_id", "pref", "lang", "theme"]),
                    "domain": domain,
                    "value": self._generate_random_id(random.randint(16, 32))
                })
            
            # Generate aged cookies with realistic timestamps
            now = datetime.now()
            for template in selected_templates[:cookie_count]:
                # Backdate created time: 7-30 days ago
                days_old = random.randint(7, 30)
                created_time = now - timedelta(days=days_old)
                
                # Some cookies are session, some persistent
                is_session = random.random() < 0.3  # 30% session cookies
                
                cookie = {
                    "name": template["name"],
                    "value": template["value"],
                    "domain": template["domain"],
                    "path": "/",
                    "secure": True,
                    "httpOnly": random.choice([True, False]),
                    "sameSite": random.choice(["Lax", "None", "Strict"]),
                }
                
                if not is_session:
                    # Persistent cookie: expires in 30-365 days
                    expires_days = random.randint(30, 365)
                    expires = created_time + timedelta(days=expires_days)
                    cookie["expires"] = expires.timestamp()
                
                aged_cookies.append(cookie)
            
            # Inject cookies into context
            await context.add_cookies(aged_cookies)
            
            logger.info(
                f"🍪 Injected {len(aged_cookies)} aged cookies for {profile_name} "
                f"({sum(1 for c in aged_cookies if 'expires' not in c)} session, "
                f"{sum(1 for c in aged_cookies if 'expires' in c)} persistent)"
            )
            return True
            
        except Exception as e:
            logger.warning(f"Failed to inject aged cookies for {profile_name}: {e}")
            return False
    
    def _generate_random_id(self, length: int) -> str:
        """Generate random alphanumeric ID for cookie values."""
        import string
        import secrets
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key for manual key creation."""
        return Fernet.generate_key().decode()


# Convenience function for generating keys
def generate_cookie_encryption_key() -> str:
    """Generate a new cookie encryption key. Store this securely!"""
    key = Fernet.generate_key().decode()
    print(f"Generated new cookie encryption key:")
    print(f"{COOKIE_KEY_ENV}={key}")
    return key


if __name__ == "__main__":
    # When run directly, generate a new key
    generate_cookie_encryption_key()

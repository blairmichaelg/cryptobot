"""Secure Cookie Storage Module.

Provides encrypted storage for browser cookies using Fernet symmetric
encryption.  Keys are managed via environment variables for security.
"""

import os
import json
import logging
import random
import string
import base64
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from core.config import CONFIG_DIR

logger = logging.getLogger(__name__)

# Environment variable names for encryption keys
COOKIE_KEY_ENV = "CRYPTOBOT_COOKIE_KEY"
COOKIE_KEY_OLD_ENV = "CRYPTOBOT_COOKIE_KEY_OLD"  # For key rotation


class SecureCookieStorage:
    """Handles encrypted storage and retrieval of browser cookies.

    Uses Fernet encryption (AES-128-CBC with HMAC) for confidentiality
    and integrity.  Supports key rotation via MultiFernet.
    """

    def __init__(
        self, storage_dir: Optional[str] = None,
    ) -> None:
        """Initialise the secure cookie storage.

        Args:
            storage_dir: Directory to store encrypted cookies.
                Defaults to ``cookies_encrypted`` inside the
                project config directory.
        """
        self.storage_dir = storage_dir or str(
            CONFIG_DIR / "cookies_encrypted"
        )
        os.makedirs(self.storage_dir, exist_ok=True)

        self._fernet: Optional[
            Union[Fernet, MultiFernet]
        ] = self._initialize_fernet()

    def _initialize_fernet(
        self,
    ) -> Optional[Union[Fernet, MultiFernet]]:
        """Initialise Fernet with keys from environment variables.

        Supports key rotation via MultiFernet.

        Note:
            Requires ``load_dotenv()`` to have been called before
            ``BrowserManager`` initialisation.

        Returns:
            A ``Fernet`` or ``MultiFernet`` instance, or ``None``
            on failure.
        """
        primary_key = os.environ.get(COOKIE_KEY_ENV)
        old_key = os.environ.get(COOKIE_KEY_OLD_ENV)

        if not primary_key:
            # Try loading .env in case it wasn't loaded yet
            try:
                from dotenv import load_dotenv
                env_path = os.path.join(os.getcwd(), ".env")
                load_dotenv(env_path, override=False)
                primary_key = os.environ.get(COOKIE_KEY_ENV)
                if primary_key:
                    logger.info(
                        "Successfully loaded %s after explicit"
                        " load_dotenv() from %s",
                        COOKIE_KEY_ENV, env_path,
                    )
            except Exception as e:
                logger.debug(
                    "Auxiliary dotenv load failed: %s", e,
                )

        if not primary_key:
            # Fix #34: Try loading from persistent file fallback
            key_file = CONFIG_DIR / ".cookie_key"
            if key_file.exists():
                try:
                    primary_key = key_file.read_text().strip()
                    logger.info(
                        "Loaded %s from persistent fallback"
                        " file: %s",
                        COOKIE_KEY_ENV, key_file,
                    )
                    # Update environment for other modules
                    os.environ[COOKIE_KEY_ENV] = primary_key
                except Exception as e:
                    logger.warning(
                        "Failed to read fallback key file: %s", e,
                    )

        if not primary_key:
            # Generate a new key if still none exists
            generated_key = Fernet.generate_key().decode()
            logger.warning(
                "Generated new cookie encryption key."
                " Persistence will depend on saving this key."
            )

            # 1. Save to fallback file
            try:
                key_file = CONFIG_DIR / ".cookie_key"
                key_file.write_text(generated_key)
                logger.info(
                    "Persisted newly generated key to %s",
                    key_file,
                )
            except Exception as e:
                logger.warning(
                    "Could not persist new key to fallback: %s",
                    e,
                )

            # 2. Attempt to save to .env
            try:
                env_path = os.path.join(os.getcwd(), ".env")
                if os.path.exists(env_path):
                    with open(env_path, "a") as f:
                        f.write(
                            f"\n{COOKIE_KEY_ENV}="
                            f"{generated_key}\n"
                        )
                    logger.info(
                        "Appended new key to %s", env_path,
                    )
                else:
                    with open(env_path, "w") as f:
                        f.write(
                            f"{COOKIE_KEY_ENV}="
                            f"{generated_key}\n"
                        )
                    logger.info(
                        "Created new %s with key", env_path,
                    )
            except Exception as e:
                logger.debug(
                    "Could not append to .env: %s", e,
                )

            primary_key = generated_key
            os.environ[COOKIE_KEY_ENV] = primary_key

        try:
            # Support key rotation with MultiFernet
            keys = [Fernet(primary_key.encode())]
            if old_key:
                keys.append(Fernet(old_key.encode()))
                logger.info(
                    "Using key rotation with MultiFernet",
                )
            if len(keys) > 1:
                return MultiFernet(keys)
            return keys[0]
        except Exception as e:
            logger.error(
                "Failed to initialize encryption: %s", e,
            )
            return None

    def _get_cookie_path(self, profile_name: str) -> str:
        """Get the encrypted cookie file path for a profile.

        Args:
            profile_name: Unique profile identifier.

        Returns:
            Absolute path to the ``.enc`` cookie file.
        """
        # Sanitize profile name for filesystem
        safe_name = "".join(
            c for c in profile_name if c.isalnum() or c in "_-"
        )
        return os.path.join(self.storage_dir, f"{safe_name}.enc")

    async def save_cookies(
        self,
        cookies: List[Dict[str, Any]],
        profile_name: str,
    ) -> bool:
        """Encrypt and save cookies to disk.

        Args:
            cookies: List of cookie dicts from browser context.
            profile_name: Unique identifier for this profile.

        Returns:
            ``True`` if saved successfully, ``False`` otherwise.
        """
        if not self._fernet:
            logger.error(
                "Encryption not initialized."
                " Cannot save cookies securely."
            )
            return False

        try:
            # Serialize cookies to JSON
            cookie_data = json.dumps(cookies).encode("utf-8")

            # Encrypt
            encrypted_data = self._fernet.encrypt(cookie_data)

            # Save to file
            cookie_path = self._get_cookie_path(profile_name)
            with open(cookie_path, "wb") as f:
                f.write(encrypted_data)

            logger.debug(
                "Saved %d encrypted cookies for %s",
                len(cookies), profile_name,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to save encrypted cookies for %s: %s",
                profile_name, e,
            )
            return False

    async def load_cookies(
        self, profile_name: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Load and decrypt cookies from disk.

        Args:
            profile_name: Unique identifier for this profile.

        Returns:
            List of cookie dicts, or ``None`` if not found or
            decryption failed.
        """
        if not self._fernet:
            logger.error(
                "Encryption not initialized."
                " Cannot load cookies securely."
            )
            return None

        cookie_path = self._get_cookie_path(profile_name)

        if not os.path.exists(cookie_path):
            logger.debug(
                "No encrypted cookies found for %s",
                profile_name,
            )
            return None

        try:
            # Read encrypted data
            with open(cookie_path, "rb") as f:
                encrypted_data = f.read()

            # Decrypt
            decrypted_data = self._fernet.decrypt(encrypted_data)

            # Deserialize
            cookies = json.loads(
                decrypted_data.decode("utf-8"),
            )

            logger.info(
                "Loaded %d encrypted cookies for %s",
                len(cookies), profile_name,
            )
            return cookies

        except InvalidToken:
            logger.error(
                "Failed to decrypt cookies for %s."
                " Key may have changed.",
                profile_name,
            )
            # Optionally delete corrupted file
            self._handle_invalid_token(
                cookie_path, profile_name,
            )
            return None
        except Exception as e:
            logger.error(
                "Failed to load encrypted cookies for %s: %s",
                profile_name, e,
            )
            return None

    def _handle_invalid_token(
        self, cookie_path: str, profile_name: str,
    ) -> None:
        """Handle decryption failure due to key mismatch.

        Backs up the corrupted file instead of deleting it.

        Args:
            cookie_path: Path to the invalid cookie file.
            profile_name: Profile identifier (for logging).
        """
        try:
            # Backup the corrupted file instead of deleting
            backup_path = f"{cookie_path}.backup"
            os.rename(cookie_path, backup_path)
            logger.warning(
                "Moved invalid cookie file to %s", backup_path,
            )
        except Exception as e:
            logger.warning(
                "Could not backup invalid cookie file: %s", e,
            )

    def delete_cookies(self, profile_name: str) -> bool:
        """Delete stored cookies for a profile.

        Args:
            profile_name: Unique identifier for this profile.

        Returns:
            ``True`` if deleted, ``False`` otherwise.
        """
        try:
            cookie_path = self._get_cookie_path(profile_name)
            if os.path.exists(cookie_path):
                os.remove(cookie_path)
                logger.debug(
                    "Deleted encrypted cookies for %s",
                    profile_name,
                )
                return True
            return False
        except Exception as e:
            logger.error(
                "Failed to delete cookies for %s: %s",
                profile_name, e,
            )
            return False

    async def inject_aged_cookies(
        self,
        context: Any,
        profile_name: str,
    ) -> bool:
        """Add realistic aged cookies to appear as established browser.

        Injects 20-50 realistic cookies from common sites with
        backdated timestamps to make the browser appear as a
        long-established user, not a fresh install.

        Args:
            context: Browser context to inject cookies into.
            profile_name: Profile identifier for logging.

        Returns:
            ``True`` if cookies injected successfully.
        """
        try:
            # Common domains and cookie types
            aged_cookies: List[Dict[str, Any]] = []

            # Generate 20-50 cookies
            cookie_count = random.randint(20, 50)
            now = datetime.now()
            now_ts = int(now.timestamp())
            now_ms = int(now.timestamp() * 1000)

            # Common cookie templates
            templates = [
                # Google Analytics
                {
                    "name": "_ga",
                    "domain": ".google.com",
                    "value": (
                        f"GA1.2."
                        f"{random.randint(100000000, 999999999)}"
                        f".{now_ts}"
                    ),
                },
                {
                    "name": "_gid",
                    "domain": ".google.com",
                    "value": (
                        f"GA1.2."
                        f"{random.randint(100000000, 999999999)}"
                        f".{now_ts}"
                    ),
                },
                {
                    "name": "_ga",
                    "domain": ".youtube.com",
                    "value": (
                        f"GA1.2."
                        f"{random.randint(100000000, 999999999)}"
                        f".{now_ts}"
                    ),
                },
                # Advertising cookies
                {
                    "name": "IDE",
                    "domain": ".doubleclick.net",
                    "value": self._generate_random_id(32),
                },
                {
                    "name": "test_cookie",
                    "domain": ".doubleclick.net",
                    "value": "CheckForPermission",
                },
                {
                    "name": "NID",
                    "domain": ".google.com",
                    "value": self._generate_random_id(64),
                },
                # Social media
                {
                    "name": "_fbp",
                    "domain": ".facebook.com",
                    "value": (
                        f"fb.1.{now_ms}."
                        f"{random.randint(100000000, 999999999)}"
                    ),
                },
                {
                    "name": "fr",
                    "domain": ".facebook.com",
                    "value": self._generate_random_id(48),
                },
                {
                    "name": "personalization_id",
                    "domain": ".twitter.com",
                    "value": (
                        f'"{self._generate_random_id(22)}=='
                    ),
                },
                # E-commerce
                {
                    "name": "session-id",
                    "domain": ".amazon.com",
                    "value": self._generate_random_id(24),
                },
                {
                    "name": "ubid-main",
                    "domain": ".amazon.com",
                    "value": self._generate_random_id(20),
                },
                # Preferences
                {
                    "name": "PREF",
                    "domain": ".google.com",
                    "value": (
                        "tz=UTC&f4=4000000"
                        "&f5=20000&f6=40000000"
                    ),
                },
                {
                    "name": "CONSENT",
                    "domain": ".google.com",
                    "value": (
                        f"YES+cb."
                        f"20{random.randint(200101, 251231)}"
                        f"-11-p0.en+FX+"
                        f"{random.randint(100, 999)}"
                    ),
                },
                # Generic tracking
                {
                    "name": "_gcl_au",
                    "domain": ".google.com",
                    "value": (
                        f"1.1."
                        f"{random.randint(100000000, 999999999)}"
                        f".{now_ts}"
                    ),
                },
                {
                    "name": "_gat_gtag",
                    "domain": ".google.com",
                    "value": "1",
                },
            ]

            # Additional realistic domains
            extra_domains = [
                ".wikipedia.org", ".github.com",
                ".stackoverflow.com", ".reddit.com",
                ".medium.com", ".cloudflare.com",
            ]

            # Randomly select from templates and add extras
            template_limit = min(
                len(templates), cookie_count - 10,
            )
            selected_templates = random.sample(
                templates, template_limit,
            )

            # Add some random cookies for extra domains
            extra_sample = random.sample(
                extra_domains, min(len(extra_domains), 10),
            )
            for domain in extra_sample:
                cookie_name = random.choice([
                    "session_id", "user_id",
                    "pref", "lang", "theme",
                ])
                selected_templates.append({
                    "name": cookie_name,
                    "domain": domain,
                    "value": self._generate_random_id(
                        random.randint(16, 32),
                    ),
                })

            # Generate aged cookies with realistic timestamps
            for template in selected_templates[:cookie_count]:
                # Backdate created time: 7-30 days ago
                days_old = random.randint(7, 30)
                created_time = now - timedelta(days=days_old)

                # 30% session cookies
                is_session = random.random() < 0.3

                cookie: Dict[str, Any] = {
                    "name": template["name"],
                    "value": template["value"],
                    "domain": template["domain"],
                    "path": "/",
                    "secure": True,
                    "httpOnly": random.choice([True, False]),
                    "sameSite": random.choice([
                        "Lax", "None", "Strict",
                    ]),
                }

                if not is_session:
                    # Persistent cookie: expires in 30-365 days
                    expires_days = random.randint(30, 365)
                    expires = created_time + timedelta(
                        days=expires_days,
                    )
                    cookie["expires"] = expires.timestamp()

                aged_cookies.append(cookie)

            # Inject cookies into context
            await context.add_cookies(aged_cookies)

            session_count = sum(
                1 for c in aged_cookies if "expires" not in c
            )
            persistent_count = sum(
                1 for c in aged_cookies if "expires" in c
            )
            logger.info(
                "Injected %d aged cookies for %s"
                " (%d session, %d persistent)",
                len(aged_cookies), profile_name,
                session_count, persistent_count,
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to inject aged cookies for %s: %s",
                profile_name, e,
            )
            return False

    def _generate_random_id(self, length: int) -> str:
        """Generate a random alphanumeric ID for cookie values.

        Args:
            length: Number of characters to generate.

        Returns:
            Random alphanumeric string of the given length.
        """
        chars = string.ascii_letters + string.digits
        return "".join(
            random.choice(chars) for _ in range(length)
        )

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key for manual key creation.

        Returns:
            A base64-encoded Fernet key string.
        """
        return Fernet.generate_key().decode()


# Convenience function for generating keys
def generate_cookie_encryption_key() -> str:
    """Generate a new cookie encryption key.

    Prints the key in a format suitable for ``.env`` files.

    Returns:
        The generated key string.
    """
    key = Fernet.generate_key().decode()
    print("Generated new cookie encryption key:")
    print(f"{COOKIE_KEY_ENV}={key}")
    return key


if __name__ == "__main__":
    # When run directly, generate a new key
    generate_cookie_encryption_key()

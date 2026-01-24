"""
Auto-Registration Script for Faucet Accounts

Self-healing account registration with:
- Temp email integration (temp-mail.org API)
- Credential generation with Faker
- Automated email verification
- Encrypted credential storage
- Account rotation on bans
"""

import asyncio
import logging
import json
import os
import base64
import aiohttp
import random
import string
from pathlib import Path
from typing import Optional, Dict, Any, List
from cryptography.fernet import Fernet
from datetime import datetime

# Optional import for Faker (provides better username generation)
try:
    from faker import Faker
    _fake = Faker()
except ImportError:
    # Faker is optional - provide fallback for basic username generation
    _fake = None

# Setup
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
VAULT_FILE = CONFIG_DIR / "accounts_vault.enc"
VAULT_KEY_FILE = CONFIG_DIR / ".vault_key"

logger = logging.getLogger(__name__)


class TempMailAPI:
    """Integration with temp-mail.org API for disposable emails."""
    
    API_BASE = "https://api.temp-mail.org"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def get_random_email(self) -> str:
        """Generate a random temp email address."""
        # Generate random username
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        
        # Get available domains
        if self.session is None:
            return f"{username}@tempmail.com"
        
        try:
            async with self.session.get(f"{self.API_BASE}/request/domains/format/json") as resp:
                if resp.status == 200:
                    domains = await resp.json()
                    domain = random.choice(domains)
                    return f"{username}{domain}"
        except Exception:  # pylint: disable=bare-except
            pass
        
        # Fallback
        return f"{username}@tempmail.com"
    
    async def check_inbox(self, email: str, timeout: int = 60) -> List[Dict[str, Any]]:
        """Poll inbox for new emails with timeout.
        
        Args:
            email: Email address to check
            timeout: Max wait time in seconds
            
        Returns:
            List of email messages
        """
        if self.session is None:
            return []
            
        email_hash = base64.b64encode(email.encode()).decode()
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                async with self.session.get(f"{self.API_BASE}/request/mail/id/{email_hash}/format/json") as resp:
                    if resp.status == 200:
                        messages = await resp.json()
                        if messages:
                            return messages
            except Exception:  # pylint: disable=bare-except
                pass
            
            await asyncio.sleep(5)
        
        return []
    
    async def extract_verification_link(self, email_body: str) -> Optional[str]:
        """Extract verification/activation link from email body."""
        import re
        
        # Common patterns for verification links
        patterns = [
            r'https?://[^\s]+verify[^\s]*',
            r'https?://[^\s]+activate[^\s]*',
            r'https?://[^\s]+confirm[^\s]*',
            r'https?://[^\s]+registration[^\s]*'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, email_body, re.IGNORECASE)
            if match:
                return match.group(0).rstrip('">\'')
        
        return None


class AccountVault:
    """Encrypted storage for account credentials."""
    
    def __init__(self):
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)
    
    def _load_or_create_key(self) -> bytes:
        """Load existing vault key or create new one."""
        if VAULT_KEY_FILE.exists():
            return VAULT_KEY_FILE.read_bytes()
        
        key = Fernet.generate_key()
        VAULT_KEY_FILE.write_bytes(key)
        VAULT_KEY_FILE.chmod(0o600)  # Restrict permissions
        logger.info("Created new vault encryption key")
        return key
    
    def save_account(self, faucet: str, username: str, password: str, email: str, metadata: Optional[Dict] = None):
        """Save account credentials to encrypted vault."""
        accounts = self.load_all_accounts()
        
        account_data = {
            "faucet": faucet,
            "username": username,
            "password": password,
            "email": email,
            "created_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        # Add or update
        key = f"{faucet}:{username}"
        accounts[key] = account_data
        
        # Encrypt and save
        encrypted = self.cipher.encrypt(json.dumps(accounts).encode())
        VAULT_FILE.write_bytes(encrypted)
        logger.info(f"Saved account {key} to vault")
    
    def load_all_accounts(self) -> Dict[str, Dict]:
        """Load all accounts from vault."""
        if not VAULT_FILE.exists():
            return {}
        
        try:
            encrypted = VAULT_FILE.read_bytes()
            decrypted = self.cipher.decrypt(encrypted)
            return json.loads(decrypted)
        except Exception as e:
            logger.error(f"Failed to load vault: {e}")
            return {}
    
    def mark_burned(self, faucet: str, username: str):
        """Mark account as burned/banned."""
        accounts = self.load_all_accounts()
        key = f"{faucet}:{username}"
        
        if key in accounts:
            accounts[key]["metadata"]["burned"] = True
            accounts[key]["metadata"]["burned_at"] = datetime.utcnow().isoformat()
            encrypted = self.cipher.encrypt(json.dumps(accounts).encode())
            VAULT_FILE.write_bytes(encrypted)
            logger.warning(f"Marked account {key} as burned")


class FaucetRegistrar:
    """Automated registration for faucet sites."""
    
    FAUCET_CONFIGS = {
        "firefaucet": {
            "url": "https://firefaucet.win/register",
            "selectors": {
                "username": "#username",
                "email": "#email",
                "password": "#password",
                "password_confirm": "#password_confirm",
                "submit": "button[type='submit']"
            },
            "verification_required": True
        },
        "dutchy": {
            "url": "https://autofaucet.dutchycorp.space/register.php",
            "selectors": {
                "username": "input[name='username']",
                "email": "input[name='email']",
                "password": "input[name='password']",
                "submit": "button[type='submit']"
            },
            "verification_required": True
        },
        "coinpayu": {
            "url": "https://www.coinpayu.com/register",
            "selectors": {
                "email": "input[placeholder='Email']",
                "password": "input[placeholder='Password']",
                "password_confirm": "input[placeholder='Confirm Password']",
                "submit": "button:has-text('Sign Up')"
            },
            "verification_required": True
        }
    }
    
    def __init__(self, browser_manager, captcha_solver):
        self.browser_manager = browser_manager
        self.captcha_solver = captcha_solver
        self.vault = AccountVault()
    
    def generate_credentials(self) -> Dict[str, str]:
        """Generate random credentials using Faker."""
        if _fake is None:
            username = f"user_{random.randint(10000, 99999)}"
        else:
            username = _fake.user_name() + str(random.randint(100, 999))
        password = self._generate_secure_password()
        
        return {
            "username": username,
            "password": password
        }
    
    def _generate_secure_password(self, length: int = 16) -> str:
        """Generate strong random password."""
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(random.choice(chars) for _ in range(length))
        return password
    
    async def register_account(self, faucet: str) -> Optional[Dict[str, str]]:
        """Register new account on specified faucet.
        
        Args:
            faucet: Faucet name (firefaucet, dutchy, coinpayu, etc.)
            
        Returns:
            Account credentials if successful, None otherwise
        """
        if faucet not in self.FAUCET_CONFIGS:
            logger.error(f"Unknown faucet: {faucet}")
            return None
        
        config = self.FAUCET_CONFIGS[faucet]
        creds = self.generate_credentials()
        
        try:
            async with TempMailAPI() as temp_mail:
                # Generate temp email
                email = await temp_mail.get_random_email()
                logger.info(f"Generated temp email: {email}")
                
                # Create browser context
                context = await self.browser_manager.get_or_create_context(
                    profile={"username": creds["username"], "faucet": faucet}
                )
                page = await context.new_page()
                
                # Navigate to registration page
                logger.info(f"Navigating to {config['url']}")
                await page.goto(config['url'])
                
                # Fill registration form
                selectors = config['selectors']
                
                if 'username' in selectors:
                    await page.fill(selectors['username'], creds['username'])
                
                await page.fill(selectors['email'], email)
                await page.fill(selectors['password'], creds['password'])
                
                if 'password_confirm' in selectors:
                    await page.fill(selectors['password_confirm'], creds['password'])
                
                # Solve CAPTCHA if present
                logger.info("Checking for CAPTCHA...")
                await self.captcha_solver.solve_captcha(page)
                
                # Submit registration
                await page.click(selectors['submit'])
                await page.wait_for_load_state()
                
                # Check for success
                if await page.locator(".alert-success, .toast-success, :has-text('successfully')").count() > 0:
                    logger.info(f"✅ Registration successful for {faucet}")
                    
                    # Handle email verification if required
                    if config.get('verification_required'):
                        logger.info("Waiting for verification email...")
                        emails = await temp_mail.check_inbox(email, timeout=120)
                        
                        if emails:
                            # Extract verification link
                            email_body = emails[0].get('mail_text', '')
                            verify_link = await temp_mail.extract_verification_link(email_body)
                            
                            if verify_link:
                                logger.info(f"Clicking verification link: {verify_link}")
                                await page.goto(verify_link)
                                await page.wait_for_load_state()
                                logger.info("✅ Account verified")
                    
                    # Save to vault
                    self.vault.save_account(
                        faucet=faucet,
                        username=creds['username'],
                        password=creds['password'],
                        email=email,
                        metadata={"auto_registered": True}
                    )
                    
                    await context.close()
                    return {**creds, "email": email}
                
                else:
                    # Check for errors
                    error = await page.locator(".alert-danger, .error-message").first.text_content() if await page.locator(".alert-danger, .error-message").count() > 0 else "Unknown error"
                    logger.error(f"Registration failed: {error}")
                    await context.close()
                    return None
        
        except Exception as e:
            logger.error(f"Registration error for {faucet}: {e}")
            return None
    
    async def rotate_burned_accounts(self, faucet: str, burned_username: str) -> Optional[Dict[str, str]]:
        """Detect ban and create replacement account.
        
        Args:
            faucet: Faucet name
            burned_username: Username that got banned
            
        Returns:
            New account credentials if successful
        """
        logger.warning(f"Rotating burned account {burned_username} on {faucet}")
        
        # Mark old account as burned
        self.vault.mark_burned(faucet, burned_username)
        
        # Create new account
        new_account = await self.register_account(faucet)
        
        if new_account:
            logger.info(f"✅ Created replacement account: {new_account['username']}")
            return new_account
        
        return None


async def main():
    """Demo: Register accounts for all faucets."""
    from browser.instance import BrowserManager
    from solvers.captcha import CaptchaSolver
    from core.config import BotSettings
    
    settings = BotSettings()
    browser_manager = BrowserManager(headless=settings.headless)
    captcha_solver = CaptchaSolver(api_key=settings.twocaptcha_api_key or "")
    
    registrar = FaucetRegistrar(browser_manager, captcha_solver)
    
    # Register on all configured faucets
    for faucet in ["firefaucet", "dutchy", "coinpayu"]:
        logger.info(f"\n{'='*50}")
        logger.info(f"Registering on {faucet}")
        logger.info(f"{'='*50}")
        
        account = await registrar.register_account(faucet)
        
        if account:
            print(f"\n✅ SUCCESS: {faucet}")
            print(f"Username: {account['username']}")
            print(f"Password: {account['password']}")
            print(f"Email: {account['email']}")
        else:
            print(f"\n❌ FAILED: {faucet}")
        
        await asyncio.sleep(5)
    
    await browser_manager.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

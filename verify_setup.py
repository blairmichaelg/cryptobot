import asyncio
import logging
from core.config import BotSettings
from solvers.captcha import CaptchaSolver
from core.wallet_manager import WalletDaemon
import aiohttp

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("SetupVerifier")

async def test_captcha(settings: BotSettings):
    logger.info("--- Testing Captcha Solver ---")
    solver = CaptchaSolver(api_key=settings.twocaptcha_api_key or settings.capsolver_api_key)
    if not solver.api_key:
        logger.warning("❌ No API Key found.")
        return
    
    # Simple check for 2captcha (we don't solve, just check balance)
    if settings.twocaptcha_api_key:
        url = f"http://2captcha.com/res.php?key={solver.api_key}&action=getbalance&json=1"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    if data.get('status') == 1:
                        logger.info(f"✅ 2Captcha Connected. Balance: ${data.get('request')}")
                    else:
                        logger.error(f"❌ 2Captcha Error: {data}")
        except Exception as e:
            logger.error(f"❌ 2Captcha Connection Failed: {e}")

async def test_wallet(settings: BotSettings):
    logger.info("\n--- Testing Wallet Daemon ---")
    daemon = WalletDaemon(settings.electrum_rpc_url, settings.electrum_rpc_user, settings.electrum_rpc_pass)
    connected = await daemon.check_connection()
    if connected:
        logger.info(f"✅ Connected to Wallet RPC at {settings.electrum_rpc_url}")
        balance = await daemon.get_balance()
        logger.info(f"💰 Current Wallet Balance: {balance}")
    else:
        logger.warning(f"⚠️ Could not connect to Wallet RPC. Automated withdrawals to local wallet will fail.")

async def test_proxies(settings: BotSettings):
    logger.info("\n--- Testing Proxies ---")
    if not settings.accounts:
        logger.warning("No accounts found in config to test proxies for.")
        return

    async with aiohttp.ClientSession() as session:
        for acc in settings.accounts:
            proxy = acc.proxy or (acc.proxy_pool[0] if acc.proxy_pool else None)
            if not proxy: continue
            
            logger.info(f"Testing proxy for {acc.username} ({acc.faucet})...")
            try:
                # Test connectivity and get IP
                async with session.get("https://api.ipify.org?format=json", proxy=proxy, timeout=10) as resp:
                    data = await resp.json()
                    logger.info(f"✅ Proxy working. IP: {data.get('ip')}")
            except Exception as e:
                logger.error(f"❌ Proxy Failed for {acc.username}: {e}")

async def main():
    settings = BotSettings()
    await test_captcha(settings)
    await test_wallet(settings)
    await test_proxies(settings)
    logger.info("\nVerification Complete.")

if __name__ == "__main__":
    asyncio.run(main())

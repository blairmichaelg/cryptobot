import asyncio
import json
from core.config import CONFIG_DIR
from core.wallet_manager import WalletDaemon


def load_wallet_addresses() -> dict:
    config_path = CONFIG_DIR / "faucet_config.json"
    if not config_path.exists():
        return {}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    wallet_addresses = data.get("wallet_addresses")
    return wallet_addresses if isinstance(wallet_addresses, dict) else {}

async def main():
    wallet_addresses = load_wallet_addresses()
    if not wallet_addresses:
        print("No balances found or no wallet addresses configured.")
        return

    wallet = WalletDaemon({}, "", "")
    try:
        balances = await wallet.get_balances_for_addresses(wallet_addresses)
    finally:
        await wallet.close()

    if not balances:
        print("No balances found or no wallet addresses configured.")
        return
    print("Cake/Direct Wallet Balances:")
    for coin, amt in sorted(balances.items()):
        print(f"- {coin}: {amt}")

if __name__ == "__main__":
    asyncio.run(main())

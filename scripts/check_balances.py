import asyncio
from core.config import BotSettings
from core.wallet_manager import WalletDaemon

async def main():
    settings = BotSettings()
    wallet = WalletDaemon({}, "", "")
    balances = await wallet.get_balances_for_addresses(settings.wallet_addresses)
    if not balances:
        print("No balances found or no wallet addresses configured.")
        return
    print("Cake/Direct Wallet Balances:")
    for coin, amt in sorted(balances.items()):
        print(f"- {coin}: {amt}")

if __name__ == "__main__":
    asyncio.run(main())

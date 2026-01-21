#!/usr/bin/env python
import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Add project root to path
import sys
sys.path.append(os.getcwd())

from core.config import BotSettings
from core.wallet_manager import WalletDaemon

DEFAULT_COINS = ["BTC", "LTC", "DOGE"]
PLACEHOLDER_VALUES = {"YOUR_DOGE_ADDRESS", "YOUR_ADDRESS", "", None}


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_config(path: Path, config: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)


def get_validation_patterns(config: Dict[str, Any]) -> Dict[str, str]:
    return config.get("validation_patterns", {})


def is_placeholder(addr: Optional[str]) -> bool:
    if addr is None:
        return True
    if isinstance(addr, str) and addr.strip() in PLACEHOLDER_VALUES:
        return True
    return False


def validate_address_format(address: str, pattern: Optional[str]) -> bool:
    if not pattern:
        return True
    import re
    return re.match(pattern, address) is not None


async def audit_wallets(config_path: Path, generate: bool, write: bool) -> None:
    config = load_config(config_path)
    wallet_addresses: Dict[str, Any] = config.get("wallet_addresses", {})
    validation_patterns = get_validation_patterns(config)

    settings = BotSettings()
    wallet = WalletDaemon(settings.wallet_rpc_urls, settings.electrum_rpc_user, settings.electrum_rpc_pass)

    print("Wallet audit summary:")
    for coin, entry in wallet_addresses.items():
        address = entry.get("address") if isinstance(entry, dict) else entry
        enabled = entry.get("enabled", True) if isinstance(entry, dict) else True
        pattern = validation_patterns.get(coin)
        if not enabled:
            print(f"- {coin}: disabled")
            continue
        if is_placeholder(address):
            print(f"- {coin}: MISSING/PLACEHOLDER")
            continue
        if not validate_address_format(address, pattern):
            print(f"- {coin}: INVALID FORMAT")
            continue
        print(f"- {coin}: OK")

    # FaucetPay awareness
    if settings.use_faucetpay:
        has_fp = any(
            getattr(settings, f"faucetpay_{c.lower()}_address", None)
            for c in ["BTC", "LTC", "DOGE", "BCH", "TRX", "ETH", "BNB", "SOL", "TON", "DASH", "POLYGON", "USDT"]
        )
        if not has_fp:
            print("\nNote: FaucetPay mode is enabled but no FaucetPay addresses are set in .env.")
            print("      Direct wallet addresses will be used as fallback.")

    # Connection/balance checks
    print("\nWallet daemon connectivity:")
    for coin in DEFAULT_COINS:
        ok = await wallet.check_connection(coin)
        if not ok:
            print(f"- {coin}: NOT CONNECTED")
            continue
        bal = await wallet.get_balance(coin)
        print(f"- {coin}: CONNECTED, balance={bal}")

    updates: Dict[str, Tuple[str, str]] = {}

    if generate:
        for coin in DEFAULT_COINS:
            entry = wallet_addresses.get(coin, {})
            address = entry.get("address") if isinstance(entry, dict) else entry
            if not is_placeholder(address):
                continue

            ok = await wallet.check_connection(coin)
            if not ok:
                print(f"- {coin}: cannot generate address (daemon not connected)")
                continue

            new_addr = await wallet.get_unused_address(coin)
            if not new_addr:
                print(f"- {coin}: failed to generate new address")
                continue

            updates[coin] = (address or "", new_addr)
            if isinstance(entry, dict):
                entry["address"] = new_addr
                entry["enabled"] = True
                wallet_addresses[coin] = entry
            else:
                wallet_addresses[coin] = {"address": new_addr, "enabled": True}

    if updates:
        print("\nGenerated addresses:")
        for coin, (_old, new) in updates.items():
            print(f"- {coin}: {new}")

        if write:
            config["wallet_addresses"] = wallet_addresses
            save_config(config_path, config)
            print(f"\nSaved updates to {config_path}")
        else:
            print("\nRun with --write to persist generated addresses.")

    await wallet.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and optionally generate wallet addresses")
    parser.add_argument("--config", default="config/faucet_config.json", help="Path to faucet_config.json")
    parser.add_argument("--generate", action="store_true", help="Generate missing BTC/LTC/DOGE addresses via wallet daemon")
    parser.add_argument("--write", action="store_true", help="Write any generated addresses back to config")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    asyncio.run(audit_wallets(config_path, args.generate, args.write))


if __name__ == "__main__":
    main()

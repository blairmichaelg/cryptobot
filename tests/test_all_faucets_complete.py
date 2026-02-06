"""
Comprehensive faucet test suite with detailed reporting.
Tests all 18 faucets systematically and generates a report.
"""
import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

from core.config import BotSettings
from browser.instance import BrowserManager
from core.registry import FAUCET_REGISTRY, get_faucet_class
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# All faucets to test
ALL_FAUCETS = [
    "firefaucet",
    "cointiply",
    "dutchy",
    "coinpayu",
    "adbtc",
    "faucetcrypto",
    "freebitcoin",
    "litepick",
    "tronpick",
    "dogepick",
    "solpick",
    "binpick",
    "bchpick",
    "tonpick",
    "polygonpick",
    "dashpick",
    "ethpick",
    "usdpick",
]

async def test_single_faucet(faucet_name: str, settings: BotSettings, headless: bool = True):
    """Test login for a single faucet."""
    result = {
        "faucet": faucet_name,
        "status": "unknown",
        "login_success": False,
        "balance": None,
        "timer": None,
        "error": None,
        "notes": []
    }
    
    browser = None
    try:
        # Get credentials
        env_prefix = faucet_name.upper()
        username = os.getenv(f"{env_prefix}_USERNAME")
        password = os.getenv(f"{env_prefix}_PASSWORD")
        
        if not username or not password:
            result["status"] = "no_credentials"
            result["error"] = f"Missing {env_prefix}_USERNAME or {env_prefix}_PASSWORD"
            result["notes"].append("Add credentials to .env file")
            return result
        
        # Get faucet class
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            result["status"] = "not_registered"
            result["error"] = "Faucet class not found in registry"
            return result
        
        # Create browser
        browser = BrowserManager(
            headless=headless,
            timeout=90000,
            block_images=settings.block_images,
            block_media=settings.block_media,
            user_agents=settings.user_agents
        )
        await browser.launch()
        
        # Create context and page
        context = await browser.create_context(
            proxy=None,  # No proxy for testing
            user_agent=None,
            profile_name=username
        )
        page = await browser.new_page(context=context)
        
        # Create bot
        bot = faucet_class(settings, page)
        bot.settings_account_override = {
            "username": username,
            "password": password
        }
        
        # Test login
        logger.info(f"[{faucet_name}] Testing login...")
        login_start = datetime.now()
        
        try:
            login_result = await asyncio.wait_for(
                bot.login(),
                timeout=120  # 2 minute timeout
            )
        except asyncio.TimeoutError:
            result["status"] = "login_timeout"
            result["error"] = "Login timed out after 120 seconds"
            result["notes"].append("May be Cloudflare/proxy issue")
            return result
        
        login_duration = (datetime.now() - login_start).total_seconds()
        
        if not login_result:
            result["status"] = "login_failed"
            result["error"] = "Login returned False"
            result["notes"].append(f"Login took {login_duration:.1f}s")
            
            # Check current URL for clues
            try:
                current_url = page.url
                if "cloudflare" in current_url.lower():
                    result["notes"].append("Blocked by Cloudflare")
                elif "captcha" in current_url.lower():
                    result["notes"].append("CAPTCHA required")
            except:
                pass
            
            return result
        
        result["login_success"] = True
        result["status"] = "login_ok"
        result["notes"].append(f"Login took {login_duration:.1f}s")
        
        # Try to get balance
        try:
            if hasattr(bot, 'get_current_balance'):
                balance = await bot.get_current_balance()
            else:
                balance = await bot.get_balance()
            result["balance"] = balance
            result["notes"].append(f"Balance: {balance}")
        except Exception as e:
            result["notes"].append(f"Balance check failed: {str(e)[:50]}")
        
        # Try to get timer
        try:
            timer = await bot.get_timer()
            result["timer"] = timer
            result["notes"].append(f"Timer: {timer} seconds")
        except Exception as e:
            result["notes"].append(f"Timer check failed: {str(e)[:50]}")
        
        # Mark as fully working if we got this far
        if result["login_success"]:
            result["status"] = "working"
        
        return result
        
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        logger.error(f"[{faucet_name}] Test error: {e}", exc_info=True)
        return result
        
    finally:
        if browser:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"[{faucet_name}] Browser cleanup error: {e}")

async def main():
    """Run tests on all faucets and generate report."""
    print("\n" + "="*80)
    print("COMPREHENSIVE FAUCET TEST SUITE")
    print(f"Testing {len(ALL_FAUCETS)} faucets")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")
    
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    
    results = []
    
    for i, faucet_name in enumerate(ALL_FAUCETS, 1):
        print(f"\n[{i}/{len(ALL_FAUCETS)}] Testing {faucet_name.upper()}...")
        print("-" * 60)
        
        result = await test_single_faucet(faucet_name, settings, headless)
        results.append(result)
        
        # Print immediate result
        status_icon = {
            "working": "✅",
            "login_ok": "✅",
            "login_failed": "❌",
            "login_timeout": "⏱️",
            "no_credentials": "🔑",
            "not_registered": "❓",
            "error": "💥"
        }.get(result["status"], "❓")
        
        print(f"{status_icon} Status: {result['status']}")
        if result.get("error"):
            print(f"   Error: {result['error']}")
        for note in result.get("notes", []):
            print(f"   • {note}")
        
        # Small delay between tests
        await asyncio.sleep(2)
    
    # Generate summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    working = [r for r in results if r["status"] in ["working", "login_ok"]]
    failed = [r for r in results if r["status"] in ["login_failed", "error"]]
    timeout = [r for r in results if r["status"] == "login_timeout"]
    no_creds = [r for r in results if r["status"] == "no_credentials"]
    
    print(f"\n✅ Working: {len(working)}/{len(results)}")
    for r in working:
        notes_str = " | ".join(r.get("notes", [])[:2])
        print(f"   • {r['faucet']}: {notes_str}")
    
    print(f"\n❌ Failed: {len(failed)}/{len(results)}")
    for r in failed:
        print(f"   • {r['faucet']}: {r.get('error', 'Unknown')}")
    
    if timeout:
        print(f"\n⏱️  Timed Out: {len(timeout)}/{len(results)}")
        for r in timeout:
            print(f"   • {r['faucet']}")
    
    if no_creds:
        print(f"\n🔑 No Credentials: {len(no_creds)}/{len(results)}")
        for r in no_creds:
            print(f"   • {r['faucet']}")
    
    # Save JSON report
    report_file = Path("faucet_test_report.json")
    with open(report_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_faucets": len(results),
            "working": len(working),
            "failed": len(failed),
            "results": results
        }, f, indent=2)
    
    print(f"\n📄 Detailed report saved to: {report_file}")
    
    # Return success if at least some faucets work
    success_rate = len(working) / len(results) if results else 0
    print(f"\n📊 Success Rate: {success_rate*100:.1f}%")
    
    return success_rate >= 0.5  # Consider success if 50%+ work

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

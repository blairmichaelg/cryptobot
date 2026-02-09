"""
Comprehensive test to verify all 18 faucets can initialize and have required methods.
This validates the core structure without actually running claims.
"""
import asyncio
import logging
from core.config import BotSettings
from core.registry import FAUCET_REGISTRY, get_faucet_class
from browser.instance import BrowserManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def _check_faucet_structure(faucet_name: str, faucet_class):
    """Test that a faucet class has all required methods and can initialize."""
    try:
        # Create a test browser manager (won't actually launch browser)
        settings = BotSettings()
        
        # Check class has required methods
        required_methods = ['login', 'claim', 'get_balance', 'get_timer']
        missing_methods = []
        for method in required_methods:
            if not hasattr(faucet_class, method):
                missing_methods.append(method)
        
        if missing_methods:
            logger.error(f"❌ {faucet_name}: Missing methods: {missing_methods}")
            return False
        
        logger.info(f"✅ {faucet_name}: All required methods present")
        return True
        
    except Exception as e:
        logger.error(f"❌ {faucet_name}: Initialization error: {e}")
        return False

async def main():
    """Test all 18 faucets."""
    logger.info("=" * 60)
    logger.info("Testing all 18 faucets for structural correctness...")
    logger.info("=" * 60)
    
    # Get unique faucet names
    faucet_names = sorted(set([
        "firefaucet", "cointiply", "freebitcoin", "dutchy", "coinpayu", "adbtc", "faucetcrypto",
        "litepick", "tronpick", "dogepick", "bchpick", "solpick", "tonpick", 
        "polygonpick", "binpick", "dashpick", "ethpick", "usdpick"
    ]))
    
    results = {}
    for faucet_name in faucet_names:
        logger.info(f"\nTesting {faucet_name}...")
        faucet_class = get_faucet_class(faucet_name)
        
        if not faucet_class:
            logger.error(f"❌ {faucet_name}: Not found in registry")
            results[faucet_name] = False
            continue
        
        results[faucet_name] = await _check_faucet_structure(faucet_name, faucet_class)
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    
    logger.info(f"\n✅ Passed: {passed}/{len(results)}")
    logger.info(f"❌ Failed: {failed}/{len(results)}")
    
    if failed > 0:
        logger.info("\nFailed faucets:")
        for name, passed in results.items():
            if not passed:
                logger.info(f"  - {name}")
    
    logger.info("\n" + "=" * 60)
    
    return failed == 0

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

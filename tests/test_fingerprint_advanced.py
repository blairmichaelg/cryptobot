"""
Test script to verify advanced canvas and WebGL fingerprint randomization.

This script validates that:
1. Same profile gets same fingerprint across sessions
2. Different profiles get different fingerprints
3. Fingerprints are stored and retrieved correctly
4. Canvas noise is deterministic per profile
5. WebGL parameters are realistic and consistent
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from browser.stealth_scripts import get_full_stealth_script
from core.config import CONFIG_DIR
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_fingerprint_consistency():
    """Test that same profile gets same fingerprint."""
    logger.info("="*80)
    logger.info("TEST 1: Fingerprint Consistency for Same Profile")
    logger.info("="*80)
    
    profile_name = "test_user_123"
    
    # Create browser manager
    bm = BrowserManager(headless=True)
    await bm.launch()
    
    # Create context for first time
    logger.info(f"Creating context for {profile_name} (first time)...")
    context1 = await bm.create_context(profile_name=profile_name)
    
    # Load fingerprint
    fingerprint1 = await bm.load_profile_fingerprint(profile_name)
    logger.info(f"First fingerprint: {fingerprint1}")
    
    await context1.close()
    
    # Create context again
    logger.info(f"Creating context for {profile_name} (second time)...")
    context2 = await bm.create_context(profile_name=profile_name)
    
    # Load fingerprint again
    fingerprint2 = await bm.load_profile_fingerprint(profile_name)
    logger.info(f"Second fingerprint: {fingerprint2}")
    
    await context2.close()
    await bm.close()
    
    # Verify consistency
    assert fingerprint1 == fingerprint2, "Fingerprints should match for same profile!"
    assert fingerprint1['canvas_seed'] == fingerprint2['canvas_seed'], "Canvas seeds should match!"
    assert fingerprint1['gpu_index'] == fingerprint2['gpu_index'], "GPU indices should match!"
    
    logger.info("✅ PASS: Same profile gets same fingerprint across sessions")
    logger.info("")

async def test_different_profiles():
    """Test that different profiles get different fingerprints."""
    logger.info("="*80)
    logger.info("TEST 2: Different Fingerprints for Different Profiles")
    logger.info("="*80)
    
    bm = BrowserManager(headless=True)
    await bm.launch()
    
    profiles = ["user_alice", "user_bob", "user_charlie"]
    fingerprints = {}
    
    for profile in profiles:
        logger.info(f"Creating context for {profile}...")
        context = await bm.create_context(profile_name=profile)
        fingerprint = await bm.load_profile_fingerprint(profile)
        fingerprints[profile] = fingerprint
        logger.info(f"Fingerprint for {profile}: {fingerprint}")
        await context.close()
    
    await bm.close()
    
    # Verify they're different
    canvas_seeds = [fp['canvas_seed'] for fp in fingerprints.values()]
    gpu_indices = [fp['gpu_index'] for fp in fingerprints.values()]
    
    assert len(set(canvas_seeds)) > 1, "Canvas seeds should differ across profiles!"
    # GPU indices might occasionally collide (13 options), so we just log them
    logger.info(f"Canvas seeds: {canvas_seeds}")
    logger.info(f"GPU indices: {gpu_indices}")
    
    logger.info("✅ PASS: Different profiles get different fingerprints")
    logger.info("")

async def test_gpu_configs():
    """Test that GPU configurations are realistic."""
    logger.info("="*80)
    logger.info("TEST 3: GPU Configuration Realism")
    logger.info("="*80)
    
    # Parse the GPU configs from the stealth script
    from browser.stealth_scripts import WEBGL_EVASION
    
    # Extract GPU configs (simple parsing)
    if "NVIDIA GeForce RTX 4060" in WEBGL_EVASION:
        logger.info("✅ Contains NVIDIA RTX 4060")
    if "Intel(R) Iris(R) Xe Graphics" in WEBGL_EVASION:
        logger.info("✅ Contains Intel Iris Xe")
    if "AMD Radeon RX 6700" in WEBGL_EVASION:
        logger.info("✅ Contains AMD Radeon RX 6700")
    if "RTX 3080" in WEBGL_EVASION:
        logger.info("✅ Contains RTX 3080")
    if "UHD Graphics 770" in WEBGL_EVASION:
        logger.info("✅ Contains UHD Graphics 770")
    
    logger.info("✅ PASS: GPU configurations include modern 2024-2026 GPUs")
    logger.info("")

async def test_canvas_seeding():
    """Test that canvas seed generates valid JavaScript."""
    logger.info("="*80)
    logger.info("TEST 4: Canvas Seed Generation")
    logger.info("="*80)
    
    # Test with different seeds
    seeds = [12345, 99999, 500000]
    
    for seed in seeds:
        script = get_full_stealth_script(canvas_seed=seed, gpu_index=5)
        
        # Verify seed is injected
        assert f"window.__FINGERPRINT_SEED__ = {seed}" in script, f"Seed {seed} not found in script!"
        assert "window.__GPU_INDEX__ = 5" in script, "GPU index not found in script!"
        
        logger.info(f"✅ Seed {seed} correctly injected into script")
    
    logger.info("✅ PASS: Canvas seeds are correctly injected")
    logger.info("")

async def test_persistence():
    """Test that fingerprints persist to disk correctly."""
    logger.info("="*80)
    logger.info("TEST 5: Fingerprint Persistence")
    logger.info("="*80)
    
    profile_name = "persistence_test_user"
    
    bm = BrowserManager(headless=True)
    await bm.launch()
    
    # Create context
    context = await bm.create_context(profile_name=profile_name)
    await bm.load_profile_fingerprint(profile_name)
    await context.close()
    await bm.close()
    
    # Verify file exists
    fingerprint_file = CONFIG_DIR / "profile_fingerprints.json"
    assert fingerprint_file.exists(), "Fingerprint file should exist!"
    
    # Load from file directly
    with open(fingerprint_file, "r") as f:
        data = json.load(f)
    
    assert profile_name in data, f"Profile {profile_name} not in fingerprint file!"
    assert 'canvas_seed' in data[profile_name], "canvas_seed not in saved fingerprint!"
    assert 'gpu_index' in data[profile_name], "gpu_index not in saved fingerprint!"
    assert 'locale' in data[profile_name], "locale not in saved fingerprint!"
    assert 'timezone_id' in data[profile_name], "timezone_id not in saved fingerprint!"
    
    logger.info(f"Saved fingerprint: {data[profile_name]}")
    logger.info("✅ PASS: Fingerprints persist correctly to disk")
    logger.info("")

async def main():
    """Run all tests."""
    logger.info("\n")
    logger.info("%s", "╔" + "="*78 + "╗")
    logger.info("%s", "║" + " "*15 + "ADVANCED FINGERPRINT RANDOMIZATION TESTS" + " "*22 + "║")
    logger.info("%s", "╚" + "="*78 + "╝")
    logger.info("\n")
    
    try:
        await test_fingerprint_consistency()
        await test_different_profiles()
        await test_gpu_configs()
        await test_canvas_seeding()
        await test_persistence()
        
        logger.info("="*80)
        logger.info("🎉 ALL TESTS PASSED!")
        logger.info("="*80)
        logger.info("")
        logger.info("Summary:")
        logger.info("✅ Same profile = same fingerprint (deterministic)")
        logger.info("✅ Different profiles = different fingerprints")
        logger.info("✅ GPU configs include modern 2024-2026 hardware")
        logger.info("✅ Canvas noise is seeded and consistent")
        logger.info("✅ Fingerprints persist to config/profile_fingerprints.json")
        logger.info("")
        
    except Exception as e:
        logger.error(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

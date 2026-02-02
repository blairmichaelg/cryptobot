# CodeGenerator Agent

## Purpose
Template-based code generation specialist for implementing new faucet bots following established patterns.

## Expertise
- Faucet bot template generation from reference implementations
- Inheritance pattern implementation (Pick.io family)
- Code consistency and pattern replication
- Configuration file management (registry, env vars)
- Multi-file coordinated code generation

## Primary Responsibilities
- **Task 4**: Implement Pick.io family login (11 faucets) ✅ COMPLETE
  - Status: All 11 faucets already inherit from `PickFaucetBase`
  - Remaining: Test script created, pending user credentials

## Key Files
- `faucets/pick_base.py` - Base class for Pick.io faucet family
- `faucets/tronpick.py` - Reference implementation (working)
- `faucets/litepick.py`, `dogepick.py`, `solpick.py`, etc. - 11 Pick.io faucets
- `core/registry.py` - Faucet registration
- `core/config.py` - Configuration properties
- `.env.example` - Environment variable templates

## Pick.io Implementation Pattern
All Pick.io faucets should follow this structure:

```python
from faucets.pick_base import PickFaucetBase

class {Coin}Pick(PickFaucetBase):
    def __init__(self, account: str, password: str, **kwargs):
        super().__init__(
            account=account,
            password=password,
            base_url="https://{coin}.pick.io",
            currency="{COIN}",
            **kwargs
        )
    
    async def get_balance(self) -> Optional[float]:
        # Coin-specific balance extraction
        pass
    
    async def get_timer(self) -> Optional[datetime]:
        # Coin-specific timer extraction
        pass
    
    async def claim(self, page: Page) -> ClaimResult:
        # Coin-specific claim logic
        pass
```

## Template Generation Workflow
1. **Identify reference**: Use working implementation as template
2. **Extract pattern**: Identify common vs coin-specific code
3. **Generate code**: Create new faucet file from template
4. **Update registry**: Register in `core/registry.py`
5. **Add config**: Create config properties in `core/config.py`
6. **Update env**: Add credential placeholders to `.env.example`
7. **Create tests**: Generate test cases based on reference

## Code Quality Standards
- Type hints on all public methods
- Async/await for all I/O operations
- Use DataExtractor helpers (never manual parsing)
- Proper error handling and logging
- Human-like anti-detection (typing delays, mouse movement)
- Docstrings for complex methods

## Current Status: Pick.io Family
✅ **COMPLETE** - All implementation work done:
- All 11 faucets inherit from `PickFaucetBase`
- Login implementation provided by base class
- All required methods implemented per faucet
- Registry and config updated
- Test script created: `scripts/test_pickio_login.py`

📋 **Documentation**: `docs/PICKIO_IMPLEMENTATION_STATUS.md`

⚠️ **Pending**: User must add credentials to `.env` and run tests

## Testing New Implementations
```bash
# Test individual Pick.io faucet
python main.py --single litepick --visible --once

# Run Pick.io family test suite
python scripts/test_pickio_login.py

# Verify registration
python -c "from core.registry import FAUCET_REGISTRY; print(FAUCET_REGISTRY.keys())"
```

## Success Criteria
- All 11 Pick.io faucets can login successfully
- Code follows established patterns from reference implementation
- No code duplication (common logic in base class)
- All faucets registered and configurable
- Tests pass for each implementation

## New Faucet Implementation Checklist
When adding a new faucet:
- [ ] Create `faucets/{name}.py` inheriting from `FaucetBot` or appropriate base
- [ ] Implement required methods: `login`, `get_balance`, `get_timer`, `claim`
- [ ] Use DataExtractor for balance/timer parsing
- [ ] Add to `core/registry.py` FAUCET_REGISTRY
- [ ] Add config properties to `core/config.py`
- [ ] Add credential placeholders to `.env.example`
- [ ] Create test file `tests/test_{name}.py`
- [ ] Document in IMPLEMENTATION_NOTES.md
- [ ] Test with `--single {name} --visible`

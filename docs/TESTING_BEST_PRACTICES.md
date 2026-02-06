# Testing Best Practices

## Analytics Data Separation

### Overview
The cryptobot maintains separate analytics files for production and testing to ensure accurate profitability metrics:

- **Production**: `earnings_analytics.json` - Contains real faucet claim data
- **Test**: `test_analytics.json` - Contains test data from automated tests and manual testing

### Using Test Mode

#### In Automated Tests (pytest)
Test mode is **automatically enabled** when running pytest tests. The `PYTEST_CURRENT_TEST` environment variable is detected, and all analytics data is written to `test_analytics.json`.

```python
# tests/test_*.py
import pytest
from core.analytics import EarningsTracker

def test_my_feature():
    # Test mode is automatically enabled
    tracker = EarningsTracker()
    tracker.record_claim("test_faucet", True, 100, "BTC")
    # This data goes to test_analytics.json
```

#### Manual Testing with --test-mode Flag
When manually testing the bot, use the `--test-mode` flag to prevent polluting production analytics:

```bash
# Run with test mode enabled
python main.py --test-mode

# Run a single faucet in test mode
python main.py --test-mode --single firefaucet

# Run with visible browser in test mode
python main.py --test-mode --visible
```

#### Programmatic Test Mode Control
You can also enable/disable test mode programmatically:

```python
from core.analytics import set_test_mode, is_test_mode

# Enable test mode
set_test_mode(True)

# Check if test mode is enabled
if is_test_mode():
    print("Running in test mode")

# Disable test mode (return to production)
set_test_mode(False)
```

### Test Data Filtering

The analytics system automatically filters out known test faucet names from production analytics:
- `test_faucet`
- Any faucet starting with `test_`
- `TestFaucet`, `Faucet1`, `Faucet2`, `Faucet3`

In test mode, these filters are bypassed, allowing test data to be recorded.

### Production Analytics

Production analytics should only contain data from real faucet claims. To view production analytics:

```bash
# View summary from production data
python -c 'from core.analytics import EarningsTracker; a = EarningsTracker(); print(a.get_daily_summary())'

# Ensure test mode is disabled (default)
python -c 'from core.analytics import is_test_mode; print(f"Test mode: {is_test_mode()}")'
```

### Best Practices

1. **Always use --test-mode for manual testing** to avoid contaminating production metrics
2. **Never commit test_analytics.json** to version control (already in .gitignore)
3. **Keep production earnings_analytics.json clean** - only real faucet data
4. **Automated tests automatically use test mode** - no manual configuration needed
5. **Historical production data is preserved** during test mode - they are separate files

### Troubleshooting

#### Production data has test entries
If production analytics contains test data, you can clean it manually:

```python
import json
from core.analytics import TEST_FAUCET_NAMES

# Load production analytics
with open('earnings_analytics.json', 'r') as f:
    data = json.load(f)

# Filter out test entries
data['claims'] = [
    c for c in data['claims'] 
    if c['faucet'].lower() not in TEST_FAUCET_NAMES and not c['faucet'].startswith('test_')
]

# Save cleaned data
with open('earnings_analytics.json', 'w') as f:
    json.dump(data, f, indent=2)
```

#### Verify which file is being used
```python
from core.analytics import get_analytics_file, is_test_mode

print(f"Test mode: {is_test_mode()}")
print(f"Analytics file: {get_analytics_file()}")
```

### File Structure
```
cryptobot/
├── earnings_analytics.json     # Production data (committed to git)
├── test_analytics.json          # Test data (ignored by git)
└── docs/
    └── TESTING_BEST_PRACTICES.md
```

### Related Issues
- #71 - Clean test data from earnings_analytics.json

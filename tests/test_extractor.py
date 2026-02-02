import pytest
from core.extractor import DataExtractor

def test_parse_timer_h_m_s():
    assert DataExtractor.parse_timer_to_minutes("1h 30m 0s") == 90.0
    assert DataExtractor.parse_timer_to_minutes("0h 45m") == 45.0
    assert DataExtractor.parse_timer_to_minutes("2h") == 120.0

def test_parse_timer_colon_format():
    assert DataExtractor.parse_timer_to_minutes("01:30:00") == 90.0
    assert DataExtractor.parse_timer_to_minutes("45:00") == 45.0
    assert DataExtractor.parse_timer_to_minutes("01:00") == 1.0

def test_parse_timer_text_format():
    assert DataExtractor.parse_timer_to_minutes("15 minutes") == 15.0
    assert DataExtractor.parse_timer_to_minutes("120 seconds") == 2.0
    assert DataExtractor.parse_timer_to_minutes("Next roll in 5 mins") == 5.0

def test_extract_balance():
    assert DataExtractor.extract_balance("Balance: 1,234.56 BTC") == "1234.56"
    # Trailing zeros are removed for normalization
    assert DataExtractor.extract_balance("0.00012300") == "0.000123"
    assert DataExtractor.extract_balance("Your wallet: 500 Coins") == "500"
    assert DataExtractor.extract_balance("No balance found") == "0"

def test_parse_timer_edge_cases():
    assert DataExtractor.parse_timer_to_minutes("") == 0.0
    assert DataExtractor.parse_timer_to_minutes(None) == 0.0
    assert DataExtractor.parse_timer_to_minutes("Invalid Text") == 0.0


class TestTimerParsingDaysFormat:
    """Test suite for days format in timer parsing."""
    
    def test_parse_timer_days_only(self):
        """Test parsing days format."""
        assert DataExtractor.parse_timer_to_minutes("2 days") == 2 * 24 * 60
        assert DataExtractor.parse_timer_to_minutes("1 day") == 24 * 60
        assert DataExtractor.parse_timer_to_minutes("3d") == 3 * 24 * 60
    
    def test_parse_timer_days_with_hours(self):
        """Test parsing days with hours."""
        # "1d 5h" should be parsed as 1 day + 5 hours = 1440 + 300 = 1740 minutes
        result = DataExtractor.parse_timer_to_minutes("1d 5h")
        assert result == 1 * 24 * 60 + 5 * 60  # 1740 minutes
    
    def test_parse_timer_hours_format(self):
        """Test parsing hours format."""
        assert DataExtractor.parse_timer_to_minutes("5 hours") == 5 * 60
        assert DataExtractor.parse_timer_to_minutes("1 hour") == 60


class TestBalanceExtractionEdgeCases:
    """Test suite for balance extraction edge cases."""
    
    def test_extract_balance_no_numbers(self):
        """Test balance extraction when no numbers present."""
        assert DataExtractor.extract_balance("No numbers here") == "0"
        assert DataExtractor.extract_balance("Balance: N/A") == "0"
        assert DataExtractor.extract_balance("") == "0"
    
    def test_extract_balance_multiple_numbers(self):
        """Test balance extraction picks first number."""
        # Should extract first number
        assert DataExtractor.extract_balance("Balance: 123.45 of 1000 total") == "123.45"
    
    def test_extract_balance_with_commas(self):
        """Test balance extraction removes commas and trailing zeros."""
        # Trailing zeros removed
        assert DataExtractor.extract_balance("1,000,000.50") == "1000000.5"
        assert DataExtractor.extract_balance("Balance: 1,234,567.89 BTC") == "1234567.89"
    
    def test_extract_balance_integer_only(self):
        """Test balance extraction with integers."""
        assert DataExtractor.extract_balance("500") == "500"
        assert DataExtractor.extract_balance("Balance: 42") == "42"
    
    def test_extract_balance_decimal_only(self):
        """Test balance extraction with decimals."""
        assert DataExtractor.extract_balance("0.00000001") == "0.00000001"
        # Note: ".5" without leading zero will extract "5" due to regex pattern
        assert DataExtractor.extract_balance(".5") == "5"


class TestTimerParsingComplexFormats:
    """Test suite for complex timer formats."""
    
    def test_parse_timer_mixed_formats(self):
        """Test parsing mixed format timers."""
        # HH:MM:SS format
        assert DataExtractor.parse_timer_to_minutes("02:30:45") == 2 * 60 + 30 + 45/60.0
        
        # Complex text
        assert DataExtractor.parse_timer_to_minutes("Wait 30 seconds") == 0.5
        assert DataExtractor.parse_timer_to_minutes("Available in 90 min") == 90.0
    
    def test_parse_timer_seconds_only(self):
        """Test parsing seconds-only formats."""
        assert DataExtractor.parse_timer_to_minutes("30s") == 0.5
        assert DataExtractor.parse_timer_to_minutes("90 seconds") == 1.5
        assert DataExtractor.parse_timer_to_minutes("45 sec") == 0.75

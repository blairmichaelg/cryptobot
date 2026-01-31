"""
Tests for ClaimResult tracking and amount/balance extraction fixes.

Validates:
- DataExtractor handles scientific notation
- ClaimResult.validate() catches invalid values
- Analytics.record_claim validates inputs
- _record_analytics properly extracts and normalizes amounts
"""

import pytest
from faucets.base import ClaimResult
from core.extractor import DataExtractor
from core.analytics import EarningsTracker
import tempfile
import os


class TestDataExtractorEnhancements:
    """Test enhanced DataExtractor.extract_balance()"""
    
    def test_extract_scientific_notation(self):
        """Scientific notation like 3.8e-07 should be converted properly"""
        result = DataExtractor.extract_balance("3.8e-07")
        assert result != "0", "Should extract scientific notation"
        # Should be approximately 0.00000038
        assert float(result) == pytest.approx(3.8e-07, rel=1e-9)
    
    def test_extract_large_scientific_notation(self):
        """Large numbers in scientific notation"""
        result = DataExtractor.extract_balance("1.5E+08")
        assert float(result) == pytest.approx(1.5e8, rel=1e-6)
    
    def test_extract_standard_decimal(self):
        """Standard decimal numbers should still work"""
        assert DataExtractor.extract_balance("1234.56") == "1234.56"
        assert DataExtractor.extract_balance("0.00012345") == "0.00012345"
    
    def test_extract_with_commas(self):
        """Comma-separated numbers"""
        assert DataExtractor.extract_balance("1,234.56") == "1234.56"
        assert DataExtractor.extract_balance("1,234,567.89") == "1234567.89"
    
    def test_extract_from_text(self):
        """Extract from embedded text"""
        assert DataExtractor.extract_balance("Balance: 1234.56 BTC") == "1234.56"
        assert DataExtractor.extract_balance("You claimed 0.00000038 BTC") == "0.00000038"
    
    def test_extract_zero(self):
        """Zero values"""
        assert DataExtractor.extract_balance("0") == "0"
        assert DataExtractor.extract_balance("0.0") == "0"
        assert DataExtractor.extract_balance("") == "0"
        assert DataExtractor.extract_balance(None) == "0"
    
    def test_extract_trailing_zeros(self):
        """Trailing zeros should be removed"""
        result = DataExtractor.extract_balance("1.50000")
        assert result == "1.5"


class TestClaimResultValidation:
    """Test ClaimResult.validate() method"""
    
    def test_validate_valid_result(self):
        """Valid ClaimResult should pass validation"""
        result = ClaimResult(
            success=True,
            status="Claimed",
            amount="100",
            balance="5000"
        )
        validated = result.validate("TestFaucet")
        assert validated.amount == "100"
        assert validated.balance == "5000"
    
    def test_validate_none_amount(self):
        """None amount should be converted to '0'"""
        result = ClaimResult(
            success=True,
            status="Claimed",
            amount=None,
            balance="5000"
        )
        validated = result.validate("TestFaucet")
        assert validated.amount == "0"
    
    def test_validate_none_balance(self):
        """None balance should be converted to '0'"""
        result = ClaimResult(
            success=True,
            status="Claimed",
            amount="100",
            balance=None
        )
        validated = result.validate("TestFaucet")
        assert validated.balance == "0"
    
    def test_validate_numeric_amount(self):
        """Numeric amounts should be converted to strings"""
        result = ClaimResult(
            success=True,
            status="Claimed",
            amount=123.45,  # Float instead of string
            balance="5000"
        )
        validated = result.validate("TestFaucet")
        assert isinstance(validated.amount, str)
        assert validated.amount == "123.45"
    
    def test_validate_scientific_notation_amount(self):
        """Scientific notation in amount"""
        result = ClaimResult(
            success=True,
            status="Claimed",
            amount=3.8e-07,  # Scientific notation as float
            balance="5000"
        )
        validated = result.validate("TestFaucet")
        assert isinstance(validated.amount, str)
        # Should preserve the value
        assert float(validated.amount) == pytest.approx(3.8e-07, rel=1e-9)


class TestAnalyticsValidation:
    """Test analytics.record_claim validation"""
    
    def test_record_with_valid_data(self):
        """Recording with valid data should work"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name
        
        try:
            tracker = EarningsTracker(storage_file=temp_file)
            tracker.record_claim(
                faucet="TestFaucet",
                success=True,
                amount=100.0,
                currency="BTC",
                balance_after=5000.0,
                allow_test=True
            )
            
            assert len(tracker.claims) == 1
            claim = tracker.claims[0]
            assert claim['amount'] == 100.0
            assert claim['balance_after'] == 5000.0
            assert claim['currency'] == "BTC"
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_record_with_invalid_amount(self):
        """Invalid amount should be sanitized to 0"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name
        
        try:
            tracker = EarningsTracker(storage_file=temp_file)
            tracker.record_claim(
                faucet="TestFaucet",
                success=True,
                amount=None,  # Invalid
                currency="BTC",
                balance_after=5000.0,
                allow_test=True
            )
            
            assert len(tracker.claims) == 1
            claim = tracker.claims[0]
            assert claim['amount'] == 0.0
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_record_with_invalid_balance(self):
        """Invalid balance should be sanitized to 0"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name
        
        try:
            tracker = EarningsTracker(storage_file=temp_file)
            tracker.record_claim(
                faucet="TestFaucet",
                success=True,
                amount=100.0,
                currency="BTC",
                balance_after="invalid",  # Invalid
                allow_test=True
            )
            
            assert len(tracker.claims) == 1
            claim = tracker.claims[0]
            assert claim['balance_after'] == 0.0
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_record_with_suspicious_amount(self):
        """Suspiciously large amounts should be rejected"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name
        
        try:
            tracker = EarningsTracker(storage_file=temp_file)
            tracker.record_claim(
                faucet="TestFaucet",
                success=True,
                amount=1e15,  # Suspiciously large
                currency="BTC",
                balance_after=5000.0,
                allow_test=True
            )
            
            assert len(tracker.claims) == 1
            claim = tracker.claims[0]
            # Should be sanitized to 0
            assert claim['amount'] == 0.0
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_record_successful_with_zero_amount_logs_warning(self, caplog):
        """Successful claim with 0 amount should log warning"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name
        
        try:
            tracker = EarningsTracker(storage_file=temp_file)
            tracker.record_claim(
                faucet="TestFaucet",
                success=True,
                amount=0.0,  # Zero but successful
                currency="BTC",
                balance_after=5000.0,
                allow_test=True
            )
            
            # Should still record but log warning
            assert len(tracker.claims) == 1
            # Check for warning in logs (requires caplog fixture)
            assert any("0 amount" in rec.message for rec in caplog.records)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)


class TestEndToEndScenarios:
    """Test complete flow from ClaimResult to analytics"""
    
    def test_scientific_notation_claim_flow(self):
        """End-to-end: scientific notation amount should be tracked correctly"""
        # Simulate a faucet returning scientific notation
        result = ClaimResult(
            success=True,
            status="Claimed 3.8e-07 BTC",
            amount="3.8e-07",
            balance="0.00005000"
        )
        
        # Validate
        result.validate("FreeBitcoin")
        
        # Extract amount
        amount_str = DataExtractor.extract_balance(result.amount)
        assert amount_str != "0"
        amount_float = float(amount_str)
        assert amount_float == pytest.approx(3.8e-07, rel=1e-9)
        
        # Extract balance
        balance_str = DataExtractor.extract_balance(result.balance)
        balance_float = float(balance_str)
        assert balance_float == pytest.approx(0.00005, rel=1e-8)
    
    def test_comma_separated_balance_flow(self):
        """End-to-end: comma-separated numbers should work"""
        result = ClaimResult(
            success=True,
            status="Claimed",
            amount="1,234",
            balance="5,678.90"
        )
        
        result.validate("TestFaucet")
        
        amount_str = DataExtractor.extract_balance(result.amount)
        assert amount_str == "1234"
        
        balance_str = DataExtractor.extract_balance(result.balance)
        assert balance_str == "5678.9"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

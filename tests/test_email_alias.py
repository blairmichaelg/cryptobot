import pytest
from faucets.base import FaucetBot


class TestEmailAliasStripping:
    """Test suite for email alias stripping functionality."""
    
    def test_strip_email_alias_with_plus(self):
        """Test stripping email aliases with '+' character."""
        assert FaucetBot.strip_email_alias("user+site@gmail.com") == "user@gmail.com"
        assert FaucetBot.strip_email_alias("john+faucet@example.com") == "john@example.com"
        assert FaucetBot.strip_email_alias("test+coinpayu@domain.org") == "test@domain.org"
    
    def test_strip_email_alias_without_plus(self):
        """Test email addresses without aliases remain unchanged."""
        assert FaucetBot.strip_email_alias("user@gmail.com") == "user@gmail.com"
        assert FaucetBot.strip_email_alias("test@example.com") == "test@example.com"
        assert FaucetBot.strip_email_alias("john.doe@domain.org") == "john.doe@domain.org"
    
    def test_strip_email_alias_multiple_plus(self):
        """Test handling multiple '+' characters (edge case)."""
        # Should strip everything after first '+' up to '@'
        assert FaucetBot.strip_email_alias("user+site+extra@gmail.com") == "user@gmail.com"
        assert FaucetBot.strip_email_alias("test+a+b+c@example.com") == "test@example.com"
    
    def test_strip_email_alias_empty_or_invalid(self):
        """Test handling of empty or invalid email addresses."""
        assert FaucetBot.strip_email_alias("") == ""
        assert FaucetBot.strip_email_alias("invalid") == "invalid"
        assert FaucetBot.strip_email_alias("no-at-sign") == "no-at-sign"
        assert FaucetBot.strip_email_alias(None) == None
    
    def test_strip_email_alias_preserves_domain(self):
        """Test that domain part is preserved correctly."""
        assert FaucetBot.strip_email_alias("user+alias@sub.domain.com") == "user@sub.domain.com"
        assert FaucetBot.strip_email_alias("test+tag@mail.example.co.uk") == "test@mail.example.co.uk"
    
    def test_strip_email_alias_plus_at_end(self):
        """Test email with '+' at the end of local part (edge case)."""
        # "user+@example.com" should become "user@example.com"
        assert FaucetBot.strip_email_alias("user+@example.com") == "user@example.com"
    
    def test_strip_email_alias_preserves_dots_and_special_chars(self):
        """Test that dots and other valid characters are preserved."""
        assert FaucetBot.strip_email_alias("john.doe+tag@gmail.com") == "john.doe@gmail.com"
        assert FaucetBot.strip_email_alias("user_name+site@example.com") == "user_name@example.com"
        assert FaucetBot.strip_email_alias("test-email+alias@domain.org") == "test-email@domain.org"

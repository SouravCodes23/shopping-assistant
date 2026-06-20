"""
tests/unit/test_award_loyalty_points.py

Unit tests for the award_loyalty_points agent tool.
Covers all 8 Security Boundary assertions from the implementation plan.
"""

import sys

import pytest

# ---------------------------------------------------------------------------
# Reload app.agent between tests so module-level mutable state
# (_LOYALTY_ACCOUNTS, _AWARDED_ORDERS, _redemption_attempts) is reset.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_agent_state():
    """Force a fresh module reload before every test to reset shared state."""
    if "app.agent" in sys.modules:
        del sys.modules["app.agent"]
    if "app" in sys.modules:
        del sys.modules["app"]
    yield


def get_tool():
    """Import award_loyalty_points from a freshly loaded module."""
    from app.agent import award_loyalty_points

    return award_loyalty_points


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------


def test_successful_award():
    """Basic success: valid user, valid order, valid amount → points awarded."""
    award = get_tool()
    result = award("user_001", "ORD-1001", 75.0)
    assert "75 loyalty point" in result
    assert "user_001" in result
    assert "ORD-1001" in result
    assert "New balance: 75" in result


def test_points_floored_for_fractional_amount():
    """Points are floored — $49.99 should award 49 points, not 50."""
    award = get_tool()
    result = award("user_001", "ORD-1001", 49.99)
    assert "49 loyalty point" in result


# ---------------------------------------------------------------------------
# Security Boundary #1 — Double-award prevention
# ---------------------------------------------------------------------------


def test_double_award_same_order_rejected():
    """Security Boundary #1: Same order_id cannot be awarded twice."""
    award = get_tool()
    first = award("user_001", "ORD-1001", 50.0)
    second = award("user_001", "ORD-1001", 50.0)
    assert "50 loyalty point" in first
    assert "already been awarded" in second


def test_double_award_different_user_same_order_rejected():
    """Security Boundary #1: Different user cannot award points for an already-awarded order."""
    award = get_tool()
    award("user_001", "ORD-1001", 50.0)
    result = award("user_002", "ORD-1001", 50.0)
    assert "already been awarded" in result


# ---------------------------------------------------------------------------
# Security Boundary #3 — Inflated purchase amount
# ---------------------------------------------------------------------------


def test_purchase_amount_above_cap_rejected():
    """Security Boundary #3: purchase_amount_usd > $10,000 is rejected."""
    award = get_tool()
    result = award("user_001", "ORD-1001", 99999.99)
    assert "Invalid input" in result


# ---------------------------------------------------------------------------
# Security Boundary #4 — Zero / negative amount
# ---------------------------------------------------------------------------


def test_zero_purchase_amount_rejected():
    """Security Boundary #4: purchase_amount_usd = 0 is rejected (must be > 0)."""
    award = get_tool()
    result = award("user_001", "ORD-1001", 0)
    assert "Invalid input" in result


def test_negative_purchase_amount_rejected():
    """Security Boundary #4: Negative purchase_amount_usd is rejected."""
    award = get_tool()
    result = award("user_001", "ORD-1001", -50.0)
    assert "Invalid input" in result


# ---------------------------------------------------------------------------
# Security Boundary #5 — Unknown / fabricated order ID
# ---------------------------------------------------------------------------


def test_unknown_order_id_rejected():
    """Security Boundary #5: Fabricated order IDs not in registry are rejected."""
    award = get_tool()
    result = award("user_001", "ORD-9999", 50.0)
    assert "not found" in result.lower()


def test_invalid_order_id_format_rejected():
    """Security Boundary #5: Malformed order IDs fail Pydantic pattern validation."""
    award = get_tool()
    result = award("user_001", "'; DROP TABLE orders;--", 50.0)
    assert "Invalid input" in result


# ---------------------------------------------------------------------------
# Security Boundary #6 — Unregistered user
# ---------------------------------------------------------------------------


def test_unregistered_user_rejected():
    """Security Boundary #6: Users not in _REGISTERED_USERS cannot earn points."""
    award = get_tool()
    result = award("hacker_99", "ORD-1001", 50.0)
    assert "not a registered customer" in result


# ---------------------------------------------------------------------------
# Security Boundary #8 — Balance cap
# ---------------------------------------------------------------------------


def test_balance_capped_at_max():
    """Security Boundary #8: Cumulative balance cannot exceed MAX_LOYALTY_BALANCE."""
    from app import agent as agent_module

    # Manually set balance near the cap
    agent_module._LOYALTY_ACCOUNTS["user_001"] = 999_990

    award = get_tool()
    # Try to award 100 points — should only get 10 (to reach 1,000,000)
    result = award("user_001", "ORD-1001", 100.0)
    assert "New balance: 1000000" in result
    assert "10 loyalty point" in result

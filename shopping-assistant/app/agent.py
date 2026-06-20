# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math
import os
import threading
import time
from collections import defaultdict

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

# Load credentials from .env (GOOGLE_API_KEY or ADC — never hardcode keys)
load_dotenv()

# ---------------------------------------------------------------------------
# FIX 2: Thread-safe atomic discount code store
# A threading.Lock() ensures only one thread can check-and-flip the
# "redeemed" flag at a time, eliminating the race-condition double-redemption
# identified in the STRIDE threat model (Tampering — HIGH RISK).
# In production, replace with a DB row + unique constraint or Cloud Firestore
# transaction for cross-process atomicity.
# ---------------------------------------------------------------------------
_codes_lock = threading.Lock()

_DISCOUNT_CODES: dict[str, dict] = {
    "WELCOME50": {"discount": "50% off your first order", "redeemed": False},
    "SUMMER20": {"discount": "20% off all summer items", "redeemed": False},
}

# ---------------------------------------------------------------------------
# Simulated registered user registry
# In production this would be a DB lookup.
# ---------------------------------------------------------------------------
_REGISTERED_USERS: set[str] = {
    "user_001",
    "user_002",
    "user_abc",
    "kaggle_student",
}

# ---------------------------------------------------------------------------
# FIX 2 (loyalty): Thread-safe loyalty points store + awarded-order registry.
# _LOYALTY_ACCOUNTS: user_id → cumulative points balance.
# _AWARDED_ORDERS:   set of order IDs that have already been awarded points
#                    (prevents double-award — Security Boundary #1).
# ---------------------------------------------------------------------------
_loyalty_lock = threading.Lock()
_LOYALTY_ACCOUNTS: dict[str, int] = defaultdict(int)
_AWARDED_ORDERS: set[str] = set()

MAX_LOYALTY_BALANCE: int = 1_000_000  # cap to prevent runaway accumulation

# Valid orders eligible for point awards (mirrors check_order_status registry)
_VALID_ORDER_IDS: frozenset[str] = frozenset(
    {"ORD-1001", "ORD-1002", "ORD-1003", "ORD-1004"}
)

# ---------------------------------------------------------------------------
# FIX 1: Per-user rate limiting for discount code redemption attempts.
# Limits each user_id to RATE_LIMIT_MAX_ATTEMPTS within a sliding window,
# preventing brute-force code enumeration (Denial of Service — HIGH RISK).
# For API-level rate limiting across all endpoints, deploy Cloud Armor
# (production) or a reverse proxy such as nginx/Caddy (local staging).
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_redemption_attempts: dict[str, list[float]] = defaultdict(list)

RATE_LIMIT_WINDOW_SECONDS: int = 60  # sliding window duration
RATE_LIMIT_MAX_ATTEMPTS: int = 5  # max attempts per user per window


def _is_rate_limited(user_id: str) -> bool:
    """Return True if user has exceeded the redemption rate limit."""
    now = time.monotonic()
    with _rate_lock:
        # Evict expired timestamps outside the current window
        _redemption_attempts[user_id] = [
            t
            for t in _redemption_attempts[user_id]
            if now - t < RATE_LIMIT_WINDOW_SECONDS
        ]
        if len(_redemption_attempts[user_id]) >= RATE_LIMIT_MAX_ATTEMPTS:
            return True
        _redemption_attempts[user_id].append(now)
        return False


# ---------------------------------------------------------------------------
# FIX 3: Pydantic input schemas — CONTEXT.md Rule 1
# Every tool validates its inputs against a strict schema before any
# business logic runs, preventing type confusion and injection attacks.
# ---------------------------------------------------------------------------


class AwardLoyaltyInput(BaseModel):
    user_id: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Registered customer user ID",
    )
    order_id: str = Field(
        ...,
        min_length=4,
        max_length=20,
        pattern=r"^[A-Za-z0-9-]+$",
        description="Confirmed order ID eligible for point award (e.g. ORD-1001)",
    )
    purchase_amount_usd: float = Field(
        ...,
        gt=0,
        le=10_000,
        description="Purchase total in USD. Points awarded = floor(amount).",
    )


class RedeemDiscountInput(BaseModel):
    user_id: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Registered customer user ID (alphanumeric, hyphens, underscores only)",
    )
    code: str = Field(
        ...,
        min_length=4,
        max_length=20,
        pattern=r"^[A-Za-z0-9]+$",
        description="Discount code to redeem (e.g. WELCOME50, SUMMER20)",
    )


class ListProductsInput(BaseModel):
    category: str = Field(
        default="",
        max_length=50,
        pattern=r"^(electronics|clothing|home|)$",
        description="Product category filter: 'electronics', 'clothing', 'home', or empty for all",
    )


class CheckOrderInput(BaseModel):
    order_id: str = Field(
        ...,
        min_length=4,
        max_length=20,
        pattern=r"^[A-Za-z0-9-]+$",
        description="Order ID to look up (e.g. ORD-1001)",
    )


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def award_loyalty_points(
    user_id: str, order_id: str, purchase_amount_usd: float
) -> str:
    """Award loyalty points to a registered user after a confirmed purchase.

    Points are calculated at 1 point per $1 USD spent (floored). Each order
    can only be awarded points once — duplicate submissions are rejected.

    Args:
        user_id: The registered customer's unique ID.
        order_id: The confirmed order ID to award points for (e.g. ORD-1001).
        purchase_amount_usd: Total purchase value in USD (must be > 0, <= 10000).

    Returns:
        A confirmation message with the points awarded and the new balance,
        or an explanation of why the award was rejected.
    """
    # 1. Pydantic input validation (Security Boundaries #3, #4)
    try:
        validated = AwardLoyaltyInput(
            user_id=user_id,
            order_id=order_id,
            purchase_amount_usd=purchase_amount_usd,
        )
    except ValidationError:
        return (
            "Invalid input: please provide a valid user ID, a known order ID "
            "(e.g. ORD-1001), and a purchase amount between $0.01 and $10,000."
        )

    # 2. Rate limit check (Security Boundary #7)
    if _is_rate_limited(validated.user_id):
        return (
            f"Too many requests. Please wait {RATE_LIMIT_WINDOW_SECONDS} seconds "
            "before trying again."
        )

    # 3. Registered user check (Security Boundary #6)
    if validated.user_id not in _REGISTERED_USERS:
        return (
            "Sorry, that user ID is not a registered customer. "
            "Please create an account before earning loyalty points."
        )

    # 4. Valid order check (Security Boundary #5)
    normalized_order = validated.order_id.upper()
    if normalized_order not in _VALID_ORDER_IDS:
        return (
            f"Order '{validated.order_id}' was not found in our system. "
            "Points can only be awarded for confirmed orders."
        )

    # 5. Atomic double-award prevention + point credit (Security Boundaries #1, #8)
    points_to_award = math.floor(validated.purchase_amount_usd)

    with _loyalty_lock:
        # Security Boundary #1: idempotency — reject duplicate order awards
        if normalized_order in _AWARDED_ORDERS:
            return (
                f"Points for order '{normalized_order}' have already been awarded "
                "and cannot be credited again."
            )

        # Security Boundary #8: cap cumulative balance
        current_balance = _LOYALTY_ACCOUNTS[validated.user_id]
        new_balance = min(current_balance + points_to_award, MAX_LOYALTY_BALANCE)
        actual_awarded = new_balance - current_balance

        _LOYALTY_ACCOUNTS[validated.user_id] = new_balance
        _AWARDED_ORDERS.add(normalized_order)

    return (
        f"🌟 {actual_awarded} loyalty point(s) awarded to '{validated.user_id}' "
        f"for order '{normalized_order}' "
        f"(purchase: ${validated.purchase_amount_usd:.2f}). "
        f"New balance: {new_balance} point(s)."
    )


def redeem_discount_code(user_id: str, code: str) -> str:
    """Redeem a single-use discount code for a registered user.

    Args:
        user_id: The unique ID of the registered customer attempting redemption.
        code: The discount code string to redeem (e.g. WELCOME50, SUMMER20).

    Returns:
        A message confirming successful redemption or explaining why it failed.
    """
    # Fix 3: Validate inputs with Pydantic before any business logic
    try:
        validated = RedeemDiscountInput(user_id=user_id, code=code)
    except ValidationError as exc:
        return f"Invalid input: {exc.error_count()} validation error(s). Please check your user ID and code format."

    # Fix 1: Enforce rate limit before touching shared state
    if _is_rate_limited(validated.user_id):
        return (
            f"Too many redemption attempts. Please wait {RATE_LIMIT_WINDOW_SECONDS} seconds "
            "before trying again."
        )

    # Fix 2: Atomic check-and-redeem under lock
    with _codes_lock:
        # 1. Validate user
        if validated.user_id not in _REGISTERED_USERS:
            return (
                "Sorry, that user ID is not a registered customer. "
                "Please create an account before redeeming discount codes."
            )

        # 2. Validate code exists
        normalized = validated.code.strip().upper()
        if normalized not in _DISCOUNT_CODES:
            return (
                "That is not a valid discount code. "
                "Please check the code and try again."
            )

        # 3. Check if already redeemed (atomic — no gap between check and set)
        entry = _DISCOUNT_CODES[normalized]
        if entry["redeemed"]:
            return (
                f"The code '{normalized}' has already been redeemed and cannot be used again. "
                "Each discount code is valid for a single use only."
            )

        # 4. Mark as redeemed atomically
        entry["redeemed"] = True

    return (
        f"🎉 Success! Code '{normalized}' has been redeemed for user '{validated.user_id}'. "
        f"Benefit applied: {entry['discount']}. Enjoy your savings!"
    )


def list_available_products(category: str = "") -> str:
    """Browse available products in the retail store, optionally filtered by category.

    Args:
        category: Optional product category to filter by (e.g. 'electronics',
                  'clothing', 'home'). Leave empty to list all categories.

    Returns:
        A formatted string listing available products.
    """
    # Fix 3: Validate input
    try:
        validated = ListProductsInput(category=category)
    except ValidationError:
        return "Invalid category. Please choose from: electronics, clothing, home — or leave blank for all."

    catalogue = {
        "electronics": [
            "Wireless Headphones - $79.99",
            "Smart Watch - $199.99",
            "Bluetooth Speaker - $49.99",
        ],
        "clothing": [
            "Summer Dress - $39.99",
            "Denim Jacket - $69.99",
            "Running Shoes - $89.99",
        ],
        "home": [
            "Scented Candle Set - $24.99",
            "Throw Blanket - $34.99",
            "Ceramic Mug Set - $19.99",
        ],
    }

    if validated.category:
        cat = validated.category.lower()
        if cat in catalogue:
            items = "\n  - ".join(catalogue[cat])
            return f"Available {cat} products:\n  - {items}"
        return f"Sorry, we don't have a category called '{cat}'. Available categories: {', '.join(catalogue.keys())}."

    lines = []
    for cat, items in catalogue.items():
        lines.append(
            f"**{cat.title()}**: {', '.join(i.split(' - ')[0] for i in items)}"
        )
    return "Our store categories and products:\n" + "\n".join(lines)


def check_order_status(order_id: str) -> str:
    """Check the shipping/delivery status of an order.

    Args:
        order_id: The order ID to look up (e.g. 'ORD-1001').

    Returns:
        A string with the current order status.
    """
    # Fix 3: Validate input
    try:
        validated = CheckOrderInput(order_id=order_id)
    except ValidationError:
        return "Invalid order ID format. Order IDs look like: ORD-1001, ORD-1002."

    orders = {
        "ORD-1001": "Delivered on June 18 — left at front door.",
        "ORD-1002": "Out for delivery — expected today by 6 PM.",
        "ORD-1003": "Processing — estimated dispatch in 1-2 business days.",
        "ORD-1004": "Shipped — in transit, expected June 22.",
    }
    status = orders.get(validated.order_id.upper())
    if status:
        return f"Order {validated.order_id.upper()}: {status}"
    return "No order found with that ID. Please double-check your order confirmation email."


# ---------------------------------------------------------------------------
# Agent definition
# Credentials are resolved in this order (no hardcoded keys):
#   1. GOOGLE_API_KEY environment variable (set in .env or CI secrets)
#   2. Application Default Credentials (gcloud auth application-default login)
#   3. Google Cloud Secret Manager (recommended for production)
# ---------------------------------------------------------------------------
root_agent = Agent(
    name="shopping_assistant",
    model=Gemini(
        model="gemini-2.0-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are a friendly and knowledgeable AI shopping assistant for our retail store. "
        "Help customers browse products, check order status, and redeem discount codes. "
        "When redeeming a discount code, always ask for the customer's registered user ID first. "
        "Be warm, helpful, and proactively suggest relevant products or deals."
    ),
    tools=[
        award_loyalty_points,
        redeem_discount_code,
        list_available_products,
        check_order_status,
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)

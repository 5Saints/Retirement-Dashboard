"""Anchored-real spending rule (PRD Section 4.9, CR-003)."""

from decimal import Decimal

from fios_engine.models import ExpenseCategory
from fios_engine.money import to_dollars
from fios_engine.spending import build_schedule, first_year_spending, scaled_categories

INFLATION = Decimal("0.03")

CATEGORIES = [
    ExpenseCategory("Core living expenses", essential=True, anchor_amount=Decimal("150000")),
    ExpenseCategory("Travel", essential=False, anchor_amount=Decimal("40000")),
    ExpenseCategory("Vehicles", essential=False, anchor_amount=Decimal("20000")),
    ExpenseCategory("Hobbies", essential=False, anchor_amount=Decimal("20000")),
    ExpenseCategory("Home improvements", essential=False, anchor_amount=Decimal("30000")),
    ExpenseCategory("Miscellaneous", essential=False, anchor_amount=Decimal("40000")),
]


def test_2032_is_the_anchor_not_the_base_year():
    """The engine must never inflate $300,000 forward from 2026 to 2032 -- 2032 is the
    anchor year itself, so first_year_spending(2032) must equal exactly $300,000."""
    assert first_year_spending(2032, INFLATION) == Decimal("300000")


def test_earlier_candidate_deflates_later_candidate_inflates():
    earlier = first_year_spending(2031, INFLATION)
    anchor = first_year_spending(2032, INFLATION)
    later = first_year_spending(2033, INFLATION)

    assert earlier < anchor < later
    assert to_dollars(earlier) == Decimal("291262")
    assert to_dollars(later) == Decimal("309000")


def test_categories_scale_proportionally():
    scaled_2032 = scaled_categories(CATEGORIES, 2032, INFLATION)
    assert sum(scaled_2032.values()) == Decimal("300000")

    scaled_2033 = scaled_categories(CATEGORIES, 2033, INFLATION)
    total_2033 = sum(scaled_2033.values())
    assert to_dollars(total_2033) == Decimal("309000")

    # essential/discretionary 50/50 split is preserved at any retirement date
    essential_names = {c.name for c in CATEGORIES if c.essential}
    essential_total = sum(v for name, v in scaled_2033.items() if name in essential_names)
    assert essential_total / total_2033 == Decimal("150000") / Decimal("300000")


def test_spending_grows_at_inflation_rate_only_after_retirement_begins():
    schedule = build_schedule(2032, INFLATION)

    assert schedule.spending_in_year(2032) == Decimal("300000")
    assert schedule.spending_in_year(2033) == Decimal("300000") * (1 + INFLATION)
    assert schedule.spending_in_year(2034) == Decimal("300000") * (1 + INFLATION) ** 2

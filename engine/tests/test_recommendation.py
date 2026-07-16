"""Tests for the Recommendation and Optimization Engine (Section 26, Phase 6a)."""

from decimal import Decimal

from fios_engine.recommendation import (
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    generate_recommendations,
)
from fios_engine.retirement_readiness import assumption_confidence_percent
from fios_engine.seed import build_baseline_scenario


def _fast_scenario():
    scenario = build_baseline_scenario()
    scenario.monte_carlo_enabled = False
    return scenario


def test_generates_the_expected_candidate_pool_size():
    result = generate_recommendations(_fast_scenario())

    # 3 Roth-conversion amounts + 3 discretionary-cut fractions + proportional
    # withdrawal + real-estate purchase + emergency lake-home sale.
    assert result.candidates_considered == 9


def test_returns_at_most_five_recommendations():
    result = generate_recommendations(_fast_scenario())

    assert 0 < len(result.recommendations) <= 5


def test_ranking_orders_by_earliest_woa_first():
    result = generate_recommendations(_fast_scenario())

    dates = [r.comparison.alternative.evaluated_at for r in result.recommendations]
    assert dates == sorted(dates)


def test_all_hard_constraint_violations_are_excluded_not_just_ranked_low():
    scenario = _fast_scenario()
    scenario.terminal_age = scenario.household.current_age + 1

    result = generate_recommendations(scenario)

    assert result.candidates_excluded_hard_constraint == result.candidates_considered
    assert result.recommendations == []


def test_recommendations_carry_the_full_section_26_field_set():
    result = generate_recommendations(_fast_scenario())

    for recommendation in result.recommendations:
        assert recommendation.action
        assert recommendation.reason
        assert recommendation.trade_offs
        assert recommendation.confidence_level in ("High", "Medium", "Low")
        assert Decimal("0") <= recommendation.confidence_score <= Decimal("100")
        assert recommendation.invalidation_conditions
        assert recommendation.trace
        assert recommendation.rrs_before is not None
        assert recommendation.rrs_after is not None
        assert recommendation.comparison is not None


def test_confidence_score_matches_assumption_confidence_percent():
    scenario = _fast_scenario()
    result = generate_recommendations(scenario)

    for recommendation in result.recommendations:
        # Every candidate clones the same baseline household assumptions (none of the
        # candidate types change a Valued input's status), so confidence should match
        # the baseline's own aggregate confidence.
        assert recommendation.confidence_score == assumption_confidence_percent(scenario.household)


def test_confidence_level_thresholds_are_consistent_with_score():
    result = generate_recommendations(_fast_scenario())

    for recommendation in result.recommendations:
        if recommendation.confidence_level == "High":
            assert recommendation.confidence_score >= CONFIDENCE_HIGH_THRESHOLD
        elif recommendation.confidence_level == "Medium":
            assert CONFIDENCE_MEDIUM_THRESHOLD <= recommendation.confidence_score < CONFIDENCE_HIGH_THRESHOLD
        else:
            assert recommendation.confidence_score < CONFIDENCE_MEDIUM_THRESHOLD


def test_roth_conversion_recommendation_does_not_move_woa():
    """A Roth conversion shifts money between tax-treatment buckets without changing
    total wealth, so it should not move the Work-Optional Age -- it should rank behind
    any candidate that does, per the Section 26 optimization order."""
    result = generate_recommendations(_fast_scenario())

    roth_recommendation = next(
        (r for r in result.recommendations if r.decision_type is not None and "Roth" in r.action), None
    )
    if roth_recommendation is not None:
        assert roth_recommendation.comparison.woa_impact_months == 0


def test_monte_carlo_enabled_recommendations_include_success_probability():
    """Slower golden-path smoke test with Monte Carlo enabled (the default), covering
    the full production path rather than the fast deterministic-only tests above."""
    scenario = build_baseline_scenario()

    result = generate_recommendations(scenario)

    assert len(result.recommendations) > 0
    for recommendation in result.recommendations:
        assert recommendation.comparison.success_probability_before is not None
        assert recommendation.comparison.success_probability_after is not None

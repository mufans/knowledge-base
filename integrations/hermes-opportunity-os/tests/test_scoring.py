import pytest

from opportunity_os.errors import ValidationError
from opportunity_os.scoring import OpportunityScores


def test_weighted_score_uses_approved_weights() -> None:
    scores = OpportunityScores(
        market_demand=10,
        experience_advantage=8,
        growth_potential=6,
        low_cost_validation=4,
        long_term_asset=2,
        cashflow_potential=0,
        interest_signal=10,
    )

    assert scores.weighted_score == pytest.approx(6.3)


@pytest.mark.parametrize("bad_value", [-0.01, 10.01])
def test_score_rejects_values_outside_zero_to_ten(bad_value: float) -> None:
    with pytest.raises(ValidationError, match="0 到 10"):
        OpportunityScores(
            market_demand=bad_value,
            experience_advantage=5,
            growth_potential=5,
            low_cost_validation=5,
            long_term_asset=5,
            cashflow_potential=5,
            interest_signal=5,
        )


def test_score_round_trips_as_explicit_fields() -> None:
    payload = {
        "market_demand": 8,
        "experience_advantage": 7,
        "growth_potential": 9,
        "low_cost_validation": 6,
        "long_term_asset": 8,
        "cashflow_potential": 4,
        "interest_signal": 5,
    }

    assert OpportunityScores.from_dict(payload).to_dict() == payload

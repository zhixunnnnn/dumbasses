"""The claim-matching gate — the part that decides whether imagery may move the score.

An observation verifies a SITE. A claim is prose. Every test here is a case where the two
must NOT be conflated: all of the REJECT cases were produced by an earlier, looser gate
that upgraded a staff-training claim on the strength of a battery site.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.data.satverify import (
    asserts_construction,
    claim_names_site,
    is_portfolio_aggregate,
    observation_supports,
)

COMPANY = "Sembcorp Industries"


def _obs(name: str, asset_type: str, changed: bool | None = True):
    return SimpleNamespace(changed=changed,
                           site=SimpleNamespace(asset_type=asset_type, name=name))


SOLAR = _obs("Tengeh Floating Solar Farm", "solar")
BATTERY = _obs("Sembcorp Banyan Energy Storage System", "battery")
GAS = _obs("Sembcorp Cogen @ Banyan", "gas")

BUILT = "Sembcorp commissioned a 60 MWp floating solar farm at Tengeh Reservoir."


def _supports(topic, text, obs=SOLAR):
    return observation_supports({"topic_id": topic, "text": text}, obs, COMPANY)


# ---- the regressions -------------------------------------------------------------
def test_training_programme_claim_is_not_construction():
    """Real false positive: a SkillsFuture award, 'verified' by a battery site."""
    text = ("Sembcorp Solar Singapore was appointed as the first SkillsFuture Queen Bee "
            "for the Energy and Power sector in 2024.")
    assert _supports("energy_transition", text, BATTERY) is False


def test_commitment_language_is_not_construction():
    text = ("The SkillsFuture Queen Bee programme underscores Sembcorp's commitment to "
            "advance the solar industry in Singapore.")
    assert _supports("energy_transition", text, BATTERY) is False


def test_generic_where_it_operates_is_not_construction():
    text = ("Sembcorp is committed to making the energy transition inclusive for the "
            "communities where it operates.")
    assert _supports("energy_transition", text, BATTERY) is False


def test_company_name_is_stripped_from_site_tokens():
    """'Sembcorp' is in the site name AND in nearly every claim — matching on it matches
    everything, which is what broke the first version."""
    assert claim_names_site("Sembcorp is committed to things", "battery",
                            "Sembcorp Banyan Energy Storage System", COMPANY) is False
    assert claim_names_site("operations at Banyan began", "battery",
                            "Sembcorp Banyan Energy Storage System", COMPANY) is True


# ---- the gate's four conditions --------------------------------------------------
def test_a_real_construction_claim_passes():
    assert _supports("energy_transition", BUILT) is True


def test_portfolio_aggregate_is_refused():
    """One observed farm says nothing about a group-wide total."""
    text = "Sembcorp renewables portfolio reached 3.8 GW by the end of 2024."
    assert is_portfolio_aggregate(text) is True
    assert _supports("energy_transition", text) is False


def test_wrong_topic_is_refused():
    """The same sentence, filed under emissions, is not corroborated by seeing a farm."""
    assert _supports("ghg_emissions", BUILT) is False


def test_fossil_asset_never_corroborates_energy_transition():
    text = "Sembcorp built a new gas-fired cogeneration plant on Jurong Island."
    assert _supports("energy_transition", text, GAS) is False


def test_gas_asset_may_corroborate_energy_management():
    text = "Sembcorp built a new gas-fired cogeneration plant on Jurong Island."
    assert _supports("energy_management", text, GAS) is True


@pytest.mark.parametrize("changed", [False, None])
def test_only_a_positive_observation_counts(changed):
    """Not-observed and inconclusive must never move a claim."""
    obs = _obs("Tengeh Floating Solar Farm", "solar", changed=changed)
    assert _supports("energy_transition", BUILT, obs) is False


# ---- wording ---------------------------------------------------------------------
@pytest.mark.parametrize("verb", ["built", "commissioned", "completed", "installed",
                                  "located at", "began operations"])
def test_construction_verbs_are_recognised(verb):
    assert asserts_construction(f"The company {verb} a solar farm in Johor.") is True


@pytest.mark.parametrize("text", [
    "We are committed to renewable energy.",
    "Solar power is central to our strategy.",
    "We aim to expand our solar capacity by 2030.",
])
def test_aspiration_is_not_construction(text):
    assert asserts_construction(text) is False

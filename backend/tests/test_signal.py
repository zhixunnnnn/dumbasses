"""T5 — is_underpriced_improver truth table (true iff all three legs true)."""
from __future__ import annotations

import itertools

from backend.engine.signal import is_improver


def test_T5_signal_truth_table():
    for proof, opinion, price in itertools.product([True, False], repeat=3):
        expected = proof and opinion and price
        assert is_improver(proof, opinion, price) is expected, (proof, opinion, price)


def test_T5_none_legs_are_not_improver():
    # an undetermined (N.A.) leg must never produce a positive flag
    assert is_improver(None, True, True) is False
    assert is_improver(True, None, True) is False
    assert is_improver(True, True, None) is False

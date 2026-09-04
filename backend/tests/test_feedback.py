from backend.app.feedback import FeedbackStore


def test_sample_feedback_seed_is_complete_and_idempotent(tmp_path):
    path = tmp_path / "feedback.sqlite3"

    first = FeedbackStore(path, seed_examples=True)
    second = FeedbackStore(path, seed_examples=True)

    stats = second.stats()
    assert stats["total"] == 5
    assert stats["byStatus"] == {"open": 2, "resolved": 2, "reviewing": 1}
    assert stats["trainablePairs"] == 2
    assert len(first.list()) == 5
    assert {row.surface for row in second.list()} == {"sample"}


def test_temporary_feedback_store_starts_empty_by_default(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.sqlite3")

    assert store.stats()["total"] == 0

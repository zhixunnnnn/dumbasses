"""ESG Evidence Engine — standalone, UI-independent scoring engine.

Every public function is importable and unit-testable in isolation. No module here
may import from `backend.app` (the FastAPI layer) or from any UI code.
"""

__all__ = ["config", "models"]

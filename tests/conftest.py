import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def no_live_trace_exports_in_unit_tests(monkeypatch):
    # Explicit tracing tests install an in-memory processor and opt back in.
    monkeypatch.setattr(settings, 'openai_tracing_enabled', False)

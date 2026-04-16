from __future__ import annotations

from aionis_workbench.runtime_bridge_host import (
    DEFAULT_RUNTIME_HEALTH_PROBE_TIMEOUT_SECONDS,
    _runtime_health_status,
)


def test_runtime_health_status_uses_default_probe_timeout(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(url: str, *, timeout: float):
        observed["url"] = url
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr("aionis_workbench.runtime_bridge_host.urlopen", fake_urlopen)

    status = _runtime_health_status("http://127.0.0.1:3101")

    assert status == ("available", None)
    assert observed == {
        "url": "http://127.0.0.1:3101/health",
        "timeout": DEFAULT_RUNTIME_HEALTH_PROBE_TIMEOUT_SECONDS,
    }

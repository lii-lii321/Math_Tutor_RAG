"""AI 调用遥测测试。"""
from __future__ import annotations

import pytest

import backend.services.ai.telemetry as telemetry


@pytest.fixture(autouse=True)
def isolated_telemetry(tmp_path, monkeypatch):
    monkeypatch.setattr(telemetry, "_telemetry_path", lambda: tmp_path / "ai_calls.jsonl")
    return tmp_path / "ai_calls.jsonl"


def test_track_success_writes_record(isolated_telemetry):
    with telemetry.track_ai_call("analyze_image") as ctx:
        ctx["ok"] = True
    records = telemetry.read_recent()
    assert len(records) == 1
    assert records[0]["operation"] == "analyze_image"
    assert records[0]["ok"] is True
    assert records[0]["latency_ms"] >= 0


def test_track_failure_records_error(isolated_telemetry):
    with pytest.raises(RuntimeError):
        with telemetry.track_ai_call("analyze_text"):
            raise RuntimeError("boom")
    records = telemetry.read_recent()
    assert records[0]["ok"] is False
    assert "boom" in records[0]["error"]


def test_summarize_aggregates(isolated_telemetry):
    with telemetry.track_ai_call("a"):
        pass
    with telemetry.track_ai_call("a"):
        pass
    with pytest.raises(RuntimeError):
        with telemetry.track_ai_call("b"):
            raise RuntimeError("x")

    summary = telemetry.summarize()
    assert summary["calls"] == 3
    assert summary["success_rate"] == round(2 / 3 * 100)
    assert summary["by_operation"]["a"]["count"] == 2
    assert summary["by_operation"]["b"]["count"] == 1


def test_summarize_empty():
    assert telemetry.summarize()["calls"] == 0

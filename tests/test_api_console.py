"""Integration smoke tests for the locally hosted research console."""
from fastapi.testclient import TestClient
from agents.api import app


def test_console_and_health_are_available():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Federated Learning Flamby Ehr" in response.text
    assert "No dossier was generated" in response.text
    assert client.get("/health").json()["status"] == "HEALTHY"


def test_api_audit_success_and_live_metrics():
    client = TestClient(app)
    before = client.get("/metrics").json()["dossiers_processed_total"]
    response = client.post("/api/audit", json={
        "task_id": "REGRESSION-001",
        "target_identifier": "SYNTHETIC-001",
        "primary_metric": 10.0,
        "secondary_metric": 2.0,
        "status_descriptor": "NOMINAL",
    })
    assert response.status_code == 200, response.text
    assert response.json()["overall_urgency"] == "ROUTINE"
    after = client.get("/metrics").json()["dossiers_processed_total"]
    assert after == before + 1


def test_phi_guard_returns_client_error_not_server_error():
    response = TestClient(app).post("/api/audit", json={
        "task_id": "TEST",
        "target_identifier": "MRN-12345678",
        "primary_metric": 10.0,
    })
    assert response.status_code == 422
    assert "12345678" not in response.text


def test_api_rejects_nonfinite_telemetry():
    response = TestClient(app).post("/api/audit", json={
        "task_id": "TEST",
        "target_identifier": "SYNTHETIC-001",
        "primary_metric": "NaN",
    })
    assert response.status_code == 422


def test_browser_console_javascript_is_valid(tmp_path):
    import re
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which("node"):
        import pytest
        pytest.skip("Node.js is required for the browser syntax check")
    html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    match = re.search(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    assert match is not None
    script = tmp_path / "console.js"
    script.write_text(match.group(1), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

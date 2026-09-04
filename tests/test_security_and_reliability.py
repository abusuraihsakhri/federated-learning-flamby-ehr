"""
Security and reliability tests for federated-learning-flamby-ehr.
Covers: audit key enforcement, batch CLI error handling, simulator CLI parsing.
"""
import os
import sys
import csv
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from agents.base import AuditTrail, PHIGuard, SecurityException
from cli import main as cli_main
from simulator import run_simulation


# --- Audit Key Security Tests ---

def test_audit_trail_requires_secret_key():
    """AuditTrail must raise RuntimeError when no key is provided."""
    original_key = os.environ.pop("AUDIT_SECRET_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="AUDIT_SECRET_KEY"):
            AuditTrail()
    finally:
        if original_key:
            os.environ["AUDIT_SECRET_KEY"] = original_key


def test_audit_trail_rejects_short_key():
    """AuditTrail must reject keys shorter than 16 characters."""
    with pytest.raises(ValueError, match="at least 16 characters"):
        AuditTrail(secret_key="short")


def test_audit_trail_accepts_explicit_key():
    """AuditTrail works when key is passed directly."""
    trail = AuditTrail(secret_key="this-is-a-sufficiently-long-test-key-2026")
    entry = trail.log("test", "unit", "TEST_EVENT", {"data": "value"})
    assert entry["current_hash"]
    assert entry["prev_hash"] == "GENESIS_BLOCK_0000000000000000"


def test_audit_trail_integrity_after_multiple_entries():
    """Multiple log entries should form a valid chain."""
    trail = AuditTrail(secret_key="this-is-a-sufficiently-long-test-key-2026")
    for i in range(5):
        trail.log("test", "unit", "TEST", {"index": i})
    assert trail.verify_integrity() is True
    assert len(trail.get_trail()) == 5


# --- PHI Guard Tests ---

def test_phi_guard_blocks_ssn():
    with pytest.raises(SecurityException):
        PHIGuard.assert_no_phi("SSN: 123-45-6789")


def test_phi_guard_blocks_mrn():
    with pytest.raises(SecurityException):
        PHIGuard.assert_no_phi("Patient MRN-12345678")


def test_phi_guard_blocks_email():
    with pytest.raises(SecurityException):
        PHIGuard.assert_no_phi("Contact patient@example.com for follow-up")


def test_phi_guard_allows_safe_text():
    """Non-PHI text should pass without raising."""
    PHIGuard.assert_no_phi("Analytical specimen KEY-001 result nominal")
    PHIGuard.assert_no_phi("FedAvg round 3 aggregation complete")


def test_phi_redaction():
    """PHIGuard.redact_phi should replace PHI with redacted markers."""
    text = "Patient MRN-12345678 and email test@example.com"
    redacted = PHIGuard.redact_phi(text)
    assert "MRN" not in redacted or "REDACTED" in redacted
    assert "@" not in redacted


# --- Batch CLI Tests ---

def test_batch_cli_missing_file():
    """CLI batch should return error code for missing input file."""
    result = cli_main(["batch", "-i", "nonexistent_file_xyz.csv"])
    assert result == 1


def test_batch_cli_with_sample_csv():
    """CLI batch should process the included sample CSV successfully."""
    sample_csv = Path(__file__).parent.parent / "sample.csv"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp_path = tmp.name

    try:
        result = cli_main(["batch", "-i", str(sample_csv), "-o", tmp_path])
        assert result == 0

        with open(tmp_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3
        assert "overall_urgency" in rows[0]
        assert "audit_hash" in rows[0]
    finally:
        os.unlink(tmp_path)


def test_batch_cli_skips_malformed_rows():
    """CLI batch should skip rows with invalid numeric data."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False,
                                      encoding="utf-8", newline="") as tmp_in:
        writer = csv.DictWriter(tmp_in, fieldnames=[
            "task_id", "target_identifier", "primary_metric",
            "secondary_metric", "is_critical_flag", "status_descriptor"
        ])
        writer.writeheader()
        writer.writerow({
            "task_id": "T1", "target_identifier": "K1",
            "primary_metric": "not_a_number", "secondary_metric": "5.0",
            "is_critical_flag": "False", "status_descriptor": "NOMINAL"
        })
        writer.writerow({
            "task_id": "T2", "target_identifier": "K2",
            "primary_metric": "15.0", "secondary_metric": "5.0",
            "is_critical_flag": "False", "status_descriptor": "NOMINAL"
        })
        in_path = tmp_in.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp_out:
        out_path = tmp_out.name

    try:
        result = cli_main(["batch", "-i", in_path, "-o", out_path])
        assert result == 0

        with open(out_path, mode="r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        # Only the valid row should be processed
        assert len(rows) == 1
        assert rows[0]["task_id"] == "T2"
    finally:
        os.unlink(in_path)
        os.unlink(out_path)


# --- Simulator Tests ---

def test_simulator_with_seed():
    """Simulator with a fixed seed produces deterministic results."""
    result = run_simulation(50, seed=42)
    assert result["total"] == 50
    assert result["audit_verified"] is True
    assert result["nominal"] + result["elevated"] + result["critical"] == 50


def test_simulator_default_iterations():
    """Simulator defaults to 100 iterations."""
    result = run_simulation()
    assert result["total"] == 100

"""Regression tests for cryptographic integrity and federated data algorithms."""
from dataclasses import replace

import numpy as np
import pytest

from agents.base import AuditTrail
from federated_learning_ehr.byzantine_aggregators import (
    FedAvgAggregator,
    TrimmedMeanAggregator,
    KrumAggregator,
    ByzantineResilientAggregator,
)
from federated_learning_ehr.dropout_handler import DropoutHandler, VerifiableSecretSharing
from federated_learning_ehr.partitioner import DataPartitioner, PartitionConfig, PartitionStrategy


def test_audit_hmac_detects_entry_tampering():
    trail = AuditTrail(secret_key="unit-test-signing-key-must-be-long")
    trail.log("worker", "qc", "TEST", {"status": "pass"})
    trail.log("worker", "qc", "TEST", {"status": "ok"})
    assert trail.verify_integrity()
    snapshot = trail.get_trail()
    snapshot[0]["actor"] = "tampered copy"
    assert trail.verify_integrity()
    trail.logs[0]["actor"] = "tampered internal entry"
    assert not trail.verify_integrity()


def test_audit_hmac_rejects_mutated_payload_hash_and_signature():
    trail = AuditTrail(secret_key="unit-test-signing-key-must-be-long")
    trail.log("worker", "qc", "TEST", {"status": "pass"})
    trail.logs[0]["payload_hash"] = "0" * 64
    assert not trail.verify_integrity()
    trail.logs[0]["payload_hash"] = "1" * 64
    trail.logs[0]["current_hash"] = "2" * 64
    assert not trail.verify_integrity()


def test_feldman_commitments_verify_share_and_reject_tampering():
    vss = VerifiableSecretSharing()
    shares, commitments = vss.split_secret(1729, num_shares=5, threshold=3)
    assert len(commitments) == 3
    assert all(s.verify(vss.prime) for s in shares)
    assert vss.reconstruct_secret(shares[:3]) == 1729
    with pytest.raises(ValueError, match="Insufficient"):
        vss.reconstruct_secret(shares[:2])
    modified = replace(shares[0], share_value=(shares[0].share_value + 1) % vss.prime)
    assert not modified.verify(vss.prime)
    with pytest.raises(ValueError, match="verification"):
        vss.reconstruct_secret([modified, *shares[1:3]])


def test_dropout_recovery_uses_original_threshold_and_registered_shares():
    handler = DropoutHandler(threshold_fraction=0.5)
    shares = handler.prepare_shares_for_round(1, {"hospital_a": 1920}, 5)["hospital_a"]
    assert handler.reconstruct_dropped_node(1, "hospital_a", shares[:2]) is None
    assert handler.reconstruct_dropped_node(1, "hospital_a", shares[:3]) == 1920
    forged = replace(shares[0], share_value=(shares[0].share_value + 1) % handler.prime)
    assert handler.reconstruct_dropped_node(1, "hospital_a", [forged, *shares[1:3]]) is None
    handler.register_node("hospital_b")
    handler.active_nodes["hospital_b"] -= 100
    assert len(handler.detect_dropouts(1)) == 1
    assert handler.detect_dropouts(1) == []


def test_fedavg_supports_integer_updates_without_truncation():
    mean = FedAvgAggregator().aggregate(
        [np.array([1, 4]), np.array([4, 10])], [1, 3]
    )
    np.testing.assert_allclose(mean, [3.25, 8.5])


@pytest.mark.parametrize("updates,weights", [
    ([], None),
    ([np.array([1, 2]), np.array([1])], None),
    ([np.array([1]), np.array([2])], [1]),
    ([np.array([1]), np.array([2])], [0, 0]),
    ([np.array([1]), np.array([np.nan])], None),
])
def test_fedavg_rejects_invalid_inputs(updates, weights):
    with pytest.raises(ValueError):
        FedAvgAggregator().aggregate(updates, weights)


def test_trimmed_mean_zero_fraction_retains_all_updates():
    vals = [np.array([1.]), np.array([2.]), np.array([99.])]
    np.testing.assert_allclose(TrimmedMeanAggregator(0).aggregate(vals), [34.])


def test_krum_with_five_sites_selects_honest_update():
    vals = [np.array([0.]), np.array([0.1]), np.array([0.2]),
            np.array([0.3]), np.array([100.])]
    result = KrumAggregator(0.2).aggregate(vals)
    assert result[0] < 1


def test_site_identifiers_match_model_updates():
    with pytest.raises(ValueError, match="Site identifiers"):
        ByzantineResilientAggregator().aggregate(["a"], [np.array([1.]), np.array([2.])])


def test_label_skew_assigns_every_record_exactly_once():
    labels = np.array([0] * 80 + [1] * 20)
    config = PartitionConfig(strategy=PartitionStrategy.LABEL_SKEW, num_sites=5)
    partitions = DataPartitioner(config).partition_dataset(labels, num_classes=2)
    assigned = np.concatenate([p.sample_indices for p in partitions])
    np.testing.assert_array_equal(np.sort(assigned), np.arange(len(labels)))


def test_quantity_skew_assigns_every_record_exactly_once():
    labels = np.array([0] * 80 + [1] * 20)
    config = PartitionConfig(strategy=PartitionStrategy.QUANTITY_SKEW, num_sites=5)
    partitions = DataPartitioner(config).partition_dataset(labels, num_classes=2)
    assigned = np.concatenate([p.sample_indices for p in partitions])
    np.testing.assert_array_equal(np.sort(assigned), np.arange(len(labels)))


@pytest.mark.parametrize("strategy", [PartitionStrategy.TEMPORAL_SKEW, PartitionStrategy.MIXED])
def test_unsupported_partition_modes_fail_explicitly(strategy):
    labels = np.array([0, 1, 0, 1])
    config = PartitionConfig(strategy=strategy, num_sites=2)
    with pytest.raises(NotImplementedError):
        DataPartitioner(config).partition_dataset(labels, 2)


def test_legacy_cli_preserves_false_boolean_csv_value(tmp_path):
    import csv
    from federated_learning_ehr.cli import main as legacy_main

    src = tmp_path / "tasks.csv"
    dst = tmp_path / "output.csv"
    fieldnames = ["task_id", "target_identifier", "primary_metric", "secondary_metric",
                  "status_descriptor", "is_critical_flag"]
    with src.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for value in ("False", "True"):
            writer.writerow({
                "task_id": "TEST-" + value, "target_identifier": "SYNTHETIC-01",
                "primary_metric": "0", "secondary_metric": "0",
                "status_descriptor": "NOMINAL", "is_critical_flag": value,
            })
    assert legacy_main(["batch", "-i", str(src), "-o", str(dst)]) == 0
    with dst.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["critical_count"] == "0"
    assert rows[1]["critical_count"] == "1"


def test_simulation_rejects_empty_workloads():
    from simulator import run_simulation
    with pytest.raises(ValueError, match="positive"):
        run_simulation(0)

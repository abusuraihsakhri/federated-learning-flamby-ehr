"""
Distributed Component High-Throughput Traffic & Stress Testing Simulator for Federated Learning Flamby Ehr.
"""
import argparse
import time
import random
from agents.models import SystemTaskPayload
from agents.supervisor import SystemSupervisor
from agents.base import PHIGuard, SecurityException, AuditLogger


def run_simulation(iterations: int = 100, seed: int = None):
    """Run a distributed component simulation with the specified number of iterations."""
    if not isinstance(iterations, int) or iterations <= 0:
        raise ValueError("Simulation task count must be a positive integer")
    rng = random.Random(seed)
    starting_audit_blocks = len(AuditLogger.get_trail())

    print(f"Starting Distributed Component Simulation on Federated Learning Flamby Ehr ({iterations} tasks)...")
    supervisor = SystemSupervisor(model_provider="mock")
    start_time = time.time()
    nominal_count = 0
    elevated_count = 0
    critical_count = 0
    phi_blocked_count = 0

    for i in range(iterations):
        # 1. Normal / Elevated / Critical payload distribution
        p_val = rng.uniform(5.0, 40.0)
        s_val = rng.uniform(1.0, 20.0)
        is_crit = rng.random() < 0.15
        descriptor = rng.choice(["NOMINAL", "DISCORDANT_ANOMALY", "MUTANT_VARIANT", "OPTIMAL"])

        payload = SystemTaskPayload(
            task_id=f"SIM-{i+1:04d}",
            target_identifier=f"SPECIMEN-{rng.randint(100, 999)}",
            primary_metric=round(p_val, 2),
            secondary_metric=round(s_val, 2),
            status_descriptor=descriptor,
            is_critical_flag=is_crit
        )

        dossier = supervisor.process_task(payload)
        if dossier.overall_urgency.value == "CRITICAL_STAT_PANIC":
            critical_count += 1
        elif dossier.overall_urgency.value == "ELEVATED_RISK":
            elevated_count += 1
        else:
            nominal_count += 1

        # 2. Adversarial PHI test injection (every 25 iterations)
        if (i + 1) % 25 == 0:
            try:
                PHIGuard.assert_no_phi(f"Patient John Doe MRN-{rng.randint(100000, 999999)} test")
            except SecurityException:
                phi_blocked_count += 1

    elapsed = time.time() - start_time
    rate = iterations / max(0.001, elapsed)
    print("\n" + "=" * 70)
    print("  SIMULATION SUMMARY FOR FEDERATED LEARNING FLAMBY EHR")
    print("=" * 70)
    print(f"  Total Tasks Processed:     {iterations}")
    print(f"  Elapsed Time:              {elapsed:.3f} seconds ({rate:.1f} tasks/sec)")
    print(f"  Routine Outcomes:          {nominal_count} ({nominal_count/iterations*100:.1f}%)")
    print(f"  Elevated Risk Outcomes:    {elevated_count} ({elevated_count/iterations*100:.1f}%)")
    print(f"  Critical Interventions:    {critical_count} ({critical_count/iterations*100:.1f}%)")
    probes = iterations // 25
    print(f"  Synthetic PHI Probes:     {probes} / blocked: {phi_blocked_count}")
    print(f"  HMAC Audit Ledger Blocks:  {len(AuditLogger.get_trail()) - starting_audit_blocks}")
    print(f"  HMAC Cryptographic Check:  {AuditLogger.verify_integrity()}")
    print("=" * 70)
    return {
        "total": iterations,
        "elapsed_sec": round(elapsed, 3),
        "rate": round(rate, 1),
        "nominal": nominal_count,
        "elevated": elevated_count,
        "critical": critical_count,
        "phi_blocked": phi_blocked_count,
        "audit_verified": AuditLogger.verify_integrity(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="simulator",
        description="Distributed Component High-Throughput Traffic & Stress Testing Simulator",
    )
    parser.add_argument("--tasks", type=int, default=100, help="Number of tasks to simulate (default: 100)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()
    run_simulation(args.tasks, seed=args.seed)

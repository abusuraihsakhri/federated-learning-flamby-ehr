"""
Enhanced SecAgg with Dropout Resilience using Verifiable Secret Sharing (VSS).
Handles client dropout gracefully during federated training rounds.
Domain: Privacy-Preserving Federated Healthcare & FHE
Standard: Google SecAgg / Federated Learning Standards
"""
import hashlib
import logging
import secrets
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# The share field has prime order q. Commitments live in a separate group of
# order q, so polynomial arithmetic and exponent arithmetic agree.
DEFAULT_SHARE_PRIME = 2**61 - 1
DEFAULT_GROUP_PRIME = 119903836479112085453  # 52*q + 1, prime
DEFAULT_GENERATOR = 4503599627370496  # 2**52 mod DEFAULT_GROUP_PRIME


class NodeStatus(str, Enum):
    ACTIVE = "active"
    DROPPED = "dropped"
    RECOVERED = "recovered"
    RECONSTRUCTED = "reconstructed"


@dataclass
class VSSShare:
    """A Feldman VSS share with commitment."""
    node_id: str
    share_index: int
    share_value: int
    commitment: List[int]  # Feldman commitment coefficients
    timestamp: float = field(default_factory=time.time)
    group_modulus: int = DEFAULT_GROUP_PRIME
    generator: int = DEFAULT_GENERATOR

    def verify(self, prime: int) -> bool:
        """Check g^share == product(commitment_j ^ index^j) in the group."""
        if not (0 < self.share_index < prime and 0 <= self.share_value < prime):
            return False
        if not self.commitment or self.group_modulus < 3:
            return False
        left = pow(self.generator, self.share_value, self.group_modulus)
        right = 1
        exponent = 1
        for commitment in self.commitment:
            if not (0 < commitment < self.group_modulus):
                return False
            right = (right * pow(commitment, exponent, self.group_modulus)) % self.group_modulus
            exponent = (exponent * self.share_index) % prime
        return left == right


@dataclass
class DropoutEvent:
    """Record of a node dropout event."""
    node_id: str
    round_number: int
    detected_at: float
    timeout_seconds: float
    status: NodeStatus = NodeStatus.DROPPED
    reconstructed: bool = False


class VerifiableSecretSharing:
    """Feldman's Verifiable Secret Sharing scheme."""

    def __init__(
        self, prime: int = DEFAULT_SHARE_PRIME,
        group_modulus: Optional[int] = None,
        generator: Optional[int] = None,
    ):
        if prime != DEFAULT_SHARE_PRIME and (group_modulus is None or generator is None):
            raise ValueError("Custom share fields require an explicit commitment group")
        self.prime = prime
        self.group_modulus = group_modulus or DEFAULT_GROUP_PRIME
        self.generator = generator or DEFAULT_GENERATOR
        if (
            prime < 3 or (self.group_modulus - 1) % prime != 0
            or not (1 < self.generator < self.group_modulus)
            or pow(self.generator, prime, self.group_modulus) != 1
        ):
            raise ValueError("Commitment generator must have the share field's prime order")

    def generate_polynomial(self, secret: int, threshold: int) -> List[int]:
        """Generate random polynomial of degree t-1 with secret as constant term."""
        if not isinstance(secret, int) or not (0 <= secret < self.prime):
            raise ValueError("Secret must be an integer in the share field")
        if not (1 <= threshold < self.prime):
            raise ValueError("Threshold must be within the share field")
        coefficients = [secret]
        for _ in range(threshold - 1):
            coefficients.append(secrets.randbelow(self.prime))
        return coefficients

    def evaluate_polynomial(self, coefficients: List[int], x: int) -> int:
        """Evaluate polynomial at point x modulo prime."""
        result = 0
        for i, coeff in enumerate(coefficients):
            result = (result + coeff * pow(x, i, self.prime)) % self.prime
        return result

    def compute_commitments(self, coefficients: List[int], generator: Optional[int] = None) -> List[int]:
        """Compute Feldman commitments in a group of order self.prime."""
        if generator is not None and generator != self.generator:
            raise ValueError("Commitment generator does not match the configured group")
        return [pow(self.generator, coeff, self.group_modulus) for coeff in coefficients]

    def split_secret(
        self, secret: int, num_shares: int, threshold: int
    ) -> Tuple[List[VSSShare], List[int]]:
        """Split secret into n shares with threshold t."""
        if not (1 <= threshold <= num_shares < self.prime):
            raise ValueError("Require 1 <= threshold <= num_shares < prime")
        coefficients = self.generate_polynomial(secret, threshold)
        commitments = self.compute_commitments(coefficients)
        shares = []
        for i in range(1, num_shares + 1):
            share_value = self.evaluate_polynomial(coefficients, i)
            share = VSSShare(
                node_id=f"node_{i}",
                share_index=i,
                share_value=share_value,
                commitment=commitments,
                group_modulus=self.group_modulus,
                generator=self.generator,
            )
            shares.append(share)
        return shares, commitments

    def reconstruct_secret(self, shares: List[VSSShare]) -> int:
        """Reconstruct secret using Lagrange interpolation."""
        if not shares or len(shares) < len(shares[0].commitment):
            raise ValueError("Insufficient shares for reconstruction")
        if len({share.share_index for share in shares}) != len(shares):
            raise ValueError("Duplicate share indices")
        commitments = shares[0].commitment
        if any(
            share.commitment != commitments
            or share.group_modulus != self.group_modulus
            or share.generator != self.generator
            or not share.verify(self.prime)
            for share in shares
        ):
            raise ValueError("Share verification failed")
        secret = 0
        for i, share_i in enumerate(shares):
            xi = share_i.share_index
            yi = share_i.share_value
            numerator = 1
            denominator = 1
            for j, share_j in enumerate(shares):
                if i != j:
                    xj = share_j.share_index
                    numerator = (numerator * (-xj)) % self.prime
                    denominator = (denominator * (xi - xj)) % self.prime
            lagrange_coeff = (numerator * pow(denominator, -1, self.prime)) % self.prime
            secret = (secret + yi * lagrange_coeff) % self.prime
        return secret


class DropoutHandler:
    """Detect and handle node dropouts during federated training rounds."""

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        threshold_fraction: float = 0.5,
        prime: int = 2**61 - 1,
    ):
        self.timeout_seconds = timeout_seconds
        self.threshold_fraction = threshold_fraction
        self.vss = VerifiableSecretSharing(prime)
        self.prime = prime
        self.active_nodes: Dict[str, float] = {}
        self.dropout_events: List[DropoutEvent] = []
        self.round_shares: Dict[int, Dict[str, Dict[int, VSSShare]]] = {}
        self.round_thresholds: Dict[int, int] = {}

    def register_node(self, node_id: str):
        """Register a node as active for the current round."""
        self.active_nodes[node_id] = time.time()
        logger.info(f"Node {node_id} registered as active")

    def heartbeat(self, node_id: str):
        """Update node heartbeat timestamp."""
        if node_id in self.active_nodes:
            self.active_nodes[node_id] = time.time()

    def detect_dropouts(self, round_number: int) -> List[DropoutEvent]:
        """Detect nodes that have timed out."""
        now = time.time()
        dropouts = []
        for node_id, last_seen in list(self.active_nodes.items()):
            if now - last_seen > self.timeout_seconds:
                event = DropoutEvent(
                    node_id=node_id,
                    round_number=round_number,
                    detected_at=now,
                    timeout_seconds=self.timeout_seconds,
                )
                self.dropout_events.append(event)
                dropouts.append(event)
                del self.active_nodes[node_id]  # Report each dropout once
                logger.warning(
                    f"Node {node_id} dropped out in round {round_number} "
                    f"(last seen {now - last_seen:.1f}s ago)"
                )
        return dropouts

    def prepare_shares_for_round(
        self, round_number: int, node_secrets: Dict[str, int], num_nodes: int
    ) -> Dict[str, List[VSSShare]]:
        """Prepare VSS shares for each node's masked update."""
        if num_nodes < 2 or not (0 < self.threshold_fraction < 1):
            raise ValueError("Require at least two nodes and 0 < threshold_fraction < 1")
        threshold = max(2, int(num_nodes * self.threshold_fraction) + 1)
        threshold = min(num_nodes, threshold)
        self.round_thresholds[round_number] = threshold
        self.round_shares[round_number] = {}
        all_shares: Dict[str, List[VSSShare]] = {}
        for node_id, secret in node_secrets.items():
            shares, commitments = self.vss.split_secret(secret, num_nodes, threshold)
            all_shares[node_id] = shares
            self.round_shares[round_number][node_id] = {
                share.share_index: share for share in shares
            }
        return all_shares

    def reconstruct_dropped_node(
        self, round_number: int, dropped_node_id: str, available_shares: List[VSSShare]
    ) -> Optional[int]:
        """Reconstruct a dropped node's contribution using VSS."""
        threshold = self.round_thresholds.get(round_number)
        registered = self.round_shares.get(round_number, {}).get(dropped_node_id)
        if threshold is None or registered is None:
            logger.error("No trusted shares registered for %s in round %s", dropped_node_id, round_number)
            return None
        if len(available_shares) < threshold:
            logger.error(
                f"Insufficient shares for reconstruction: "
                f"{len(available_shares)} < {threshold}"
            )
            return None
        selected = available_shares[:threshold]
        if len({s.share_index for s in selected}) != threshold or any(
            s.share_index not in registered
            or s.commitment != registered[s.share_index].commitment
            or not self.verify_share_integrity(s)
            for s in selected
        ):
            logger.error("Invalid or untrusted shares for %s", dropped_node_id)
            return None
        try:
            secret = self.vss.reconstruct_secret(selected)
        except ValueError:
            return None
        for event in self.dropout_events:
            if event.round_number == round_number and event.node_id == dropped_node_id:
                event.reconstructed = True
                event.status = NodeStatus.RECONSTRUCTED
        logger.info("Reconstructed contribution for dropped node %s", dropped_node_id)
        return secret

    def verify_share_integrity(self, share: VSSShare) -> bool:
        """Verify a share's integrity against its Feldman commitment."""
        return share.verify(self.prime)

    def get_round_summary(self, round_number: int) -> Dict[str, Any]:
        """Get summary of dropout handling for a round."""
        round_dropouts = [
            e for e in self.dropout_events if e.round_number == round_number
        ]
        return {
            "round": round_number,
            "total_active": len(self.active_nodes),
            "total_dropped": len(round_dropouts),
            "dropped_nodes": [e.node_id for e in round_dropouts],
            "reconstructed": sum(1 for e in round_dropouts if e.reconstructed),
        }

"""
Byzantine-Resilient Aggregation Methods for Federated EHR Learning.
Implements Krum, Multi-Krum, and Trimmed Mean to detect and reject poisoned model updates.
Domain: Privacy-Preserving Federated Healthcare & FHE
Standard: Google SecAgg / Federated Learning Standards
"""
import math
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


def _validated_updates(updates: List[np.ndarray]) -> List[np.ndarray]:
    if not updates:
        raise ValueError("At least one model update is required")
    arrays = [np.asarray(update, dtype=float) for update in updates]
    shape = arrays[0].shape
    if not shape or any(a.shape != shape or not np.all(np.isfinite(a)) for a in arrays):
        raise ValueError("Model updates must be finite arrays of identical shape")
    return arrays


class AggregationMethod(str, Enum):
    FEDAVG = "fedavg"
    KRUM = "krum"
    MULTI_KRUM = "multi_krum"
    TRIMMED_MEAN = "trimmed_mean"


@dataclass
class ByzantineConfig:
    """Configuration for Byzantine-resilient aggregation."""
    aggregation_method: AggregationMethod = AggregationMethod.TRIMMED_MEAN
    byzantine_fraction: float = 0.2  # max assumed compromised fraction
    outlier_threshold: float = 3.0   # std-dev threshold for outlier detection
    krum_select_m: int = 3          # number of updates for Multi-Krum
    trim_fraction: float = 0.1      # fraction to trim from each side


@dataclass
class SiteTrustRecord:
    """Trust tracking for a hospital site."""
    site_id: str
    trust_score: float = 1.0
    anomaly_count: int = 0
    total_rounds: int = 0
    history: List[float] = field(default_factory=list)

    def update(self, is_anomalous: bool, decay: float = 0.05, recovery: float = 0.01):
        self.total_rounds += 1
        if is_anomalous:
            self.anomaly_count += 1
            self.trust_score = max(0.0, self.trust_score - decay)
        else:
            self.trust_score = min(1.0, self.trust_score + recovery)
        self.history.append(self.trust_score)


class ByzantineDetector:
    """Detect anomalous model updates from compromised hospital nodes."""

    def __init__(self, config: Optional[ByzantineConfig] = None):
        self.config = config or ByzantineConfig()
        self.site_records: Dict[str, SiteTrustRecord] = {}

    def get_or_create_record(self, site_id: str) -> SiteTrustRecord:
        if site_id not in self.site_records:
            self.site_records[site_id] = SiteTrustRecord(site_id=site_id)
        return self.site_records[site_id]

    def compute_pairwise_cosine_similarity(
        self, updates: List[np.ndarray]
    ) -> np.ndarray:
        """Compute pairwise cosine similarity between model updates."""
        n = len(updates)
        sim_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                norm_i = np.linalg.norm(updates[i])
                norm_j = np.linalg.norm(updates[j])
                if norm_i == 0 or norm_j == 0:
                    sim = 0.0
                else:
                    sim = float(np.dot(updates[i], updates[j]) / (norm_i * norm_j))
                sim_matrix[i, j] = sim
                sim_matrix[j, i] = sim
        return sim_matrix

    def detect_anomalies(
        self, site_ids: List[str], updates: List[np.ndarray]
    ) -> Dict[str, bool]:
        """Flag updates with cosine similarity < 0.5 to the median update."""
        if len(updates) < 3:
            return {sid: False for sid in site_ids}

        sim_matrix = self.compute_pairwise_cosine_similarity(updates)
        median_sim = np.median(sim_matrix, axis=1)
        threshold = 0.5
        anomalies = {}
        for i, site_id in enumerate(site_ids):
            is_anomalous = median_sim[i] < threshold
            record = self.get_or_create_record(site_id)
            record.update(is_anomalous)
            anomalies[site_id] = is_anomalous
            if is_anomalous:
                logger.warning(
                    f"Site {site_id} flagged as anomalous "
                    f"(median_sim={median_sim[i]:.4f}, trust={record.trust_score:.4f})"
                )
        return anomalies


class KrumAggregator:
    """Krum: select update with minimum sum of distances to k nearest updates."""

    def __init__(self, byzantine_fraction: float = 0.2):
        self.byzantine_fraction = byzantine_fraction

    def aggregate(self, updates: List[np.ndarray]) -> np.ndarray:
        updates = _validated_updates(updates)
        n = len(updates)
        if n < 3 or not (0 <= self.byzantine_fraction < 0.5):
            raise ValueError("Krum requires at least three updates and 0 <= Byzantine fraction < 0.5")
        f = int(math.floor(n * self.byzantine_fraction))
        if n < 2 * f + 3:
            raise ValueError("Not enough updates to tolerate the configured Byzantine clients")
        k = n - f - 2
        if k < 1:
            k = 1

        distances = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = float(np.linalg.norm(updates[i] - updates[j]))
                distances[i, j] = d
                distances[j, i] = d

        scores = np.zeros(n)
        for i in range(n):
            sorted_dists = np.sort(distances[i])
            scores[i] = np.sum(sorted_dists[1 : k + 1])  # exclude self-distance

        winner = int(np.argmin(scores))
        logger.info(f"Krum selected update {winner} with score {scores[winner]:.6f}")
        return updates[winner].copy()


class MultiKrumAggregator:
    """Multi-Krum: select m best updates and average them."""

    def __init__(self, byzantine_fraction: float = 0.2, m: int = 3):
        self.byzantine_fraction = byzantine_fraction
        self.m = m

    def aggregate(self, updates: List[np.ndarray]) -> np.ndarray:
        updates = _validated_updates(updates)
        n = len(updates)
        if n < 3 or not (0 <= self.byzantine_fraction < 0.5):
            raise ValueError("Multi-Krum requires at least three updates and 0 <= Byzantine fraction < 0.5")
        f = int(math.floor(n * self.byzantine_fraction))
        if n < 2 * f + 3 or not (1 <= self.m <= n - f - 2):
            raise ValueError("Invalid Byzantine budget or Multi-Krum selection count")
        k = n - f - 2
        if k < 1:
            k = 1
        m = min(self.m, n)

        distances = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = float(np.linalg.norm(updates[i] - updates[j]))
                distances[i, j] = d
                distances[j, i] = d

        scores = np.zeros(n)
        for i in range(n):
            sorted_dists = np.sort(distances[i])
            scores[i] = np.sum(sorted_dists[1 : k + 1])

        selected_indices = np.argsort(scores)[:m]
        result = np.mean([updates[i] for i in selected_indices], axis=0)
        logger.info(
            f"Multi-Krum selected {m} updates from indices {selected_indices.tolist()}"
        )
        return result


class TrimmedMeanAggregator:
    """Trimmed Mean: sort per-coordinate, trim top/bottom f%, compute mean."""

    def __init__(self, trim_fraction: float = 0.1):
        self.trim_fraction = trim_fraction

    def aggregate(self, updates: List[np.ndarray]) -> np.ndarray:
        updates = _validated_updates(updates)
        n = len(updates)
        if not (0 <= self.trim_fraction < 0.5):
            raise ValueError("Trim fraction must be between 0 (inclusive) and 0.5")
        trim_count = int(n * self.trim_fraction)
        stacked = np.stack(updates, axis=0)  # (n, d)
        sorted_updates = np.sort(stacked, axis=0)
        trimmed = sorted_updates[trim_count : n - trim_count]
        if len(trimmed) == 0:
            raise ValueError("Trim fraction removes every update")
        result = np.mean(trimmed, axis=0)
        logger.info(
            f"Trimmed Mean aggregated {n} updates, trimmed {trim_count} from each side"
        )
        return result


class FedAvgAggregator:
    """Standard FedAvg: simple weighted average."""

    def __init__(self):
        pass

    def aggregate(
        self, updates: List[np.ndarray], weights: Optional[List[float]] = None
    ) -> np.ndarray:
        updates = _validated_updates(updates)
        if weights is None:
            weights = [1.0] * len(updates)
        if (len(weights) != len(updates) or
                any(not math.isfinite(w) or w < 0 for w in weights) or
                sum(weights) <= 0):
            raise ValueError("Weights must be finite, nonnegative, and match the updates")
        return np.average(np.stack(updates), axis=0, weights=weights)


class ByzantineResilientAggregator:
    """Unified aggregator that selects method based on configuration."""

    def __init__(self, config: Optional[ByzantineConfig] = None):
        self.config = config or ByzantineConfig()
        self.detector = ByzantineDetector(self.config)
        self._aggregators = {
            AggregationMethod.FEDAVG: FedAvgAggregator(),
            AggregationMethod.KRUM: KrumAggregator(self.config.byzantine_fraction),
            AggregationMethod.MULTI_KRUM: MultiKrumAggregator(
                self.config.byzantine_fraction, self.config.krum_select_m
            ),
            AggregationMethod.TRIMMED_MEAN: TrimmedMeanAggregator(
                self.config.trim_fraction
            ),
        }

    def aggregate(
        self,
        site_ids: List[str],
        updates: List[np.ndarray],
        weights: Optional[List[float]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Aggregate updates with Byzantine resilience. Returns (result, metadata)."""
        updates = _validated_updates(updates)
        if len(site_ids) != len(updates) or len(site_ids) != len(set(site_ids)):
            raise ValueError("Site identifiers must be unique and match the updates")
        anomalies = self.detector.detect_anomalies(site_ids, updates)
        flagged = [sid for sid, is_anom in anomalies.items() if is_anom]

        if flagged and self.config.aggregation_method == AggregationMethod.FEDAVG:
            logger.warning(
                f"Anomalies detected in {len(flagged)} sites but using FedAvg; "
                f"consider switching to Krum or Trimmed Mean."
            )

        aggregator = self._aggregators[self.config.aggregation_method]
        if self.config.aggregation_method == AggregationMethod.FEDAVG:
            result = aggregator.aggregate(updates, weights)
        else:
            result = aggregator.aggregate(updates)

        metadata = {
            "method": self.config.aggregation_method.value,
            "num_sites": len(site_ids),
            "flagged_sites": flagged,
            "site_trust_scores": {
                sid: self.detector.get_or_create_record(sid).trust_score
                for sid in site_ids
            },
        }
        return result, metadata

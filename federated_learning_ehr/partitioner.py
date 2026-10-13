"""
Cross-Silo Heterogeneous Data Partitioning for Federated EHR Learning.
Supports realistic hospital scenarios with non-IID data distributions.
Domain: Privacy-Preserving Federated Healthcare & FHE
Standard: Google SecAgg / Federated Learning Standards
"""
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class PartitionStrategy(str, Enum):
    DIRICHLET = "dirichlet"
    QUANTITY_SKEW = "quantity_skew"
    LABEL_SKEW = "label_skew"
    TEMPORAL_SKEW = "temporal_skew"
    MIXED = "mixed"


@dataclass
class SitePartition:
    """Data partition assigned to a hospital site."""
    site_id: str
    sample_indices: np.ndarray
    num_samples: int
    label_distribution: Dict[int, float]
    quality_score: float = 1.0
    feature_shift_params: Optional[Dict[str, Any]] = None


@dataclass
class PartitionConfig:
    """Configuration for data partitioning."""
    strategy: PartitionStrategy = PartitionStrategy.DIRICHLET
    num_sites: int = 5
    alpha: float = 0.5  # Dirichlet concentration parameter
    min_samples_per_site: int = 50
    max_samples_per_site: int = 10000
    quality_weight_enabled: bool = True


class DirichletPartitioner:
    """Partition data using Dirichlet distribution for non-IID splits."""

    def __init__(self, alpha: float = 0.5, num_sites: int = 5):
        self.alpha = alpha
        self.num_sites = num_sites

    def partition(
        self, labels: np.ndarray, num_classes: int
    ) -> List[np.ndarray]:
        """Partition sample indices using Dirichlet distribution."""
        if self.num_sites < 1 or self.alpha <= 0 or num_classes < 1:
            raise ValueError("Positive site count, Dirichlet alpha, and class count required")
        if np.any((labels < 0) | (labels >= num_classes)):
            raise ValueError("Labels must be integer class identifiers within range")
        indices_by_class = {
            c: np.where(labels == c)[0] for c in range(num_classes)
        }
        site_indices: List[List[int]] = [[] for _ in range(self.num_sites)]

        for c in range(num_classes):
            class_indices = indices_by_class[c]
            np.random.shuffle(class_indices)
            proportions = np.random.dirichlet(
                np.repeat(self.alpha, self.num_sites)
            )
            proportions = proportions / proportions.sum()
            splits = (proportions * len(class_indices)).astype(int)
            # Distribute remainder
            remainder = len(class_indices) - splits.sum()
            for i in range(remainder):
                splits[i % self.num_sites] += 1

            offset = 0
            for site_idx in range(self.num_sites):
                count = splits[site_idx]
                site_indices[site_idx].extend(
                    class_indices[offset : offset + count].tolist()
                )
                offset += count

        return [np.array(indices) for indices in site_indices]


class QuantitySkewPartitioner:
    """Partition with different sample quantities per site."""

    def __init__(
        self,
        num_sites: int = 5,
        min_ratio: float = 0.01,
        max_ratio: float = 0.5,
    ):
        self.num_sites = num_sites
        self.min_ratio = min_ratio
        self.max_ratio = max_ratio

    def partition(self, total_samples: int) -> List[int]:
        """Return number of samples per site with quantity skew."""
        raw = np.random.uniform(self.min_ratio, self.max_ratio, self.num_sites)
        proportions = raw / raw.sum()
        counts = (proportions * total_samples).astype(int)
        remainder = total_samples - counts.sum()
        for i in range(int(remainder)):
            counts[i % self.num_sites] += 1
        return counts.tolist()


class LabelSkewPartitioner:
    """Partition with different label distributions per site (hospital specialization)."""

    def __init__(self, num_sites: int = 5, specialization_strength: float = 0.8):
        self.num_sites = num_sites
        self.specialization_strength = specialization_strength

    def generate_site_distributions(
        self, num_classes: int
    ) -> List[Dict[int, float]]:
        """Generate label distributions where each site specializes in certain conditions."""
        distributions = []
        for site_idx in range(self.num_sites):
            dist = {}
            primary_class = site_idx % num_classes
            for c in range(num_classes):
                if c == primary_class:
                    dist[c] = self.specialization_strength
                else:
                    dist[c] = (1.0 - self.specialization_strength) / max(
                        1, num_classes - 1
                    )
            distributions.append(dist)
        return distributions


class QualityWeightedAggregator:
    """Weight site contributions by data quality metrics."""

    def __init__(self):
        self.site_weights: Dict[str, float] = {}
        self.site_metrics: Dict[str, Dict[str, float]] = {}

    def update_weights(
        self,
        site_id: str,
        sample_size: int,
        completeness: float,
        accuracy: float,
        convergence_score: float,
    ):
        """Update site weight based on quality metrics."""
        quality = (
            0.3 * min(1.0, sample_size / 1000)
            + 0.3 * completeness
            + 0.2 * accuracy
            + 0.2 * convergence_score
        )
        self.site_weights[site_id] = quality
        self.site_metrics[site_id] = {
            "sample_size": sample_size,
            "completeness": completeness,
            "accuracy": accuracy,
            "convergence_score": convergence_score,
            "quality": quality,
        }

    def get_weights(self, site_ids: List[str]) -> List[float]:
        """Get normalized weights for aggregation."""
        raw = [self.site_weights.get(sid, 1.0) for sid in site_ids]
        total = sum(raw)
        if total == 0:
            return [1.0 / len(site_ids)] * len(site_ids)
        return [w / total for w in raw]


class DataPartitioner:
    """Unified data partitioner supporting multiple strategies."""

    def __init__(self, config: Optional[PartitionConfig] = None):
        self.config = config or PartitionConfig()
        self.dirichlet = DirichletPartitioner(
            self.config.alpha, self.config.num_sites
        )
        self.quantity_skew = QuantitySkewPartitioner(self.config.num_sites)
        self.label_skew = LabelSkewPartitioner(self.config.num_sites)
        self.quality_aggregator = QualityWeightedAggregator()

    def partition_dataset(
        self,
        labels: np.ndarray,
        num_classes: int,
        site_ids: Optional[List[str]] = None,
    ) -> List[SitePartition]:
        """Partition dataset across hospital sites."""
        labels = np.asarray(labels)
        if labels.ndim != 1 or num_classes < 1:
            raise ValueError("Expected one-dimensional labels and a positive class count")
        if site_ids is None:
            site_ids = [f"hospital_{i}" for i in range(self.config.num_sites)]
        if len(site_ids) != self.config.num_sites or len(set(site_ids)) != len(site_ids):
            raise ValueError("Site IDs must uniquely match the configured site count")
        if self.config.num_sites < 1:
            raise ValueError("Number of sites must be positive")

        if self.config.strategy == PartitionStrategy.DIRICHLET:
            site_index_arrays = self.dirichlet.partition(labels, num_classes)
        elif self.config.strategy == PartitionStrategy.LABEL_SKEW:
            distributions = self.label_skew.generate_site_distributions(num_classes)
            site_index_arrays = self._partition_by_distribution(
                labels, num_classes, distributions
            )
        else:
            site_index_arrays = self.dirichlet.partition(labels, num_classes)

        partitions = []
        for i, (site_id, indices) in enumerate(zip(site_ids, site_index_arrays)):
            if len(indices) == 0:
                continue
            site_labels = labels[indices]
            label_dist = {}
            for c in range(num_classes):
                label_dist[c] = float(np.sum(site_labels == c)) / len(site_labels)

            partition = SitePartition(
                site_id=site_id,
                sample_indices=indices,
                num_samples=len(indices),
                label_distribution=label_dist,
                quality_score=1.0,
            )
            partitions.append(partition)
            logger.info(
                f"Site {site_id}: {len(indices)} samples, "
                f"label_dist={ {k: f'{v:.3f}' for k, v in label_dist.items()} }"
            )
        return partitions

    def _partition_by_distribution(
        self,
        labels: np.ndarray,
        num_classes: int,
        distributions: List[Dict[int, float]],
    ) -> List[np.ndarray]:
        """Partition samples according to specified label distributions."""
        if not distributions or num_classes < 1:
            raise ValueError("Expected site distributions and a positive class count")
        if np.any((labels < 0) | (labels >= num_classes)):
            raise ValueError("Labels must be integer class identifiers within range")
        site_indices: List[List[int]] = [[] for _ in distributions]
        for c in range(num_classes):
            indices = np.where(labels == c)[0]
            np.random.shuffle(indices)
            weights = np.array([max(0.0, dist.get(c, 0.0)) for dist in distributions])
            if not np.all(np.isfinite(weights)):
                raise ValueError("Site distribution weights must be finite")
            if weights.sum() == 0:
                weights = np.ones(len(distributions))
            raw_counts = len(indices) * weights / weights.sum()
            counts = np.floor(raw_counts).astype(int)
            # Largest-remainder allocation retains every example exactly once.
            for site_idx in np.argsort(-(raw_counts - counts), kind="stable")[:len(indices) - counts.sum()]:
                counts[site_idx] += 1
            offset = 0
            for site_idx, count in enumerate(counts):
                site_indices[site_idx].extend(indices[offset:offset + count].tolist())
                offset += count
        return [np.asarray(indices, dtype=int) for indices in site_indices]

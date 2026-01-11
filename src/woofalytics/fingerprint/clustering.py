"""Automatic clustering of untagged bark fingerprints.

This module uses HDBSCAN to identify coherent clusters among untagged
barks that may represent the same dog, enabling automatic profile suggestions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from woofalytics.fingerprint.models import BarkFingerprint
    from woofalytics.fingerprint.storage import FingerprintStore

logger = structlog.get_logger(__name__)

# Try to import HDBSCAN
try:
    import hdbscan

    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False
    logger.warning("hdbscan not available, clustering feature disabled")


@dataclass
class ClusterSuggestion:
    """A suggested dog profile from clustered barks."""

    cluster_id: str
    """Unique identifier for this cluster."""

    fingerprint_ids: list[str] = field(default_factory=list)
    """IDs of fingerprints in this cluster."""

    size: int = 0
    """Number of barks in this cluster."""

    centroid_embedding: np.ndarray | None = None
    """Average embedding for the cluster (512-dim, normalized)."""

    avg_pitch_hz: float | None = None
    """Average pitch of barks in Hz."""

    avg_duration_ms: float | None = None
    """Average duration of barks in ms."""

    first_seen: datetime | None = None
    """Earliest bark in cluster."""

    last_seen: datetime | None = None
    """Latest bark in cluster."""

    coherence_score: float = 0.0
    """How coherent/tight the cluster is (0-1)."""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "cluster_id": self.cluster_id,
            "fingerprint_ids": self.fingerprint_ids,
            "size": self.size,
            "avg_pitch_hz": round(self.avg_pitch_hz, 1) if self.avg_pitch_hz else None,
            "avg_duration_ms": round(self.avg_duration_ms, 1) if self.avg_duration_ms else None,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "coherence_score": round(self.coherence_score, 3),
        }


class BarkClusterer:
    """Cluster untagged bark fingerprints to suggest new dog profiles.

    Uses HDBSCAN (Hierarchical Density-Based Spatial Clustering) which:
    - Doesn't require specifying number of clusters
    - Handles noise (outliers) gracefully
    - Works well with varying cluster sizes
    """

    # HDBSCAN parameters tuned for bark embeddings
    MIN_CLUSTER_SIZE = 3  # Minimum barks to form a cluster
    MIN_SAMPLES = 2  # Core sample requirement
    CLUSTER_SELECTION_EPSILON = 0.1  # Stability threshold

    def __init__(
        self,
        store: FingerprintStore,
        min_cluster_size: int | None = None,
        min_samples: int | None = None,
    ) -> None:
        """Initialize the clusterer.

        Args:
            store: Fingerprint storage for retrieving untagged barks.
            min_cluster_size: Minimum fingerprints to form a cluster.
            min_samples: Minimum samples for a point to be a core point.

        Raises:
            ImportError: If hdbscan package is not installed.
        """
        if not HAS_HDBSCAN:
            raise ImportError(
                "hdbscan package required for clustering. "
                "Install with: pip install hdbscan"
            )

        self._store = store
        self._min_cluster_size = min_cluster_size or self.MIN_CLUSTER_SIZE
        self._min_samples = min_samples or self.MIN_SAMPLES
        self._log = logger.bind(component="bark_clusterer")

    def cluster_untagged(
        self,
        max_fingerprints: int = 1000,
    ) -> list[ClusterSuggestion]:
        """Cluster untagged fingerprints and return suggestions.

        Args:
            max_fingerprints: Maximum untagged barks to process.

        Returns:
            List of ClusterSuggestion for each identified cluster,
            sorted by size (largest first).
        """
        # Get untagged fingerprints with embeddings
        fingerprints = self._store.get_untagged_fingerprints(limit=max_fingerprints)

        # Filter to those with valid embeddings
        valid_fps = [fp for fp in fingerprints if fp.embedding is not None]

        if len(valid_fps) < self._min_cluster_size:
            self._log.info(
                "insufficient_fingerprints_for_clustering",
                count=len(valid_fps),
                required=self._min_cluster_size,
            )
            return []

        # Build embedding matrix
        embeddings = np.array([fp.embedding for fp in valid_fps])

        # Run HDBSCAN clustering
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self._min_cluster_size,
            min_samples=self._min_samples,
            cluster_selection_epsilon=self.CLUSTER_SELECTION_EPSILON,
            metric="euclidean",  # Embeddings are L2 normalized, so euclidean ~ cosine
            cluster_selection_method="eom",  # Excess of mass for stability
        )

        cluster_labels = clusterer.fit_predict(embeddings)

        # Build suggestions from clusters
        suggestions = []
        unique_labels = set(cluster_labels)
        unique_labels.discard(-1)  # Remove noise label

        for label in unique_labels:
            mask = cluster_labels == label
            cluster_fps = [fp for fp, m in zip(valid_fps, mask) if m]
            cluster_embeddings = embeddings[mask]

            # Get probabilities if available
            probabilities = None
            if hasattr(clusterer, "probabilities_"):
                probabilities = clusterer.probabilities_[mask]

            suggestion = self._build_suggestion(
                cluster_id=f"cluster_{label}",
                fingerprints=cluster_fps,
                embeddings=cluster_embeddings,
                probabilities=probabilities,
            )
            suggestions.append(suggestion)

        # Sort by size (largest first)
        suggestions.sort(key=lambda s: s.size, reverse=True)

        self._log.info(
            "clustering_complete",
            total_fingerprints=len(valid_fps),
            clusters_found=len(suggestions),
            noise_count=int((cluster_labels == -1).sum()),
        )

        return suggestions

    def _build_suggestion(
        self,
        cluster_id: str,
        fingerprints: list[BarkFingerprint],
        embeddings: np.ndarray,
        probabilities: np.ndarray | None,
    ) -> ClusterSuggestion:
        """Build a ClusterSuggestion from cluster data."""
        # Compute centroid
        centroid = embeddings.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm  # Normalize

        # Compute coherence as average probability or cosine similarity
        if probabilities is not None and len(probabilities) > 0:
            coherence = float(np.mean(probabilities))
        else:
            # Fallback: average cosine similarity to centroid
            similarities = np.dot(embeddings, centroid)
            coherence = float(np.mean(similarities))

        # Aggregate acoustic features
        pitches = [fp.pitch_hz for fp in fingerprints if fp.pitch_hz]
        durations = [fp.duration_ms for fp in fingerprints if fp.duration_ms]
        timestamps = [fp.timestamp for fp in fingerprints]

        return ClusterSuggestion(
            cluster_id=cluster_id,
            fingerprint_ids=[fp.id for fp in fingerprints],
            size=len(fingerprints),
            centroid_embedding=centroid,
            avg_pitch_hz=float(np.mean(pitches)) if pitches else None,
            avg_duration_ms=float(np.mean(durations)) if durations else None,
            first_seen=min(timestamps) if timestamps else None,
            last_seen=max(timestamps) if timestamps else None,
            coherence_score=coherence,
        )

    def create_dog_from_cluster(
        self,
        suggestion: ClusterSuggestion,
        name: str = "",
        notes: str = "",
    ) -> str:
        """Create a new dog profile from a cluster suggestion.

        Args:
            suggestion: The cluster to convert to a dog profile.
            name: Name for the new dog (optional).
            notes: Notes for the new dog (optional).

        Returns:
            The new dog's ID.
        """
        # Create the dog profile
        dog = self._store.create_dog(name=name, notes=notes)

        # Set the embedding to the cluster centroid
        if suggestion.centroid_embedding is not None:
            self._store.update_dog(
                dog.id,
                embedding=suggestion.centroid_embedding,
            )

        # Tag all fingerprints in the cluster to the new dog
        for fp_id in suggestion.fingerprint_ids:
            self._store.tag_fingerprint(
                fingerprint_id=fp_id,
                dog_id=dog.id,
                confidence=suggestion.coherence_score,
            )

        self._log.info(
            "dog_created_from_cluster",
            dog_id=dog.id,
            dog_name=name or "(unnamed)",
            cluster_id=suggestion.cluster_id,
            fingerprint_count=suggestion.size,
            coherence=f"{suggestion.coherence_score:.3f}",
        )

        return dog.id

    def get_cluster_samples(
        self,
        suggestion: ClusterSuggestion,
        count: int = 3,
    ) -> list[str]:
        """Get representative sample fingerprint IDs from a cluster.

        Returns fingerprints closest to the cluster centroid.

        Args:
            suggestion: The cluster to sample from.
            count: Number of samples to return.

        Returns:
            List of fingerprint IDs (evidence filenames can be retrieved).
        """
        if not suggestion.fingerprint_ids or suggestion.centroid_embedding is None:
            return suggestion.fingerprint_ids[:count]

        # Get fingerprints and compute distances to centroid
        fingerprints = []
        for fp_id in suggestion.fingerprint_ids:
            fp = self._store.get_fingerprint(fp_id)
            if fp and fp.embedding is not None:
                fingerprints.append(fp)

        if not fingerprints:
            return suggestion.fingerprint_ids[:count]

        # Compute cosine similarity to centroid
        distances = []
        for fp in fingerprints:
            sim = float(np.dot(fp.embedding, suggestion.centroid_embedding))
            distances.append((fp.id, sim))

        # Sort by similarity (highest first) and return top N
        distances.sort(key=lambda x: x[1], reverse=True)
        return [fp_id for fp_id, _ in distances[:count]]


def create_clusterer(
    store: FingerprintStore,
    min_cluster_size: int = 3,
    min_samples: int = 2,
) -> BarkClusterer:
    """Create a bark clusterer instance.

    Args:
        store: Fingerprint storage instance.
        min_cluster_size: Minimum barks to form a cluster.
        min_samples: Minimum samples for a point to be core point.

    Returns:
        Configured BarkClusterer.

    Raises:
        ImportError: If hdbscan package is not installed.
    """
    return BarkClusterer(
        store,
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
    )


def is_clustering_available() -> bool:
    """Check if clustering functionality is available.

    Returns:
        True if hdbscan is installed, False otherwise.
    """
    return HAS_HDBSCAN

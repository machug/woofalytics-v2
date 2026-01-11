"""Tests for fingerprint clustering module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import numpy as np
import pytest

from woofalytics.fingerprint.clustering import (
    ClusterSuggestion,
    is_clustering_available,
)
from woofalytics.fingerprint.models import BarkFingerprint, DogProfile


class TestIsClusteringAvailable:
    """Tests for clustering availability check."""

    def test_returns_bool(self):
        """Test that function returns a boolean."""
        result = is_clustering_available()
        assert isinstance(result, bool)


class TestClusterSuggestion:
    """Tests for ClusterSuggestion dataclass."""

    def test_cluster_suggestion_creation(self):
        """Test creating a cluster suggestion."""
        suggestion = ClusterSuggestion(
            cluster_id="cluster_0",
            fingerprint_ids=["fp1", "fp2", "fp3"],
            size=3,
            avg_pitch_hz=800.0,
            avg_duration_ms=150.0,
            first_seen=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            last_seen=datetime(2026, 1, 1, 14, 0, tzinfo=UTC),
            coherence_score=0.85,
        )

        assert suggestion.cluster_id == "cluster_0"
        assert len(suggestion.fingerprint_ids) == 3
        assert suggestion.size == 3
        assert suggestion.avg_pitch_hz == 800.0
        assert suggestion.avg_duration_ms == 150.0
        assert suggestion.coherence_score == 0.85

    def test_cluster_suggestion_defaults(self):
        """Test default values for cluster suggestion."""
        suggestion = ClusterSuggestion(cluster_id="cluster_0")

        assert suggestion.fingerprint_ids == []
        assert suggestion.size == 0
        assert suggestion.centroid_embedding is None
        assert suggestion.avg_pitch_hz is None
        assert suggestion.avg_duration_ms is None
        assert suggestion.first_seen is None
        assert suggestion.last_seen is None
        assert suggestion.coherence_score == 0.0

    def test_cluster_suggestion_to_dict(self):
        """Test dictionary conversion."""
        first_seen = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        last_seen = datetime(2026, 1, 1, 14, 0, tzinfo=UTC)

        suggestion = ClusterSuggestion(
            cluster_id="cluster_0",
            fingerprint_ids=["fp1", "fp2"],
            size=2,
            avg_pitch_hz=812.345,
            avg_duration_ms=155.678,
            first_seen=first_seen,
            last_seen=last_seen,
            coherence_score=0.8567,
        )

        data = suggestion.to_dict()

        assert data["cluster_id"] == "cluster_0"
        assert data["fingerprint_ids"] == ["fp1", "fp2"]
        assert data["size"] == 2
        # Should be rounded
        assert data["avg_pitch_hz"] == 812.3
        assert data["avg_duration_ms"] == 155.7
        assert data["coherence_score"] == 0.857
        assert data["first_seen"] == first_seen.isoformat()
        assert data["last_seen"] == last_seen.isoformat()

    def test_cluster_suggestion_to_dict_none_values(self):
        """Test dictionary conversion with None values."""
        suggestion = ClusterSuggestion(
            cluster_id="cluster_0",
            fingerprint_ids=[],
            size=0,
        )

        data = suggestion.to_dict()

        assert data["cluster_id"] == "cluster_0"
        assert data["avg_pitch_hz"] is None
        assert data["avg_duration_ms"] is None
        assert data["first_seen"] is None
        assert data["last_seen"] is None

    def test_cluster_suggestion_with_centroid(self):
        """Test cluster suggestion with embedding centroid."""
        centroid = np.array([0.5, 0.5, 0.5, 0.5])
        centroid = centroid / np.linalg.norm(centroid)

        suggestion = ClusterSuggestion(
            cluster_id="cluster_0",
            centroid_embedding=centroid,
            size=5,
        )

        assert suggestion.centroid_embedding is not None
        np.testing.assert_almost_equal(
            np.linalg.norm(suggestion.centroid_embedding), 1.0
        )


@pytest.mark.skipif(
    not is_clustering_available(),
    reason="hdbscan not installed",
)
class TestBarkClustererWithHDBSCAN:
    """Tests for BarkClusterer that require hdbscan."""

    def test_import_clusterer(self):
        """Test that BarkClusterer can be imported when hdbscan available."""
        from woofalytics.fingerprint.clustering import BarkClusterer, create_clusterer

        assert BarkClusterer is not None
        assert create_clusterer is not None

    def test_clusterer_parameters(self):
        """Test default clustering parameters."""
        from woofalytics.fingerprint.clustering import BarkClusterer

        assert BarkClusterer.MIN_CLUSTER_SIZE == 3
        assert BarkClusterer.MIN_SAMPLES == 2
        assert BarkClusterer.CLUSTER_SELECTION_EPSILON == 0.1

    def test_create_clusterer(self):
        """Test creating a clusterer instance."""
        from woofalytics.fingerprint.clustering import create_clusterer

        mock_store = MagicMock()
        clusterer = create_clusterer(mock_store)

        assert clusterer is not None
        assert clusterer._store == mock_store
        assert clusterer._min_cluster_size == 3
        assert clusterer._min_samples == 2

    def test_create_clusterer_custom_params(self):
        """Test creating a clusterer with custom parameters."""
        from woofalytics.fingerprint.clustering import create_clusterer

        mock_store = MagicMock()
        clusterer = create_clusterer(
            mock_store,
            min_cluster_size=5,
            min_samples=3,
        )

        assert clusterer._min_cluster_size == 5
        assert clusterer._min_samples == 3

    def test_cluster_untagged_insufficient_fingerprints(self):
        """Test clustering with insufficient fingerprints."""
        from woofalytics.fingerprint.clustering import create_clusterer

        mock_store = MagicMock()
        mock_store.get_untagged_fingerprints.return_value = [
            _make_fingerprint("fp1"),
            _make_fingerprint("fp2"),
        ]

        clusterer = create_clusterer(mock_store, min_cluster_size=3)
        suggestions = clusterer.cluster_untagged()

        assert suggestions == []

    def test_cluster_untagged_finds_clusters(self):
        """Test that clustering identifies distinct clusters."""
        from woofalytics.fingerprint.clustering import create_clusterer

        mock_store = MagicMock()

        # Create two distinct clusters of fingerprints
        # Cluster 1: embeddings near [1, 0, 0, ...]
        cluster1_fps = [
            _make_fingerprint(f"c1_{i}", _make_embedding(direction=0))
            for i in range(5)
        ]

        # Cluster 2: embeddings near [0, 1, 0, ...]
        cluster2_fps = [
            _make_fingerprint(f"c2_{i}", _make_embedding(direction=1))
            for i in range(5)
        ]

        mock_store.get_untagged_fingerprints.return_value = cluster1_fps + cluster2_fps

        clusterer = create_clusterer(mock_store, min_cluster_size=3)
        suggestions = clusterer.cluster_untagged()

        # Should find at least one cluster (exact count depends on HDBSCAN)
        assert len(suggestions) >= 1

    def test_create_dog_from_cluster(self):
        """Test creating a dog profile from a cluster."""
        from woofalytics.fingerprint.clustering import create_clusterer

        mock_store = MagicMock()
        mock_dog = DogProfile(id="new_dog_id", name="New Dog")
        mock_store.create_dog.return_value = mock_dog

        clusterer = create_clusterer(mock_store)

        suggestion = ClusterSuggestion(
            cluster_id="cluster_0",
            fingerprint_ids=["fp1", "fp2", "fp3"],
            size=3,
            centroid_embedding=np.array([1.0, 0.0, 0.0]),
            coherence_score=0.85,
        )

        dog_id = clusterer.create_dog_from_cluster(
            suggestion,
            name="Discovered Dog",
            notes="Auto-discovered from cluster",
        )

        assert dog_id == "new_dog_id"
        mock_store.create_dog.assert_called_once_with(
            name="Discovered Dog",
            notes="Auto-discovered from cluster",
        )
        # Should tag all fingerprints
        assert mock_store.tag_fingerprint.call_count == 3

    def test_get_cluster_samples(self):
        """Test getting representative samples from cluster."""
        from woofalytics.fingerprint.clustering import create_clusterer

        mock_store = MagicMock()
        centroid = np.array([1.0, 0.0, 0.0])

        # Create fingerprints with varying distances from centroid
        fp1 = _make_fingerprint("fp1", np.array([0.99, 0.1, 0.0]))  # Closest
        fp2 = _make_fingerprint("fp2", np.array([0.7, 0.7, 0.0]))  # Medium
        fp3 = _make_fingerprint("fp3", np.array([0.5, 0.5, 0.7]))  # Furthest

        mock_store.get_fingerprint.side_effect = [fp1, fp2, fp3]

        clusterer = create_clusterer(mock_store)

        suggestion = ClusterSuggestion(
            cluster_id="cluster_0",
            fingerprint_ids=["fp1", "fp2", "fp3"],
            size=3,
            centroid_embedding=centroid,
        )

        samples = clusterer.get_cluster_samples(suggestion, count=2)

        # Should return IDs sorted by similarity to centroid
        assert len(samples) == 2
        # First should be closest to centroid
        assert samples[0] == "fp1"


class TestClusteringUnavailable:
    """Tests for when hdbscan is not installed."""

    def test_import_error_without_hdbscan(self):
        """Test that BarkClusterer raises ImportError without hdbscan."""
        # Only run if hdbscan is not available
        if is_clustering_available():
            pytest.skip("hdbscan is installed")

        from woofalytics.fingerprint.clustering import BarkClusterer

        mock_store = MagicMock()
        with pytest.raises(ImportError, match="hdbscan"):
            BarkClusterer(mock_store)


# Helper functions


def _make_fingerprint(
    fp_id: str,
    embedding: np.ndarray | None = None,
) -> BarkFingerprint:
    """Create a mock fingerprint for testing."""
    if embedding is None:
        embedding = np.random.randn(512)
        embedding = embedding / np.linalg.norm(embedding)

    return BarkFingerprint(
        id=fp_id,
        timestamp=datetime.now(UTC),
        embedding=embedding,
        detection_probability=0.9,
        duration_ms=150.0,
        pitch_hz=800.0,
    )


def _make_embedding(direction: int, dim: int = 512) -> np.ndarray:
    """Create a normalized embedding pointing mostly in one direction."""
    embedding = np.zeros(dim)
    embedding[direction] = 1.0
    # Add small noise
    embedding += np.random.randn(dim) * 0.1
    embedding = embedding / np.linalg.norm(embedding)
    return embedding

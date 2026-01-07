"""SQLite storage for audio fingerprints and dog profiles.

This module handles persistent storage of fingerprints using SQLite,
with efficient binary storage for numpy embedding vectors.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import numpy as np
import structlog

from woofalytics.fingerprint.models import (
    BarkFingerprint,
    ClusterInfo,
    DogProfile,
    FingerprintMatch,
)

logger = structlog.get_logger(__name__)

# CLAP embedding dimension
EMBEDDING_DIM = 512

# Schema version for migrations
SCHEMA_VERSION = 4


def _serialize_embedding(arr: np.ndarray | None) -> bytes | None:
    """Serialize numpy array to bytes for SQLite storage."""
    if arr is None:
        return None
    return arr.astype(np.float32).tobytes()


def _deserialize_embedding(data: bytes | None, shape: tuple[int, ...] = (EMBEDDING_DIM,)) -> np.ndarray | None:
    """Deserialize bytes to numpy array."""
    if data is None:
        return None
    return np.frombuffer(data, dtype=np.float32).reshape(shape)


class FingerprintStore:
    """SQLite-based storage for fingerprints and dog profiles.

    Provides CRUD operations for dog profiles, bark fingerprints,
    and cluster management with efficient embedding vector storage.
    """

    def __init__(self, db_path: Path | str) -> None:
        """Initialize the fingerprint store.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Dog profiles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dog_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confirmed INTEGER NOT NULL DEFAULT 0,
                    confirmed_at TEXT,
                    min_samples_for_auto_tag INTEGER NOT NULL DEFAULT 5,
                    embedding BLOB,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    first_seen TEXT,
                    last_seen TEXT,
                    total_barks INTEGER NOT NULL DEFAULT 0,
                    avg_duration_ms REAL,
                    avg_pitch_hz REAL
                )
            """)

            # Bark fingerprints table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bark_fingerprints (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    embedding BLOB,
                    dog_id TEXT,
                    match_confidence REAL,
                    cluster_id TEXT,
                    evidence_filename TEXT,
                    detection_probability REAL NOT NULL DEFAULT 0,
                    doa_degrees INTEGER,
                    duration_ms REAL,
                    pitch_hz REAL,
                    spectral_centroid_hz REAL,
                    mfcc_mean BLOB,
                    FOREIGN KEY (dog_id) REFERENCES dog_profiles(id) ON DELETE SET NULL,
                    FOREIGN KEY (cluster_id) REFERENCES clusters(id) ON DELETE SET NULL
                )
            """)

            # Clusters table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clusters (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    centroid BLOB,
                    bark_count INTEGER NOT NULL DEFAULT 0,
                    first_seen TEXT,
                    last_seen TEXT,
                    suggested_name TEXT NOT NULL DEFAULT '',
                    avg_pitch_hz REAL,
                    avg_duration_ms REAL
                )
            """)

            # Schema version table - handle legacy format migration
            # Old format: version INTEGER PRIMARY KEY (version is the PK)
            # New format: id INTEGER PRIMARY KEY, version INTEGER (single row with id=1)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
            if cursor.fetchone():
                # Check if we have the old schema format (version as primary key)
                cursor.execute("PRAGMA table_info(schema_version)")
                columns = {row[1]: row for row in cursor.fetchall()}
                if "id" not in columns:
                    # Old format - get current version and recreate table
                    cursor.execute("SELECT MAX(version) FROM schema_version")
                    old_version = cursor.fetchone()[0] or 1
                    cursor.execute("DROP TABLE schema_version")
                    cursor.execute("""
                        CREATE TABLE schema_version (
                            id INTEGER PRIMARY KEY DEFAULT 1,
                            version INTEGER NOT NULL DEFAULT 1
                        )
                    """)
                    cursor.execute("INSERT INTO schema_version (id, version) VALUES (1, ?)", (old_version,))
            else:
                # Fresh database - create new format
                cursor.execute("""
                    CREATE TABLE schema_version (
                        id INTEGER PRIMARY KEY DEFAULT 1,
                        version INTEGER NOT NULL DEFAULT 1
                    )
                """)
                cursor.execute("INSERT INTO schema_version (id, version) VALUES (1, 1)")

            # Get current schema version
            cursor.execute("SELECT version FROM schema_version WHERE id = 1")
            current_version = cursor.fetchone()[0]

            if current_version < 2:
                # Migration: Add confirmation columns to dog_profiles
                try:
                    cursor.execute("ALTER TABLE dog_profiles ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                try:
                    cursor.execute("ALTER TABLE dog_profiles ADD COLUMN confirmed_at TEXT")
                except sqlite3.OperationalError:
                    pass
                try:
                    cursor.execute("ALTER TABLE dog_profiles ADD COLUMN min_samples_for_auto_tag INTEGER NOT NULL DEFAULT 5")
                except sqlite3.OperationalError:
                    pass
                cursor.execute("UPDATE schema_version SET version = 2 WHERE id = 1")
                logger.info("schema_migrated", from_version=current_version, to_version=2)
                current_version = 2

            if current_version < 3:
                # Migration: Add rejection_reason for false positive marking
                try:
                    cursor.execute("ALTER TABLE bark_fingerprints ADD COLUMN rejection_reason TEXT")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                cursor.execute("UPDATE schema_version SET version = 3 WHERE id = 1")
                logger.info("schema_migrated", from_version=current_version, to_version=3)
                current_version = 3

            if current_version < 4:
                # Migration: Add confirmation columns to bark_fingerprints
                try:
                    cursor.execute("ALTER TABLE bark_fingerprints ADD COLUMN confirmed INTEGER")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                try:
                    cursor.execute("ALTER TABLE bark_fingerprints ADD COLUMN confirmed_at TEXT")
                except sqlite3.OperationalError:
                    pass
                cursor.execute("UPDATE schema_version SET version = 4 WHERE id = 1")
                logger.info("schema_migrated", from_version=current_version, to_version=4)

            # Indexes for common queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fingerprints_dog_id ON bark_fingerprints(dog_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fingerprints_cluster_id ON bark_fingerprints(cluster_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fingerprints_timestamp ON bark_fingerprints(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fingerprints_untagged ON bark_fingerprints(dog_id) WHERE dog_id IS NULL")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fingerprints_rejected ON bark_fingerprints(rejection_reason) WHERE rejection_reason IS NOT NULL")

            conn.commit()

        logger.info("fingerprint_store_initialized", db_path=str(self.db_path))

    # --- Dog Profile Operations ---

    def create_dog(self, name: str = "", notes: str = "") -> DogProfile:
        """Create a new dog profile.

        Args:
            name: Name for the dog (can be empty initially).
            notes: Optional notes about the dog.

        Returns:
            Created DogProfile.
        """
        profile = DogProfile(name=name, notes=notes)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO dog_profiles
                (id, name, notes, created_at, updated_at, sample_count, total_barks)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.name,
                    profile.notes,
                    profile.created_at.isoformat(),
                    profile.updated_at.isoformat(),
                    0,
                    0,
                ),
            )
            conn.commit()

        logger.info("dog_profile_created", dog_id=profile.id, name=name)
        return profile

    def get_dog(self, dog_id: str) -> DogProfile | None:
        """Get a dog profile by ID.

        Args:
            dog_id: The dog's unique ID.

        Returns:
            DogProfile if found, None otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dog_profiles WHERE id = ?", (dog_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return DogProfile(
                id=row["id"],
                name=row["name"],
                notes=row["notes"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                confirmed=bool(row["confirmed"]),
                confirmed_at=datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
                min_samples_for_auto_tag=row["min_samples_for_auto_tag"],
                embedding=_deserialize_embedding(row["embedding"]),
                sample_count=row["sample_count"],
                first_seen=datetime.fromisoformat(row["first_seen"]) if row["first_seen"] else None,
                last_seen=datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None,
                total_barks=row["total_barks"],
                avg_duration_ms=row["avg_duration_ms"],
                avg_pitch_hz=row["avg_pitch_hz"],
            )

    def list_dogs(self) -> list[DogProfile]:
        """List all dog profiles.

        Returns:
            List of all DogProfiles.
        """
        dogs = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dog_profiles ORDER BY name")

            for row in cursor.fetchall():
                dogs.append(
                    DogProfile(
                        id=row["id"],
                        name=row["name"],
                        notes=row["notes"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.fromisoformat(row["updated_at"]),
                        confirmed=bool(row["confirmed"]),
                        confirmed_at=datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
                        min_samples_for_auto_tag=row["min_samples_for_auto_tag"],
                        embedding=_deserialize_embedding(row["embedding"]),
                        sample_count=row["sample_count"],
                        first_seen=datetime.fromisoformat(row["first_seen"]) if row["first_seen"] else None,
                        last_seen=datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None,
                        total_barks=row["total_barks"],
                        avg_duration_ms=row["avg_duration_ms"],
                        avg_pitch_hz=row["avg_pitch_hz"],
                    )
                )

        return dogs

    def update_dog(
        self,
        dog_id: str,
        name: str | None = None,
        notes: str | None = None,
        embedding: np.ndarray | None = None,
    ) -> DogProfile | None:
        """Update a dog profile.

        Args:
            dog_id: The dog's unique ID.
            name: New name (if provided).
            notes: New notes (if provided).
            embedding: New embedding (if provided).

        Returns:
            Updated DogProfile if found, None otherwise.
        """
        profile = self.get_dog(dog_id)
        if not profile:
            return None

        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
            profile.name = name

        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
            profile.notes = notes

        if embedding is not None:
            updates.append("embedding = ?")
            params.append(_serialize_embedding(embedding))
            profile.embedding = embedding

        if updates:
            updates.append("updated_at = ?")
            now = datetime.now(timezone.utc)
            params.append(now.isoformat())
            params.append(dog_id)
            profile.updated_at = now

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE dog_profiles SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                conn.commit()

            logger.info("dog_profile_updated", dog_id=dog_id)

        return profile

    def delete_dog(self, dog_id: str) -> bool:
        """Delete a dog profile.

        Fingerprints linked to this dog will have their dog_id set to NULL.

        Args:
            dog_id: The dog's unique ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dog_profiles WHERE id = ?", (dog_id,))
            deleted = cursor.rowcount > 0
            conn.commit()

        if deleted:
            logger.info("dog_profile_deleted", dog_id=dog_id)

        return deleted

    def update_dog_stats(
        self,
        dog_id: str,
        embedding: np.ndarray,
        timestamp: datetime,
    ) -> None:
        """Update dog profile with a new bark sample.

        Incrementally updates the embedding and statistics.

        Args:
            dog_id: The dog's unique ID.
            embedding: CLAP embedding from the new bark.
            timestamp: When the bark was detected.
        """
        profile = self.get_dog(dog_id)
        if not profile:
            return

        # Update embedding with weighted average
        profile.update_embedding(embedding)

        # Update timestamps
        if profile.first_seen is None or timestamp < profile.first_seen:
            profile.first_seen = timestamp
        if profile.last_seen is None or timestamp > profile.last_seen:
            profile.last_seen = timestamp

        profile.total_barks += 1

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE dog_profiles SET
                    embedding = ?,
                    sample_count = ?,
                    first_seen = ?,
                    last_seen = ?,
                    total_barks = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    _serialize_embedding(profile.embedding),
                    profile.sample_count,
                    profile.first_seen.isoformat() if profile.first_seen else None,
                    profile.last_seen.isoformat() if profile.last_seen else None,
                    profile.total_barks,
                    datetime.now(timezone.utc).isoformat(),
                    dog_id,
                ),
            )
            conn.commit()

    def confirm_dog(self, dog_id: str, min_samples: int | None = None) -> DogProfile | None:
        """Confirm a dog for auto-tagging.

        A confirmed dog can have new barks auto-tagged to it once
        it has sufficient samples.

        Args:
            dog_id: The dog's unique ID.
            min_samples: Override the minimum samples required for auto-tag.

        Returns:
            Updated DogProfile if found, None otherwise.
        """
        profile = self.get_dog(dog_id)
        if not profile:
            return None

        now = datetime.now(timezone.utc)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if min_samples is not None:
                cursor.execute(
                    """
                    UPDATE dog_profiles SET
                        confirmed = 1,
                        confirmed_at = ?,
                        min_samples_for_auto_tag = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), min_samples, now.isoformat(), dog_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE dog_profiles SET
                        confirmed = 1,
                        confirmed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), now.isoformat(), dog_id),
                )
            conn.commit()

        logger.info("dog_confirmed", dog_id=dog_id, min_samples=min_samples)
        return self.get_dog(dog_id)

    def unconfirm_dog(self, dog_id: str) -> DogProfile | None:
        """Remove confirmation from a dog (disable auto-tagging).

        Args:
            dog_id: The dog's unique ID.

        Returns:
            Updated DogProfile if found, None otherwise.
        """
        profile = self.get_dog(dog_id)
        if not profile:
            return None

        now = datetime.now(timezone.utc)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE dog_profiles SET
                    confirmed = 0,
                    confirmed_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), dog_id),
            )
            conn.commit()

        logger.info("dog_unconfirmed", dog_id=dog_id)
        return self.get_dog(dog_id)

    # --- Fingerprint Operations ---

    def save_fingerprint(self, fingerprint: BarkFingerprint) -> None:
        """Save a bark fingerprint.

        Args:
            fingerprint: The fingerprint to save.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO bark_fingerprints
                (id, timestamp, embedding, dog_id, match_confidence, cluster_id,
                 evidence_filename, detection_probability, doa_degrees,
                 duration_ms, pitch_hz, spectral_centroid_hz, mfcc_mean)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint.id,
                    fingerprint.timestamp.isoformat(),
                    _serialize_embedding(fingerprint.embedding),
                    fingerprint.dog_id,
                    fingerprint.match_confidence,
                    fingerprint.cluster_id,
                    fingerprint.evidence_filename,
                    fingerprint.detection_probability,
                    fingerprint.doa_degrees,
                    fingerprint.duration_ms,
                    fingerprint.pitch_hz,
                    fingerprint.spectral_centroid_hz,
                    _serialize_embedding(fingerprint.mfcc_mean) if fingerprint.mfcc_mean is not None else None,
                ),
            )
            conn.commit()

    def get_fingerprint(self, fingerprint_id: str) -> BarkFingerprint | None:
        """Get a fingerprint by ID.

        Args:
            fingerprint_id: The fingerprint's unique ID.

        Returns:
            BarkFingerprint if found, None otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bark_fingerprints WHERE id = ?", (fingerprint_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return BarkFingerprint(
                id=row["id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                embedding=_deserialize_embedding(row["embedding"]),
                dog_id=row["dog_id"],
                match_confidence=row["match_confidence"],
                cluster_id=row["cluster_id"],
                evidence_filename=row["evidence_filename"],
                rejection_reason=row["rejection_reason"],
                confirmed=bool(row["confirmed"]) if row["confirmed"] is not None else None,
                confirmed_at=datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
                detection_probability=row["detection_probability"],
                doa_degrees=row["doa_degrees"],
                duration_ms=row["duration_ms"],
                pitch_hz=row["pitch_hz"],
                spectral_centroid_hz=row["spectral_centroid_hz"],
                mfcc_mean=_deserialize_embedding(row["mfcc_mean"], (13,)) if row["mfcc_mean"] else None,
            )

    def get_untagged_fingerprints(self, limit: int = 100) -> list[BarkFingerprint]:
        """Get fingerprints that haven't been tagged to a dog.

        Excludes rejected fingerprints by default.

        Args:
            limit: Maximum number to return.

        Returns:
            List of untagged fingerprints.
        """
        fingerprints = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM bark_fingerprints
                WHERE dog_id IS NULL AND rejection_reason IS NULL
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )

            for row in cursor.fetchall():
                fingerprints.append(
                    BarkFingerprint(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        embedding=_deserialize_embedding(row["embedding"]),
                        dog_id=row["dog_id"],
                        match_confidence=row["match_confidence"],
                        cluster_id=row["cluster_id"],
                        evidence_filename=row["evidence_filename"],
                        rejection_reason=row["rejection_reason"],
                        confirmed=bool(row["confirmed"]) if row["confirmed"] is not None else None,
                        confirmed_at=datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
                        detection_probability=row["detection_probability"],
                        doa_degrees=row["doa_degrees"],
                        duration_ms=row["duration_ms"],
                        pitch_hz=row["pitch_hz"],
                        spectral_centroid_hz=row["spectral_centroid_hz"],
                        mfcc_mean=_deserialize_embedding(row["mfcc_mean"], (13,)) if row["mfcc_mean"] else None,
                    )
                )

        return fingerprints

    def tag_fingerprint(self, fingerprint_id: str, dog_id: str, confidence: float) -> bool:
        """Tag a fingerprint as belonging to a dog.

        Args:
            fingerprint_id: The fingerprint to tag.
            dog_id: The dog to assign it to.
            confidence: Match confidence (0-1).

        Returns:
            True if updated, False if fingerprint not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bark_fingerprints
                SET dog_id = ?, match_confidence = ?, cluster_id = NULL
                WHERE id = ?
                """,
                (dog_id, confidence, fingerprint_id),
            )
            updated = cursor.rowcount > 0
            conn.commit()

        return updated

    def untag_fingerprint(self, fingerprint_id: str) -> bool:
        """Remove dog association from a fingerprint.

        Args:
            fingerprint_id: The fingerprint to untag.

        Returns:
            True if updated, False if fingerprint not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bark_fingerprints
                SET dog_id = NULL, match_confidence = NULL
                WHERE id = ?
                """,
                (fingerprint_id,),
            )
            updated = cursor.rowcount > 0
            conn.commit()

        return updated

    def reject_fingerprint(self, fingerprint_id: str, reason: str) -> bool:
        """Mark a fingerprint as rejected (false positive).

        Rejected fingerprints are hidden from normal views but data is preserved.
        Common reasons: "speech", "wind", "bird", "other".

        Args:
            fingerprint_id: The fingerprint to reject.
            reason: The rejection reason (e.g., "speech", "wind", "bird", "other").

        Returns:
            True if updated, False if fingerprint not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bark_fingerprints
                SET rejection_reason = ?, dog_id = NULL, match_confidence = NULL
                WHERE id = ?
                """,
                (reason, fingerprint_id),
            )
            updated = cursor.rowcount > 0
            conn.commit()

        if updated:
            logger.info("fingerprint_rejected", fingerprint_id=fingerprint_id, reason=reason)

        return updated

    def unreject_fingerprint(self, fingerprint_id: str) -> bool:
        """Remove rejection status from a fingerprint.

        Args:
            fingerprint_id: The fingerprint to unreject.

        Returns:
            True if updated, False if fingerprint not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bark_fingerprints
                SET rejection_reason = NULL
                WHERE id = ?
                """,
                (fingerprint_id,),
            )
            updated = cursor.rowcount > 0
            conn.commit()

        if updated:
            logger.info("fingerprint_unrejected", fingerprint_id=fingerprint_id)

        return updated

    def confirm_fingerprint(self, fingerprint_id: str) -> bool:
        """Confirm a fingerprint as a real bark (even if dog is unknown).

        This marks the fingerprint as reviewed and confirmed to be a bark,
        distinguishing it from unreviewed fingerprints.

        Args:
            fingerprint_id: The fingerprint to confirm.

        Returns:
            True if updated, False if fingerprint not found.
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bark_fingerprints
                SET confirmed = 1, confirmed_at = ?, rejection_reason = NULL
                WHERE id = ?
                """,
                (now, fingerprint_id),
            )
            updated = cursor.rowcount > 0
            conn.commit()

        if updated:
            logger.info("fingerprint_confirmed", fingerprint_id=fingerprint_id)

        return updated

    def unconfirm_fingerprint(self, fingerprint_id: str) -> bool:
        """Remove confirmation status from a fingerprint.

        This returns the fingerprint to an unreviewed state.

        Args:
            fingerprint_id: The fingerprint to unconfirm.

        Returns:
            True if updated, False if fingerprint not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bark_fingerprints
                SET confirmed = NULL, confirmed_at = NULL
                WHERE id = ?
                """,
                (fingerprint_id,),
            )
            updated = cursor.rowcount > 0
            conn.commit()

        if updated:
            logger.info("fingerprint_unconfirmed", fingerprint_id=fingerprint_id)

        return updated

    def link_evidence_to_fingerprints(
        self,
        evidence_filename: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """Link an evidence file to fingerprints created within a time range.

        Args:
            evidence_filename: The filename of the evidence recording.
            start_time: Start of the time range (inclusive).
            end_time: End of the time range (inclusive).

        Returns:
            Number of fingerprints updated.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bark_fingerprints
                SET evidence_filename = ?
                WHERE timestamp >= ? AND timestamp <= ?
                AND evidence_filename IS NULL
                """,
                (evidence_filename, start_time.isoformat(), end_time.isoformat()),
            )
            updated = cursor.rowcount
            conn.commit()

        if updated > 0:
            logger.info(
                "evidence_linked_to_fingerprints",
                filename=evidence_filename,
                count=updated,
            )

        return updated

    def get_fingerprints_for_dog(self, dog_id: str, limit: int = 100) -> list[BarkFingerprint]:
        """Get all fingerprints for a specific dog.

        Args:
            dog_id: The dog's unique ID.
            limit: Maximum number to return.

        Returns:
            List of fingerprints for this dog.
        """
        fingerprints = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM bark_fingerprints
                WHERE dog_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (dog_id, limit),
            )

            for row in cursor.fetchall():
                fingerprints.append(
                    BarkFingerprint(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        embedding=_deserialize_embedding(row["embedding"]),
                        dog_id=row["dog_id"],
                        match_confidence=row["match_confidence"],
                        cluster_id=row["cluster_id"],
                        evidence_filename=row["evidence_filename"],
                        rejection_reason=row["rejection_reason"],
                        confirmed=bool(row["confirmed"]) if row["confirmed"] is not None else None,
                        confirmed_at=datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
                        detection_probability=row["detection_probability"],
                        doa_degrees=row["doa_degrees"],
                        duration_ms=row["duration_ms"],
                        pitch_hz=row["pitch_hz"],
                        spectral_centroid_hz=row["spectral_centroid_hz"],
                        mfcc_mean=_deserialize_embedding(row["mfcc_mean"], (13,)) if row["mfcc_mean"] else None,
                    )
                )

        return fingerprints

    # --- Matching Operations ---

    def find_matches(
        self,
        embedding: np.ndarray,
        threshold: float = 0.75,
        top_k: int = 3,
        only_auto_taggable: bool = True,
    ) -> list[FingerprintMatch]:
        """Find matching dogs for a given embedding.

        Uses cosine similarity to compare against known dog profiles.

        Args:
            embedding: CLAP embedding to match.
            threshold: Minimum similarity to consider a match.
            top_k: Maximum number of matches to return.
            only_auto_taggable: If True, only match against dogs that are
                confirmed and have sufficient samples for auto-tagging.
                Set to False for manual matching/suggestion.

        Returns:
            List of matches sorted by confidence (highest first).
        """
        dogs = self.list_dogs()
        matches = []

        # Normalize query embedding
        query_norm = embedding / np.linalg.norm(embedding)

        for dog in dogs:
            if dog.embedding is None:
                continue

            # Filter by auto-tag eligibility if requested
            if only_auto_taggable and not dog.can_auto_tag():
                continue

            # Cosine similarity
            similarity = float(np.dot(query_norm, dog.embedding))

            if similarity >= threshold:
                matches.append(
                    FingerprintMatch(
                        dog_id=dog.id,
                        dog_name=dog.name,
                        confidence=similarity,
                        sample_count=dog.sample_count,
                    )
                )

        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches[:top_k]

    def merge_dogs(self, source_id: str, target_id: str) -> bool:
        """Merge two dog profiles.

        All fingerprints from source are reassigned to target,
        and source is deleted.

        Args:
            source_id: Dog to merge from (will be deleted).
            target_id: Dog to merge into.

        Returns:
            True if merged successfully.
        """
        source = self.get_dog(source_id)
        target = self.get_dog(target_id)

        if not source or not target:
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Move all fingerprints to target
            cursor.execute(
                "UPDATE bark_fingerprints SET dog_id = ? WHERE dog_id = ?",
                (target_id, source_id),
            )

            # Merge embeddings if both have them
            if source.embedding is not None and target.embedding is not None:
                # Weighted average based on sample counts
                total = source.sample_count + target.sample_count
                if total > 0:
                    merged_embedding = (
                        source.embedding * source.sample_count +
                        target.embedding * target.sample_count
                    ) / total
                    merged_embedding = merged_embedding / np.linalg.norm(merged_embedding)

                    cursor.execute(
                        """
                        UPDATE dog_profiles SET
                            embedding = ?,
                            sample_count = ?,
                            total_barks = total_barks + ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            _serialize_embedding(merged_embedding),
                            total,
                            source.total_barks,
                            datetime.now(timezone.utc).isoformat(),
                            target_id,
                        ),
                    )

            # Delete source
            cursor.execute("DELETE FROM dog_profiles WHERE id = ?", (source_id,))
            conn.commit()

        logger.info("dogs_merged", source_id=source_id, target_id=target_id)
        return True

    # --- Fingerprint Query Operations ---

    def list_fingerprints(
        self,
        limit: int = 100,
        offset: int = 0,
        dog_id: str | None = None,
        tagged: bool | None = None,
        min_confidence: float | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        rejected: bool | None = None,
    ) -> tuple[list[BarkFingerprint], int]:
        """List fingerprints with filtering and pagination.

        Args:
            limit: Maximum number of fingerprints to return.
            offset: Number of fingerprints to skip.
            dog_id: Filter by specific dog.
            tagged: If True, only tagged; if False, only untagged; if None, all.
            min_confidence: Minimum match confidence (0-1).
            start_date: Filter by timestamp >= start_date.
            end_date: Filter by timestamp <= end_date.
            rejected: If True, only rejected; if False, exclude rejected; if None, all.

        Returns:
            Tuple of (list of fingerprints, total count matching filter).
        """
        conditions = []
        params: list = []

        if dog_id is not None:
            conditions.append("dog_id = ?")
            params.append(dog_id)

        if tagged is True:
            conditions.append("dog_id IS NOT NULL")
        elif tagged is False:
            conditions.append("dog_id IS NULL")

        if min_confidence is not None:
            conditions.append("match_confidence >= ?")
            params.append(min_confidence)

        if start_date is not None:
            conditions.append("timestamp >= ?")
            params.append(start_date.isoformat())

        if end_date is not None:
            conditions.append("timestamp <= ?")
            params.append(end_date.isoformat())

        # Rejection filter
        if rejected is True:
            conditions.append("rejection_reason IS NOT NULL")
        elif rejected is False:
            conditions.append("rejection_reason IS NULL")
        # If rejected is None, show all (no filter)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        fingerprints = []
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get total count
            cursor.execute(
                f"SELECT COUNT(*) FROM bark_fingerprints WHERE {where_clause}",
                params,
            )
            total = cursor.fetchone()[0]

            # Get fingerprints with pagination
            cursor.execute(
                f"""
                SELECT * FROM bark_fingerprints
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            )

            for row in cursor.fetchall():
                fingerprints.append(
                    BarkFingerprint(
                        id=row["id"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        embedding=_deserialize_embedding(row["embedding"]),
                        dog_id=row["dog_id"],
                        match_confidence=row["match_confidence"],
                        cluster_id=row["cluster_id"],
                        evidence_filename=row["evidence_filename"],
                        rejection_reason=row["rejection_reason"],
                        confirmed=bool(row["confirmed"]) if row["confirmed"] is not None else None,
                        confirmed_at=datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
                        detection_probability=row["detection_probability"],
                        doa_degrees=row["doa_degrees"],
                        duration_ms=row["duration_ms"],
                        pitch_hz=row["pitch_hz"],
                        spectral_centroid_hz=row["spectral_centroid_hz"],
                        mfcc_mean=_deserialize_embedding(row["mfcc_mean"], (13,)) if row["mfcc_mean"] else None,
                    )
                )

        return fingerprints, total

    def get_dog_acoustic_aggregates(self) -> list[dict]:
        """Get aggregate acoustic statistics per dog.

        Returns:
            List of dictionaries with per-dog acoustic statistics.
        """
        aggregates = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    d.id as dog_id,
                    d.name as dog_name,
                    AVG(f.pitch_hz) as avg_pitch_hz,
                    MIN(f.pitch_hz) as min_pitch_hz,
                    MAX(f.pitch_hz) as max_pitch_hz,
                    AVG(f.duration_ms) as avg_duration_ms,
                    MIN(f.duration_ms) as min_duration_ms,
                    MAX(f.duration_ms) as max_duration_ms,
                    AVG(f.spectral_centroid_hz) as avg_spectral_centroid_hz,
                    COUNT(f.id) as total_barks,
                    MIN(f.timestamp) as first_seen,
                    MAX(f.timestamp) as last_seen
                FROM dog_profiles d
                LEFT JOIN bark_fingerprints f ON d.id = f.dog_id
                GROUP BY d.id, d.name
                ORDER BY d.name
            """)

            for row in cursor.fetchall():
                aggregates.append({
                    "dog_id": row["dog_id"],
                    "dog_name": row["dog_name"],
                    "avg_pitch_hz": row["avg_pitch_hz"],
                    "min_pitch_hz": row["min_pitch_hz"],
                    "max_pitch_hz": row["max_pitch_hz"],
                    "avg_duration_ms": row["avg_duration_ms"],
                    "min_duration_ms": row["min_duration_ms"],
                    "max_duration_ms": row["max_duration_ms"],
                    "avg_spectral_centroid_hz": row["avg_spectral_centroid_hz"],
                    "total_barks": row["total_barks"],
                    "first_seen": datetime.fromisoformat(row["first_seen"]) if row["first_seen"] else None,
                    "last_seen": datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None,
                })

        return aggregates

    def get_dog_acoustic_stats(self, dog_id: str) -> dict | None:
        """Get acoustic statistics for a specific dog.

        Args:
            dog_id: The dog's unique identifier.

        Returns:
            Dictionary with acoustic stats, or None if dog not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    AVG(f.pitch_hz) as avg_pitch_hz,
                    MIN(f.pitch_hz) as min_pitch_hz,
                    MAX(f.pitch_hz) as max_pitch_hz,
                    AVG(f.duration_ms) as avg_duration_ms,
                    AVG(f.spectral_centroid_hz) as avg_spectral_centroid_hz,
                    COUNT(f.id) as sample_count
                FROM bark_fingerprints f
                WHERE f.dog_id = ? AND f.pitch_hz IS NOT NULL
            """, (dog_id,))

            row = cursor.fetchone()
            if row and row["sample_count"] > 0:
                return {
                    "avg_pitch_hz": row["avg_pitch_hz"],
                    "min_pitch_hz": row["min_pitch_hz"],
                    "max_pitch_hz": row["max_pitch_hz"],
                    "avg_duration_ms": row["avg_duration_ms"],
                    "avg_spectral_centroid_hz": row["avg_spectral_centroid_hz"],
                    "sample_count": row["sample_count"],
                }
            return None

    # --- Stats ---

    def get_stats(self) -> dict[str, int]:
        """Get summary statistics.

        Returns:
            Dictionary with counts of dogs, fingerprints, untagged, rejected, etc.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM dog_profiles")
            dog_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM bark_fingerprints")
            fingerprint_count = cursor.fetchone()[0]

            # Untagged excludes rejected fingerprints
            cursor.execute("SELECT COUNT(*) FROM bark_fingerprints WHERE dog_id IS NULL AND rejection_reason IS NULL")
            untagged_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM bark_fingerprints WHERE rejection_reason IS NOT NULL")
            rejected_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM clusters")
            cluster_count = cursor.fetchone()[0]

            return {
                "dogs": dog_count,
                "fingerprints": fingerprint_count,
                "untagged": untagged_count,
                "rejected": rejected_count,
                "clusters": cluster_count,
            }

    # --- Maintenance Operations ---

    def delete_fingerprint(self, fingerprint_id: str) -> bool:
        """Delete a single fingerprint.

        Args:
            fingerprint_id: The fingerprint's unique ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bark_fingerprints WHERE id = ?", (fingerprint_id,))
            deleted = cursor.rowcount > 0
            conn.commit()

        if deleted:
            logger.info("fingerprint_deleted", fingerprint_id=fingerprint_id)

        return deleted

    def purge_fingerprints(
        self,
        before: datetime | None = None,
        untagged_only: bool = False,
    ) -> int:
        """Purge fingerprints matching criteria.

        Args:
            before: Delete fingerprints older than this timestamp.
            untagged_only: If True, only delete untagged fingerprints.

        Returns:
            Number of fingerprints deleted.
        """
        conditions = []
        params: list = []

        if before is not None:
            conditions.append("timestamp < ?")
            params.append(before.isoformat())

        if untagged_only:
            conditions.append("dog_id IS NULL")

        if not conditions:
            # Safety: require at least one condition
            logger.warning("purge_fingerprints_no_conditions")
            return 0

        where_clause = " AND ".join(conditions)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Count first
            cursor.execute(f"SELECT COUNT(*) FROM bark_fingerprints WHERE {where_clause}", params)
            count = cursor.fetchone()[0]

            if count > 0:
                cursor.execute(f"DELETE FROM bark_fingerprints WHERE {where_clause}", params)
                conn.commit()
                logger.info(
                    "fingerprints_purged",
                    count=count,
                    before=before.isoformat() if before else None,
                    untagged_only=untagged_only,
                )

        return count

    def recalculate_dog_bark_counts(self) -> int:
        """Recalculate all dog bark counts from actual fingerprint data.

        This fixes any discrepancies between cached total_barks values
        and actual tagged fingerprint counts (e.g., after purging).

        Returns:
            Number of dogs updated.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get actual counts from fingerprints
            cursor.execute("""
                SELECT dog_id, COUNT(*) as actual_count
                FROM bark_fingerprints
                WHERE dog_id IS NOT NULL
                GROUP BY dog_id
            """)
            actual_counts = {row["dog_id"]: row["actual_count"] for row in cursor.fetchall()}

            # Get all dogs
            cursor.execute("SELECT id, total_barks FROM dog_profiles")
            dogs = cursor.fetchall()

            updated = 0
            for dog in dogs:
                dog_id = dog["id"]
                current = dog["total_barks"]
                actual = actual_counts.get(dog_id, 0)

                if current != actual:
                    cursor.execute(
                        "UPDATE dog_profiles SET total_barks = ?, updated_at = ? WHERE id = ?",
                        (actual, datetime.now().isoformat(), dog_id),
                    )
                    updated += 1
                    logger.info(
                        "dog_bark_count_corrected",
                        dog_id=dog_id,
                        old_count=current,
                        new_count=actual,
                    )

            if updated > 0:
                conn.commit()
                logger.info("dog_bark_counts_recalculated", dogs_updated=updated)

        return updated

    def purge_all_fingerprints(self) -> int:
        """Delete ALL fingerprints. Use with caution.

        Returns:
            Number of fingerprints deleted.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bark_fingerprints")
            count = cursor.fetchone()[0]

            if count > 0:
                cursor.execute("DELETE FROM bark_fingerprints")
                conn.commit()
                logger.warning("all_fingerprints_purged", count=count)

        return count

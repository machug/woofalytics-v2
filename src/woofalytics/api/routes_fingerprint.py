"""REST API routes for fingerprint and dog profile management.

This module provides endpoints for:
- Dog profile CRUD operations
- Bark fingerprint tagging and correction
- Fingerprint statistics
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from woofalytics.api.schemas_fingerprint import (
    BarkFingerprintSchema,
    BulkTagRequestSchema,
    BulkTagResultSchema,
    ClusterResultSchema,
    ClusterSuggestionSchema,
    ConfirmDogRequestSchema,
    CorrectBarkRequestSchema,
    CreateDogFromClusterRequestSchema,
    DogAcousticStatsSchema,
    DogBarksListSchema,
    DogProfileCreateSchema,
    DogProfileSchema,
    DogProfileUpdateSchema,
    FingerprintAggregatesSchema,
    FingerprintListSchema,
    FingerprintStatsSchema,
    PurgeResultSchema,
    RejectBarkRequestSchema,
    TagBarkRequestSchema,
    UntaggedBarksListSchema,
)
from woofalytics.fingerprint.clustering import (
    ClusterSuggestion,
    create_clusterer,
    is_clustering_available,
)
from woofalytics.config import Settings
from woofalytics.fingerprint.models import BarkFingerprint, DogProfile
from woofalytics.fingerprint.storage import FingerprintStore

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["fingerprints"])


# Dependency injection
def get_settings(request: Request) -> Settings:
    """Get settings from app state."""
    return request.app.state.settings


def get_fingerprint_store(request: Request) -> FingerprintStore:
    """Get fingerprint store from app state.

    The store is lazily initialized on first access.
    """
    if not hasattr(request.app.state, "fingerprint_store"):
        settings = request.app.state.settings
        db_path = Path(settings.evidence.directory) / "fingerprints.db"
        request.app.state.fingerprint_store = FingerprintStore(db_path)
        logger.info("fingerprint_store_initialized", db_path=str(db_path))
    return request.app.state.fingerprint_store


def _dog_to_schema(dog: DogProfile) -> DogProfileSchema:
    """Convert DogProfile model to API schema."""
    return DogProfileSchema(
        id=dog.id,
        name=dog.name,
        notes=dog.notes,
        created_at=dog.created_at,
        updated_at=dog.updated_at,
        confirmed=dog.confirmed,
        confirmed_at=dog.confirmed_at,
        min_samples_for_auto_tag=dog.min_samples_for_auto_tag,
        can_auto_tag=dog.can_auto_tag(),
        sample_count=dog.sample_count,
        first_seen=dog.first_seen,
        last_seen=dog.last_seen,
        total_barks=dog.total_barks,
        avg_duration_ms=dog.avg_duration_ms,
        avg_pitch_hz=dog.avg_pitch_hz,
    )


def _fingerprint_to_schema(
    fingerprint: BarkFingerprint,
    dog_name: str | None = None,
) -> BarkFingerprintSchema:
    """Convert BarkFingerprint model to API schema."""
    return BarkFingerprintSchema(
        id=fingerprint.id,
        timestamp=fingerprint.timestamp,
        dog_id=fingerprint.dog_id,
        dog_name=dog_name,
        match_confidence=fingerprint.match_confidence,
        cluster_id=fingerprint.cluster_id,
        evidence_filename=fingerprint.evidence_filename,
        rejection_reason=fingerprint.rejection_reason,
        confirmed=fingerprint.confirmed,
        confirmed_at=fingerprint.confirmed_at,
        detection_probability=fingerprint.detection_probability,
        doa_degrees=fingerprint.doa_degrees,
        duration_ms=fingerprint.duration_ms,
        pitch_hz=fingerprint.pitch_hz,
        spectral_centroid_hz=fingerprint.spectral_centroid_hz,
    )


# --- Dog Profile Endpoints ---


@router.get(
    "/dogs",
    response_model=list[DogProfileSchema],
    summary="List all dogs",
    description="Returns a list of all dog profiles in the database.",
)
async def list_dogs(
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> list[DogProfileSchema]:
    """List all dog profiles."""
    dogs = store.list_dogs()
    logger.debug("dogs_listed", count=len(dogs))
    return [_dog_to_schema(dog) for dog in dogs]


@router.post(
    "/dogs",
    response_model=DogProfileSchema,
    status_code=201,
    summary="Create a new dog profile",
    description="Creates a new dog profile with the given name and notes.",
)
async def create_dog(
    data: DogProfileCreateSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> DogProfileSchema:
    """Create a new dog profile."""
    dog = store.create_dog(name=data.name, notes=data.notes)
    logger.info("dog_created", dog_id=dog.id, name=dog.name)
    return _dog_to_schema(dog)


@router.get(
    "/dogs/{dog_id}",
    response_model=DogProfileSchema,
    summary="Get dog details",
    description="Returns detailed information about a specific dog profile.",
)
async def get_dog(
    dog_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> DogProfileSchema:
    """Get a dog profile by ID."""
    dog = store.get_dog(dog_id)
    if not dog:
        logger.warning("dog_not_found", dog_id=dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")
    return _dog_to_schema(dog)


@router.put(
    "/dogs/{dog_id}",
    response_model=DogProfileSchema,
    summary="Update dog profile",
    description="Updates an existing dog profile's name and/or notes.",
)
async def update_dog(
    dog_id: str,
    data: DogProfileUpdateSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> DogProfileSchema:
    """Update a dog profile."""
    dog = store.update_dog(dog_id, name=data.name, notes=data.notes)
    if not dog:
        logger.warning("dog_not_found_for_update", dog_id=dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")
    logger.info("dog_updated", dog_id=dog_id, name=data.name)
    return _dog_to_schema(dog)


@router.delete(
    "/dogs/{dog_id}",
    status_code=204,
    summary="Delete dog profile",
    description="Deletes a dog profile. Fingerprints linked to this dog will become untagged.",
)
async def delete_dog(
    dog_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> None:
    """Delete a dog profile."""
    deleted = store.delete_dog(dog_id)
    if not deleted:
        logger.warning("dog_not_found_for_delete", dog_id=dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")
    logger.info("dog_deleted", dog_id=dog_id)


@router.post(
    "/dogs/{dog_id}/merge/{other_id}",
    response_model=DogProfileSchema,
    summary="Merge two dog profiles",
    description="Merges another dog profile into this one. All barks from the other dog "
    "will be reassigned to this dog, and the other dog will be deleted.",
)
async def merge_dogs(
    dog_id: str,
    other_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> DogProfileSchema:
    """Merge two dog profiles.

    The other_id dog will be merged into dog_id, and other_id will be deleted.
    """
    if dog_id == other_id:
        raise HTTPException(status_code=400, detail="Cannot merge a dog with itself")

    # Verify both dogs exist
    target = store.get_dog(dog_id)
    if not target:
        logger.warning("merge_target_not_found", dog_id=dog_id)
        raise HTTPException(status_code=404, detail="Target dog not found")

    source = store.get_dog(other_id)
    if not source:
        logger.warning("merge_source_not_found", other_id=other_id)
        raise HTTPException(status_code=404, detail="Source dog not found")

    success = store.merge_dogs(source_id=other_id, target_id=dog_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to merge dogs")

    # Get the updated target dog
    merged = store.get_dog(dog_id)
    logger.info("dogs_merged", target_id=dog_id, source_id=other_id)
    return _dog_to_schema(merged)


@router.get(
    "/dogs/{dog_id}/barks",
    response_model=DogBarksListSchema,
    summary="Get barks for a dog",
    description="Returns a list of bark fingerprints attributed to a specific dog.",
)
async def get_dog_barks(
    dog_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> DogBarksListSchema:
    """Get bark fingerprints for a specific dog."""
    dog = store.get_dog(dog_id)
    if not dog:
        logger.warning("dog_not_found_for_barks", dog_id=dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")

    fingerprints = store.get_fingerprints_for_dog(dog_id, limit=limit)
    return DogBarksListSchema(
        dog_id=dog_id,
        dog_name=dog.name,
        count=len(fingerprints),
        total_barks=dog.total_barks,
        barks=[_fingerprint_to_schema(fp, dog.name) for fp in fingerprints],
    )


@router.post(
    "/dogs/{dog_id}/confirm",
    response_model=DogProfileSchema,
    summary="Confirm dog for auto-tagging",
    description="Confirms a dog so that new barks can be auto-tagged to it "
    "(once it has sufficient samples). The dog must be manually confirmed after "
    "enough barks have been manually tagged to build a reliable fingerprint.",
)
async def confirm_dog(
    dog_id: str,
    data: ConfirmDogRequestSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> DogProfileSchema:
    """Confirm a dog for auto-tagging."""
    dog = store.confirm_dog(dog_id, min_samples=data.min_samples)
    if not dog:
        logger.warning("dog_not_found_for_confirm", dog_id=dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")

    logger.info(
        "dog_confirmed",
        dog_id=dog_id,
        name=dog.name,
        min_samples=dog.min_samples_for_auto_tag,
        sample_count=dog.sample_count,
        can_auto_tag=dog.can_auto_tag(),
    )
    return _dog_to_schema(dog)


@router.post(
    "/dogs/{dog_id}/unconfirm",
    response_model=DogProfileSchema,
    summary="Remove confirmation from dog",
    description="Removes confirmation from a dog, disabling auto-tagging. "
    "Existing tagged barks are not affected.",
)
async def unconfirm_dog(
    dog_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> DogProfileSchema:
    """Remove confirmation from a dog."""
    dog = store.unconfirm_dog(dog_id)
    if not dog:
        logger.warning("dog_not_found_for_unconfirm", dog_id=dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")

    logger.info("dog_unconfirmed", dog_id=dog_id, name=dog.name)
    return _dog_to_schema(dog)


@router.post(
    "/dogs/{dog_id}/reset-embedding",
    response_model=DogProfileSchema,
    summary="Reset dog's acoustic embedding",
    description="Clears the dog's acoustic embedding to start fresh. Use this when a dog's "
    "profile has been contaminated with barks from other dogs. By default, also disables "
    "auto-tagging until the profile is manually confirmed again.",
)
async def reset_dog_embedding(
    dog_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
    unconfirm: Annotated[
        bool, Query(description="Also disable auto-tagging (default: true)")
    ] = True,
) -> DogProfileSchema:
    """Reset a dog's acoustic embedding to clear contamination."""
    dog = store.reset_dog_embedding(dog_id, unconfirm=unconfirm)
    if not dog:
        logger.warning("dog_not_found_for_reset", dog_id=dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")

    logger.info(
        "dog_embedding_reset",
        dog_id=dog_id,
        name=dog.name,
        unconfirmed=unconfirm,
    )
    return _dog_to_schema(dog)


# --- Bark Tagging Endpoints ---


@router.get(
    "/barks/untagged",
    response_model=UntaggedBarksListSchema,
    summary="List untagged barks",
    description="Returns a list of bark fingerprints that have not been tagged to any dog.",
)
async def list_untagged_barks(
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> UntaggedBarksListSchema:
    """List untagged bark fingerprints."""
    fingerprints = store.get_untagged_fingerprints(limit=limit)
    stats = store.get_stats()

    return UntaggedBarksListSchema(
        count=len(fingerprints),
        total_untagged=stats["untagged"],
        barks=[_fingerprint_to_schema(fp) for fp in fingerprints],
    )


@router.post(
    "/barks/{bark_id}/tag",
    response_model=BarkFingerprintSchema,
    summary="Tag bark to dog",
    description="Tags a bark fingerprint as belonging to a specific dog.",
)
async def tag_bark(
    bark_id: str,
    data: TagBarkRequestSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> BarkFingerprintSchema:
    """Tag a bark fingerprint to a dog."""
    # Verify the bark exists
    fingerprint = store.get_fingerprint(bark_id)
    if not fingerprint:
        logger.warning("bark_not_found_for_tag", bark_id=bark_id)
        raise HTTPException(status_code=404, detail="Bark fingerprint not found")

    # Verify the dog exists
    dog = store.get_dog(data.dog_id)
    if not dog:
        logger.warning("dog_not_found_for_tag", dog_id=data.dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")

    # Tag the fingerprint
    success = store.tag_fingerprint(bark_id, data.dog_id, data.confidence)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to tag bark")

    # Update dog stats if the fingerprint has an embedding
    if fingerprint.embedding is not None:
        store.update_dog_stats(data.dog_id, fingerprint.embedding, fingerprint.timestamp)

    # Get the updated fingerprint
    updated = store.get_fingerprint(bark_id)
    logger.info("bark_tagged", bark_id=bark_id, dog_id=data.dog_id, confidence=data.confidence)
    return _fingerprint_to_schema(updated, dog.name)


@router.post(
    "/barks/bulk-tag",
    response_model=BulkTagResultSchema,
    summary="Bulk tag barks",
    description="Tags multiple bark fingerprints to a single dog.",
)
async def bulk_tag_barks(
    data: BulkTagRequestSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> BulkTagResultSchema:
    """Tag multiple barks to a dog."""
    # Verify the dog exists
    dog = store.get_dog(data.dog_id)
    if not dog:
        logger.warning("dog_not_found_for_bulk_tag", dog_id=data.dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")

    tagged_count = 0
    failed_ids = []

    for bark_id in data.bark_ids:
        fingerprint = store.get_fingerprint(bark_id)
        if not fingerprint:
            failed_ids.append(bark_id)
            continue

        success = store.tag_fingerprint(bark_id, data.dog_id, data.confidence)
        if success:
            tagged_count += 1
            # Update dog stats if the fingerprint has an embedding
            if fingerprint.embedding is not None:
                store.update_dog_stats(data.dog_id, fingerprint.embedding, fingerprint.timestamp)
        else:
            failed_ids.append(bark_id)

    logger.info(
        "barks_bulk_tagged",
        dog_id=data.dog_id,
        tagged_count=tagged_count,
        failed_count=len(failed_ids),
    )

    return BulkTagResultSchema(
        tagged_count=tagged_count,
        failed_count=len(failed_ids),
        failed_ids=failed_ids,
    )


@router.post(
    "/barks/{bark_id}/correct",
    response_model=BarkFingerprintSchema,
    summary="Correct bark identification",
    description="Corrects a misidentified bark by reassigning it to a different dog.",
)
async def correct_bark(
    bark_id: str,
    data: CorrectBarkRequestSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> BarkFingerprintSchema:
    """Correct a misidentified bark."""
    # Verify the bark exists
    fingerprint = store.get_fingerprint(bark_id)
    if not fingerprint:
        logger.warning("bark_not_found_for_correction", bark_id=bark_id)
        raise HTTPException(status_code=404, detail="Bark fingerprint not found")

    # Verify the new dog exists
    new_dog = store.get_dog(data.new_dog_id)
    if not new_dog:
        logger.warning("dog_not_found_for_correction", dog_id=data.new_dog_id)
        raise HTTPException(status_code=404, detail="Dog not found")

    old_dog_id = fingerprint.dog_id

    # Re-tag the fingerprint to the new dog
    success = store.tag_fingerprint(bark_id, data.new_dog_id, data.confidence)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to correct bark identification")

    # Update the new dog's stats if the fingerprint has an embedding
    if fingerprint.embedding is not None:
        store.update_dog_stats(data.new_dog_id, fingerprint.embedding, fingerprint.timestamp)

    # Get the updated fingerprint
    updated = store.get_fingerprint(bark_id)
    logger.info(
        "bark_corrected",
        bark_id=bark_id,
        old_dog_id=old_dog_id,
        new_dog_id=data.new_dog_id,
        confidence=data.confidence,
    )
    return _fingerprint_to_schema(updated, new_dog.name)


@router.post(
    "/barks/{bark_id}/untag",
    response_model=BarkFingerprintSchema,
    summary="Untag bark",
    description="Removes the dog association from a bark, making it untagged again.",
)
async def untag_bark(
    bark_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> BarkFingerprintSchema:
    """Remove dog association from a bark."""
    # Verify the bark exists
    fingerprint = store.get_fingerprint(bark_id)
    if not fingerprint:
        logger.warning("bark_not_found_for_untag", bark_id=bark_id)
        raise HTTPException(status_code=404, detail="Bark fingerprint not found")

    old_dog_id = fingerprint.dog_id

    # Remove the dog association
    success = store.untag_fingerprint(bark_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to untag bark")

    # Get the updated fingerprint
    updated = store.get_fingerprint(bark_id)
    logger.info(
        "bark_untagged",
        bark_id=bark_id,
        old_dog_id=old_dog_id,
    )
    return _fingerprint_to_schema(updated)


@router.post(
    "/barks/{bark_id}/reject",
    response_model=BarkFingerprintSchema,
    summary="Reject bark as false positive",
    description="Marks a bark fingerprint as a false positive with a reason. "
    "Rejected barks are hidden from normal views but data is preserved.",
)
async def reject_bark(
    bark_id: str,
    data: RejectBarkRequestSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> BarkFingerprintSchema:
    """Mark a bark as a false positive."""
    # Verify the bark exists
    fingerprint = store.get_fingerprint(bark_id)
    if not fingerprint:
        logger.warning("bark_not_found_for_reject", bark_id=bark_id)
        raise HTTPException(status_code=404, detail="Bark fingerprint not found")

    # Reject the fingerprint
    success = store.reject_fingerprint(bark_id, data.reason)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reject bark")

    # Get the updated fingerprint
    updated = store.get_fingerprint(bark_id)
    logger.info(
        "bark_rejected",
        bark_id=bark_id,
        reason=data.reason,
    )
    return _fingerprint_to_schema(updated)


@router.post(
    "/barks/{bark_id}/unreject",
    response_model=BarkFingerprintSchema,
    summary="Remove rejection from bark",
    description="Removes the rejection status from a bark, making it visible again.",
)
async def unreject_bark(
    bark_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> BarkFingerprintSchema:
    """Remove rejection status from a bark."""
    # Verify the bark exists
    fingerprint = store.get_fingerprint(bark_id)
    if not fingerprint:
        logger.warning("bark_not_found_for_unreject", bark_id=bark_id)
        raise HTTPException(status_code=404, detail="Bark fingerprint not found")

    if not fingerprint.rejection_reason:
        raise HTTPException(status_code=400, detail="Bark is not rejected")

    # Remove the rejection
    success = store.unreject_fingerprint(bark_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to unreject bark")

    # Get the updated fingerprint
    updated = store.get_fingerprint(bark_id)
    logger.info("bark_unrejected", bark_id=bark_id)
    return _fingerprint_to_schema(updated)


@router.post(
    "/barks/{bark_id}/confirm",
    response_model=BarkFingerprintSchema,
    summary="Confirm bark as real",
    description="Confirms a bark fingerprint as a real bark (even if the dog is unknown). "
    "This distinguishes reviewed barks from unreviewed ones and clears any rejection.",
)
async def confirm_bark(
    bark_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> BarkFingerprintSchema:
    """Confirm a bark fingerprint as a real bark."""
    # Verify the bark exists
    fingerprint = store.get_fingerprint(bark_id)
    if not fingerprint:
        logger.warning("bark_not_found_for_confirm", bark_id=bark_id)
        raise HTTPException(status_code=404, detail="Bark fingerprint not found")

    # Confirm the fingerprint
    success = store.confirm_fingerprint(bark_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to confirm bark")

    # Get the updated fingerprint
    updated = store.get_fingerprint(bark_id)
    logger.info("bark_confirmed", bark_id=bark_id)
    return _fingerprint_to_schema(updated)


@router.post(
    "/barks/{bark_id}/unconfirm",
    response_model=BarkFingerprintSchema,
    summary="Remove confirmation from bark",
    description="Removes the confirmation status from a bark, returning it to unreviewed state.",
)
async def unconfirm_bark(
    bark_id: str,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> BarkFingerprintSchema:
    """Remove confirmation status from a bark."""
    # Verify the bark exists
    fingerprint = store.get_fingerprint(bark_id)
    if not fingerprint:
        logger.warning("bark_not_found_for_unconfirm", bark_id=bark_id)
        raise HTTPException(status_code=404, detail="Bark fingerprint not found")

    if fingerprint.confirmed is None:
        raise HTTPException(status_code=400, detail="Bark is not confirmed")

    # Remove the confirmation
    success = store.unconfirm_fingerprint(bark_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to unconfirm bark")

    # Get the updated fingerprint
    updated = store.get_fingerprint(bark_id)
    logger.info("bark_unconfirmed", bark_id=bark_id)
    return _fingerprint_to_schema(updated)


# --- Fingerprint Explorer Endpoints ---


@router.get(
    "/fingerprints",
    response_model=FingerprintListSchema,
    summary="List fingerprints with filtering",
    description="Returns a paginated list of fingerprints with optional filtering by dog, "
    "tagged status, rejection status, confidence, and date range.",
)
async def list_fingerprints(
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    dog_id: Annotated[str | None, Query(description="Filter by dog ID")] = None,
    tagged: Annotated[bool | None, Query(description="Filter by tagged status")] = None,
    rejected: Annotated[
        bool | None, Query(description="Filter by rejection status (True=rejected only, False=not rejected, None=all)")
    ] = None,
    min_confidence: Annotated[
        float | None, Query(ge=0.0, le=1.0, description="Minimum match confidence")
    ] = None,
    start_date: Annotated[
        datetime | None, Query(description="Filter by timestamp >= start_date")
    ] = None,
    end_date: Annotated[
        datetime | None, Query(description="Filter by timestamp <= end_date")
    ] = None,
) -> FingerprintListSchema:
    """List fingerprints with filtering and pagination."""
    fingerprints, total = store.list_fingerprints(
        limit=limit,
        offset=offset,
        dog_id=dog_id,
        tagged=tagged,
        min_confidence=min_confidence,
        start_date=start_date,
        end_date=end_date,
        rejected=rejected,
    )

    # Build a map of dog_id -> dog_name for tagged fingerprints
    dog_names: dict[str, str] = {}
    for fp in fingerprints:
        if fp.dog_id and fp.dog_id not in dog_names:
            dog = store.get_dog(fp.dog_id)
            if dog:
                dog_names[fp.dog_id] = dog.name

    items = [
        _fingerprint_to_schema(fp, dog_names.get(fp.dog_id) if fp.dog_id else None)
        for fp in fingerprints
    ]

    logger.debug(
        "fingerprints_listed",
        count=len(items),
        total=total,
        limit=limit,
        offset=offset,
    )

    return FingerprintListSchema(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/fingerprints/aggregates",
    response_model=FingerprintAggregatesSchema,
    summary="Get per-dog acoustic statistics",
    description="Returns aggregate acoustic statistics (pitch, duration, spectral centroid) "
    "for each dog in the database.",
)
async def get_fingerprint_aggregates(
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> FingerprintAggregatesSchema:
    """Get aggregate acoustic statistics per dog."""
    aggregates = store.get_dog_acoustic_aggregates()

    dogs = [
        DogAcousticStatsSchema(
            dog_id=agg["dog_id"],
            dog_name=agg["dog_name"],
            avg_pitch_hz=agg["avg_pitch_hz"],
            min_pitch_hz=agg["min_pitch_hz"],
            max_pitch_hz=agg["max_pitch_hz"],
            avg_duration_ms=agg["avg_duration_ms"],
            min_duration_ms=agg["min_duration_ms"],
            max_duration_ms=agg["max_duration_ms"],
            avg_spectral_centroid_hz=agg["avg_spectral_centroid_hz"],
            total_barks=agg["total_barks"],
            first_seen=agg["first_seen"],
            last_seen=agg["last_seen"],
        )
        for agg in aggregates
    ]

    logger.debug("fingerprint_aggregates_retrieved", dog_count=len(dogs))

    return FingerprintAggregatesSchema(dogs=dogs)


# --- Stats Endpoints ---


@router.get(
    "/fingerprints/stats",
    response_model=FingerprintStatsSchema,
    summary="Get fingerprint statistics",
    description="Returns summary statistics about the fingerprint database.",
)
async def get_fingerprint_stats(
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> FingerprintStatsSchema:
    """Get fingerprint database statistics."""
    stats = store.get_stats()
    logger.debug("fingerprint_stats_retrieved", **stats)
    return FingerprintStatsSchema(**stats)


# --- Clustering Endpoints ---


def _cluster_to_schema(
    suggestion: ClusterSuggestion,
    sample_ids: list[str] | None = None,
) -> ClusterSuggestionSchema:
    """Convert ClusterSuggestion to API schema."""
    return ClusterSuggestionSchema(
        cluster_id=suggestion.cluster_id,
        fingerprint_ids=suggestion.fingerprint_ids,
        size=suggestion.size,
        avg_pitch_hz=suggestion.avg_pitch_hz,
        avg_duration_ms=suggestion.avg_duration_ms,
        first_seen=suggestion.first_seen,
        last_seen=suggestion.last_seen,
        coherence_score=suggestion.coherence_score,
        sample_ids=sample_ids or [],
    )


@router.post(
    "/fingerprints/cluster",
    response_model=ClusterResultSchema,
    summary="Cluster untagged barks",
    description="Runs HDBSCAN clustering on untagged fingerprints to identify "
    "potential dog profiles. Returns cluster suggestions that can be reviewed "
    "and converted to dog profiles. Requires the 'hdbscan' package to be installed.",
)
async def cluster_untagged_barks(
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
    min_cluster_size: Annotated[
        int, Query(ge=2, le=20, description="Minimum barks to form a cluster")
    ] = 3,
    max_fingerprints: Annotated[
        int, Query(ge=10, le=5000, description="Maximum fingerprints to process")
    ] = 1000,
) -> ClusterResultSchema:
    """Cluster untagged barks to suggest new dog profiles."""
    if not is_clustering_available():
        raise HTTPException(
            status_code=501,
            detail="Clustering requires the hdbscan package. "
            "Install with: pip install woofalytics[clustering]",
        )

    try:
        clusterer = create_clusterer(store, min_cluster_size=min_cluster_size)
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    suggestions = clusterer.cluster_untagged(max_fingerprints=max_fingerprints)

    # Get representative samples for each cluster
    suggestion_schemas = []
    for s in suggestions:
        sample_ids = clusterer.get_cluster_samples(s, count=3)
        suggestion_schemas.append(_cluster_to_schema(s, sample_ids))

    # Calculate noise count
    stats = store.get_stats()
    total_untagged = min(stats["untagged"], max_fingerprints)
    clustered_count = sum(s.size for s in suggestions)
    noise_count = total_untagged - clustered_count

    logger.info(
        "clustering_completed",
        cluster_count=len(suggestions),
        total_processed=total_untagged,
        clustered_count=clustered_count,
        noise_count=noise_count,
    )

    return ClusterResultSchema(
        cluster_count=len(suggestions),
        total_untagged=total_untagged,
        noise_count=max(0, noise_count),
        suggestions=suggestion_schemas,
    )


@router.post(
    "/fingerprints/cluster/{cluster_id}/create-dog",
    response_model=DogProfileSchema,
    status_code=201,
    summary="Create dog from cluster",
    description="Creates a new dog profile from a previously identified cluster. "
    "All fingerprints in the cluster will be tagged to the new dog. The cluster "
    "must be re-fetched if clustering has been run again.",
)
async def create_dog_from_cluster(
    cluster_id: str,
    data: CreateDogFromClusterRequestSchema,
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
    min_cluster_size: Annotated[
        int, Query(ge=2, le=20, description="Minimum barks to form a cluster")
    ] = 3,
) -> DogProfileSchema:
    """Create a dog profile from a cluster suggestion."""
    if not is_clustering_available():
        raise HTTPException(
            status_code=501,
            detail="Clustering requires the hdbscan package. "
            "Install with: pip install woofalytics[clustering]",
        )

    try:
        clusterer = create_clusterer(store, min_cluster_size=min_cluster_size)
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    # Re-run clustering to get the cluster data
    # (Clusters are ephemeral - they exist only during clustering)
    suggestions = clusterer.cluster_untagged()

    # Find the requested cluster
    target: ClusterSuggestion | None = None
    for s in suggestions:
        if s.cluster_id == cluster_id:
            target = s
            break

    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Cluster '{cluster_id}' not found. "
            "Clusters may have changed since last query. "
            "Run clustering again to get updated clusters.",
        )

    # Create the dog from the cluster
    dog_id = clusterer.create_dog_from_cluster(target, name=data.name, notes=data.notes)

    # Get the created dog
    dog = store.get_dog(dog_id)
    if not dog:
        raise HTTPException(status_code=500, detail="Failed to retrieve created dog")

    logger.info(
        "dog_created_from_cluster",
        dog_id=dog_id,
        dog_name=data.name,
        cluster_id=cluster_id,
        fingerprint_count=target.size,
    )

    return _dog_to_schema(dog)


@router.post(
    "/fingerprints/purge-without-evidence",
    response_model=PurgeResultSchema,
    summary="Purge fingerprints without audio evidence",
    description="Deletes all untagged fingerprints that have no associated audio "
    "evidence file. These fingerprints cannot be verified or used for clustering.",
)
async def purge_fingerprints_without_evidence(
    store: Annotated[FingerprintStore, Depends(get_fingerprint_store)],
) -> PurgeResultSchema:
    """Purge untagged fingerprints that have no audio evidence."""
    deleted = store.purge_fingerprints(untagged_only=True, without_evidence=True)

    logger.info(
        "fingerprints_purged_without_evidence",
        deleted_count=deleted,
    )

    return PurgeResultSchema(
        deleted_count=deleted,
        message=f"Deleted {deleted} untagged fingerprints without audio evidence",
    )

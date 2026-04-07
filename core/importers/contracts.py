from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum


class DonorTrust(str, Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class SupportedArtifactContract:
    artifact_key: str
    path_hint: str
    format: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    target_families: tuple[str, ...]
    write_paths: tuple[str, ...]
    notes: str


@dataclass(frozen=True, slots=True)
class DonorImporterContract:
    donor_key: str
    donor_owner: str
    target_owner: str
    trust_level: DonorTrust
    input_only: bool
    supported_artifacts: tuple[SupportedArtifactContract, ...]
    forbidden_runtime_dependencies: tuple[str, ...]
    notes: str


@dataclass(frozen=True, slots=True)
class ImportedObjectRecord:
    family: str
    object_id: str
    revision_id: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class ImportRunResult:
    donor_key: str
    ingest_run_id: str
    import_record_id: str
    project_id: str
    imported_objects: tuple[ImportedObjectRecord, ...]


def new_ingest_run_id(donor_key: str) -> str:
    slug = donor_key.replace("/", "_").replace(":", "_").replace("-", "_")
    return f"ing_{slug}_{uuid.uuid4().hex[:12]}"


__all__ = [
    "DonorImporterContract",
    "DonorTrust",
    "ImportRunResult",
    "ImportedObjectRecord",
    "SupportedArtifactContract",
    "new_ingest_run_id",
]

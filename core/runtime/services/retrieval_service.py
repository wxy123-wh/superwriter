"""Retrieval service for search and indexing operations."""

from __future__ import annotations

from typing import TypeAlias, cast

from core.retrieval import (
    RetrievalSourceRecord,
    build_indexed_documents,
    build_support_documents,
    rank_support_documents,
    scope_consistency_stamp,
)
from core.runtime.storage import (
    CanonicalStorage,
    JSONValue,
    MetadataMarkerInput,
    MetadataMarkerSnapshot,
)
from core.runtime.types import (
    ReadObjectRequest,
    RetrievalRebuildRequest,
    RetrievalRebuildResult,
    RetrievalMatchSnapshot,
    RetrievalSearchRequest,
    RetrievalSearchResult,
    RetrievalStatusSnapshot,
    WorkspaceObjectSummary,
)

JSONObject: TypeAlias = dict[str, JSONValue]


class RetrievalService:
    """Service for managing retrieval support and search operations."""

    def __init__(self, storage: CanonicalStorage):
        self.__storage = storage

    def get_retrieval_status(
        self,
        project_id: str,
        novel_id: str | None,
        workspace_canonical_objects: tuple[WorkspaceObjectSummary, ...],
        read_object_func,
    ) -> RetrievalStatusSnapshot:
        """Get the current retrieval status for a scope."""
        scope_family, scope_object_id = self.retrieval_scope(project_id, novel_id)
        sources = self.retrieval_sources(workspace_canonical_objects, read_object_func)
        current_stamp = scope_consistency_stamp(sources)
        document_markers = self.retrieval_document_markers(project_id, novel_id)
        status_marker = self._latest_retrieval_status_marker(
            scope_family=scope_family, scope_object_id=scope_object_id
        )
        degraded = status_marker is None or self._payload_text_value(
            status_marker.payload, "build_consistency_stamp"
        ) != current_stamp
        warnings: list[str] = []
        if status_marker is None:
            warnings.append("Retrieval index not built yet.")
        elif degraded:
            warnings.append("Retrieval index is stale.")
        return self.retrieval_status_snapshot(
            scope_family=scope_family,
            scope_object_id=scope_object_id,
            current_stamp=current_stamp,
            document_markers=document_markers,
            status_marker=status_marker,
            degraded=degraded,
            warnings=tuple(warnings),
        )

    def rebuild_retrieval_support(
        self,
        request: RetrievalRebuildRequest,
        workspace_canonical_objects: tuple[WorkspaceObjectSummary, ...],
        read_object_func,
    ) -> RetrievalRebuildResult:
        """Rebuild retrieval support documents for a scope."""
        scope_family, scope_object_id = self.retrieval_scope(request.project_id, request.novel_id)
        scope_read = read_object_func(ReadObjectRequest(family=scope_family, object_id=scope_object_id))
        if scope_read.head is None:
            raise KeyError(f"{scope_family}:{scope_object_id}")

        sources = self.retrieval_sources(workspace_canonical_objects, read_object_func)
        documents, report = build_support_documents(
            sources,
            scope_project_id=request.project_id,
            scope_novel_id=request.novel_id,
        )

        replaced_marker_count = self.__storage.delete_metadata_markers(
            marker_name="retrieval_status",
            target_family=scope_family,
            target_object_id=scope_object_id,
        )
        for source in sources:
            replaced_marker_count += self.__storage.delete_metadata_markers(
                marker_name="retrieval_document",
                target_family=source.family,
                target_object_id=source.object_id,
            )

        for document in documents:
            _ = self.__storage.create_metadata_marker(
                MetadataMarkerInput(
                    target_family=document.target_family,
                    target_object_id=document.target_object_id,
                    target_revision_id=document.target_revision_id,
                    marker_name="retrieval_document",
                    created_by=request.actor,
                    marker_payload=document.marker_payload,
                )
            )

        status_payload: JSONObject = {
            "project_id": request.project_id,
            "novel_id": request.novel_id,
            "support_only": True,
            "rebuildable": True,
            "source_kind": "canonical_objects_and_revisions",
            "build_consistency_stamp": report.build_consistency_stamp,
            "indexed_object_count": report.canonical_object_count,
            "indexed_revision_count": report.canonical_revision_count,
            "warning_count": report.warning_count,
            "warnings": list(report.warnings),
        }
        _ = self.__storage.create_metadata_marker(
            MetadataMarkerInput(
                target_family=scope_family,
                target_object_id=scope_object_id,
                target_revision_id=scope_read.head.current_revision_id,
                marker_name="retrieval_status",
                created_by=request.actor,
                marker_payload=status_payload,
            )
        )
        status = RetrievalStatusSnapshot(
            scope_family=scope_family,
            scope_object_id=scope_object_id,
            support_only=True,
            rebuildable=True,
            build_consistency_stamp=report.build_consistency_stamp,
            indexed_object_count=report.canonical_object_count,
            indexed_revision_count=report.canonical_revision_count,
            degraded=False,
            warnings=report.warnings,
        )
        return RetrievalRebuildResult(
            status=status,
            document_count=len(documents),
            replaced_marker_count=replaced_marker_count,
            warnings=report.warnings,
        )

    def search_retrieval_support(
        self,
        request: RetrievalSearchRequest,
        workspace_canonical_objects: tuple[WorkspaceObjectSummary, ...],
        read_object_func,
    ) -> RetrievalSearchResult:
        """Search retrieval support documents."""
        scope_family, scope_object_id = self.retrieval_scope(request.project_id, request.novel_id)
        sources = self.retrieval_sources(workspace_canonical_objects, read_object_func)
        current_revision_ids = {source.object_id: source.revision_id for source in sources}
        current_stamp = scope_consistency_stamp(sources)

        document_markers = self.retrieval_document_markers(request.project_id, request.novel_id)
        indexed_documents = build_indexed_documents(tuple(marker.payload for marker in document_markers))
        ranked_documents = rank_support_documents(request.query, indexed_documents)

        warnings: list[str] = []
        review_hints: list[str] = []
        degraded = False
        status_marker = self._latest_retrieval_status_marker(scope_family=scope_family, scope_object_id=scope_object_id)
        if status_marker is None:
            degraded = True
            warnings.append("Retrieval support status is missing; rankings are advisory until a rebuild runs.")
        else:
            status_stamp = self._payload_text_value(status_marker.payload, "build_consistency_stamp")
            if status_stamp != current_stamp:
                degraded = True
                warnings.append(
                    "Retrieval support is stale relative to canonical revisions; rankings were downgraded instead of mutating canonical state."
                )
        if not document_markers:
            degraded = True
            warnings.append("Retrieval support documents are missing for this scope; authoring remains available while rebuild catches up.")

        match_rows: list[tuple[float, RetrievalMatchSnapshot]] = []
        for ranked_document in ranked_documents:
            current_revision_id = current_revision_ids.get(ranked_document.target_object_id)
            if current_revision_id is None:
                continue
            match_warnings: list[str] = []
            match_review_hints: list[str] = []
            adjusted_score = ranked_document.score
            if degraded:
                adjusted_score *= 0.75
            if current_revision_id != ranked_document.target_revision_id:
                degraded = True
                adjusted_score *= 0.5
                stale_warning = (
                    f"retrieval snapshot for {ranked_document.target_family}:{ranked_document.target_object_id} is stale against canonical revision {current_revision_id}"
                )
                match_warnings.append(stale_warning)
                warnings.append(stale_warning)
                match_review_hints.append("Verify the current canonical revision before acting on this retrieval match.")
            ranking_metadata = dict(ranked_document.ranking_metadata)
            ranking_metadata.update(
                {
                    "support_only": True,
                    "rebuildable": True,
                    "adjusted_score": adjusted_score,
                    "current_revision_id": current_revision_id,
                }
            )
            match_rows.append(
                (
                    adjusted_score,
                    RetrievalMatchSnapshot(
                        target_family=ranked_document.target_family,
                        target_object_id=ranked_document.target_object_id,
                        target_revision_id=ranked_document.target_revision_id,
                        score=adjusted_score,
                        summary_text=ranked_document.summary_text,
                        ranking_reasons=ranked_document.ranking_reasons,
                        warnings=tuple(match_warnings),
                        review_hints=tuple(match_review_hints),
                        ranking_metadata=ranking_metadata,
                    ),
                )
            )

        match_rows.sort(key=lambda item: (-item[0], item[1].target_family, item[1].target_object_id))
        limited_matches = [row[1] for row in match_rows[: max(1, request.limit)]]
        if len(limited_matches) >= 2:
            top_score = limited_matches[0].score
            second_score = limited_matches[1].score
            if top_score > 0 and abs(top_score - second_score) <= 10:
                degraded = True
                conflict_warning = (
                    f"Retrieval conflict: {limited_matches[0].target_object_id} and {limited_matches[1].target_object_id} ranked too closely to trust without review."
                )
                warnings.append(conflict_warning)
                review_hints.append("Verify both top retrieval matches against canonical revisions before applying any world-state change.")
                enriched_matches: list[RetrievalMatchSnapshot] = []
                for index, match in enumerate(limited_matches):
                    if index < 2:
                        metadata = dict(match.ranking_metadata)
                        metadata["conflict_penalty"] = 0.9
                        enriched_matches.append(
                            RetrievalMatchSnapshot(
                                target_family=match.target_family,
                                target_object_id=match.target_object_id,
                                target_revision_id=match.target_revision_id,
                                score=match.score * 0.9,
                                summary_text=match.summary_text,
                                ranking_reasons=match.ranking_reasons,
                                warnings=match.warnings + (conflict_warning,),
                                review_hints=match.review_hints + (
                                    "Conflicting support-only recall detected; route any consequential change through review-minded verification.",
                                ),
                                ranking_metadata=metadata,
                            )
                        )
                    else:
                        enriched_matches.append(match)
                limited_matches = sorted(
                    enriched_matches,
                    key=lambda item: (-item.score, item.target_family, item.target_object_id),
                )

        status = self.retrieval_status_snapshot(
            scope_family=scope_family,
            scope_object_id=scope_object_id,
            current_stamp=current_stamp,
            document_markers=document_markers,
            status_marker=status_marker,
            degraded=degraded,
            warnings=tuple(dict.fromkeys(warnings)),
        )
        return RetrievalSearchResult(
            status=status,
            matches=tuple(limited_matches),
            warnings=tuple(dict.fromkeys(warnings)),
            review_hints=tuple(dict.fromkeys(review_hints)),
        )

    def retrieval_scope(self, project_id: str, novel_id: str | None) -> tuple[str, str]:
        """Determine the retrieval scope family and object ID."""
        if novel_id is not None:
            return ("novel", novel_id)
        return ("project", project_id)

    def retrieval_sources(
        self,
        canonical_objects: tuple[WorkspaceObjectSummary, ...],
        read_object_func,
    ) -> tuple[RetrievalSourceRecord, ...]:
        """Build retrieval source records from canonical objects."""
        sources: list[RetrievalSourceRecord] = []
        for summary in canonical_objects:
            revisions = read_object_func(
                ReadObjectRequest(
                    family=summary.family,
                    object_id=summary.object_id,
                    include_revisions=True,
                )
            ).revisions
            sources.append(
                RetrievalSourceRecord(
                    family=summary.family,
                    object_id=summary.object_id,
                    revision_id=summary.current_revision_id,
                    revision_number=summary.current_revision_number,
                    project_id=self._payload_text_value(summary.payload, "project_id"),
                    novel_id=self._payload_text_value(summary.payload, "novel_id"),
                    payload=summary.payload,
                    revision_count=max(1, len(revisions)),
                )
            )
        return tuple(sources)

    def retrieval_document_markers(
        self,
        project_id: str,
        novel_id: str | None,
    ) -> tuple[MetadataMarkerSnapshot, ...]:
        """Fetch retrieval document markers for a scope."""
        markers = self.__storage.fetch_metadata_markers(marker_name="retrieval_document")
        filtered: list[MetadataMarkerSnapshot] = []
        for marker in markers:
            marker_project_id = self._payload_text_value(marker.payload, "project_id")
            marker_novel_id = self._payload_text_value(marker.payload, "novel_id")
            if marker_project_id != project_id:
                continue
            if novel_id is not None and marker_novel_id != novel_id:
                continue
            filtered.append(marker)
        return tuple(filtered)

    def retrieval_status_snapshot(
        self,
        *,
        scope_family: str,
        scope_object_id: str,
        current_stamp: str,
        document_markers: tuple[MetadataMarkerSnapshot, ...],
        status_marker: MetadataMarkerSnapshot | None,
        degraded: bool,
        warnings: tuple[str, ...],
    ) -> RetrievalStatusSnapshot:
        """Build a retrieval status snapshot."""
        indexed_object_count = len(document_markers)
        indexed_revision_count = sum(
            cast(int, marker.payload["revision_count"])
            for marker in document_markers
            if isinstance(marker.payload.get("revision_count"), int) and not isinstance(marker.payload.get("revision_count"), bool)
        )
        if status_marker is None:
            return RetrievalStatusSnapshot(
                scope_family=scope_family,
                scope_object_id=scope_object_id,
                support_only=True,
                rebuildable=True,
                build_consistency_stamp=current_stamp,
                indexed_object_count=indexed_object_count,
                indexed_revision_count=indexed_revision_count,
                degraded=True,
                warnings=warnings,
            )
        return RetrievalStatusSnapshot(
            scope_family=scope_family,
            scope_object_id=scope_object_id,
            support_only=bool(status_marker.payload.get("support_only", True)),
            rebuildable=bool(status_marker.payload.get("rebuildable", True)),
            build_consistency_stamp=self._payload_text_value(status_marker.payload, "build_consistency_stamp") or current_stamp,
            indexed_object_count=self._payload_int_value(status_marker.payload, "indexed_object_count", indexed_object_count),
            indexed_revision_count=self._payload_int_value(status_marker.payload, "indexed_revision_count", indexed_revision_count),
            degraded=degraded,
            warnings=warnings,
        )

    def _latest_retrieval_status_marker(
        self,
        *,
        scope_family: str,
        scope_object_id: str,
    ) -> MetadataMarkerSnapshot | None:
        """Fetch the latest retrieval status marker for a scope."""
        markers = self.__storage.fetch_metadata_markers(
            marker_name="retrieval_status",
            target_family=scope_family,
            target_object_id=scope_object_id,
        )
        return markers[-1] if markers else None

    def _payload_text_value(self, payload: JSONObject, key: str) -> str | None:
        """Extract a text value from a payload."""
        value = payload.get(key)
        if isinstance(value, str):
            return value
        return None

    def _payload_int_value(self, payload: JSONObject, key: str, default: int) -> int:
        """Extract an integer value from a payload."""
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return default

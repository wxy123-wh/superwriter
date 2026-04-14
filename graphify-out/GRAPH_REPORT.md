# Graph Report - .  (2026-04-09)

## Corpus Check
- 146 files · ~89,497 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1880 nodes · 5857 edges · 78 communities detected
- Extraction: 32% EXTRACTED · 68% INFERRED · 0% AMBIGUOUS · INFERRED: 3980 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `DialogueProcessor` - 165 edges
2. `PipelineGenerationService` - 143 edges
3. `SuperwriterApplicationService` - 142 edges
4. `IntelligentDiagnoser` - 139 edges
5. `DialogueRequest` - 138 edges
6. `WorkspaceService` - 130 edges
7. `MutationPolicyEngine` - 129 edges
8. `DiagnosisRequest` - 128 edges
9. `AIProviderError` - 127 edges
10. `MutationPolicyClass` - 123 edges

## Surprising Connections (you probably didn't know these)
- `Novel Creation System Product` --conceptually_related_to--> `SuperWriter App Icon (T-shaped letterform)`  [INFERRED]
  项目蓝图.md → apps/frontend/public/favicon.svg
- `DiagnosisRequest` --uses--> `ReadObjectRequest`  [INFERRED]
  core\ai\diagnosis.py → core\runtime\application_services.py
- `DiagnosisRequest` --uses--> `SuperwriterApplicationService`  [INFERRED]
  core\ai\diagnosis.py → core\runtime\application_services.py
- `IntelligentDiagnoser` --uses--> `ReadObjectRequest`  [INFERRED]
  core\ai\diagnosis.py → core\runtime\application_services.py
- `IntelligentDiagnoser` --uses--> `SuperwriterApplicationService`  [INFERRED]
  core\ai\diagnosis.py → core\runtime\application_services.py

## Communities

### Community 0 - "Application Services Core"
Cohesion: 0.1
Nodes (176): _AppliedReviewMutation, CandidateDraftSnapshot, CandidateSelectionRequest, CandidateSelectionResult, CanonicalObjectSnapshot, CanonicalRevisionSnapshot, ChatMessageRequest, ChatMessageSnapshot (+168 more)

### Community 1 - "Partial Revision Engine"
Cohesion: 0.04
Nodes (104): PartialModificationResult, PartialModifier, Partial modifier for workbench iteration.  This module provides the ability to m, Result of a partial modification operation., Handles partial modification of generated content.      This class provides:, Initialize the partial modifier.          Args:             ai_client: Optional, Parse a section target from user feedback.          Args:             feedback:, Convert Chinese numbers to integers.          Args:             text: Chinese nu (+96 more)

### Community 2 - "Frontend App Shell"
Cohesion: 0.02
Nodes (48): ApiContractError, ApiResponseError, assertRecord(), buildUrl(), expectArray(), expectBoolean(), expectJsonObject(), expectNullableString() (+40 more)

### Community 3 - "Object Diff & Policy"
Cohesion: 0.05
Nodes (17): _build_object_diff(), _candidate_string_list(), _import_object_result(), _non_empty_candidate_text(), _payload_text(), ReadObjectRequest, SuperwriterApplicationService, event_to_scene_candidates() (+9 more)

### Community 4 - "Family Contract Registry"
Cohesion: 0.03
Nodes (63): _canonical_family(), _family(), FamilyCategory, FamilyContract, get_family_contract_from_registry(), IdContract, _provenance_fields(), ProvenanceField (+55 more)

### Community 5 - "Dialogue Context"
Cohesion: 0.05
Nodes (73): ContextScope, ContextUpdate, DialogueContext, DialogueContextManager, DialogueTurnRecord, Dialogue context management for multi-turn conversations.  This module provides, Initialize the context manager.          Args:             storage: CanonicalSto, Create a new dialogue context.          Args:             session_id: Unique ses (+65 more)

### Community 6 - "API Server & Command Center"
Cohesion: 0.05
Nodes (43): ApiResponse, _bool_from_optional_value(), _bool_from_value(), CommandCenterAuditEntry, CommandCenterRoute, CommandCenterSignal, CommandCenterSnapshot, _error_message() (+35 more)

### Community 7 - "Candidate Comparison"
Cohesion: 0.09
Nodes (49): CandidateComparison, CandidateVersion, ComparisonBuilder, DiffSegment, Candidate comparison for Review Desk.  This module provides the ability to compa, Convert a draft dict to CandidateVersion., Build a diff between two candidate versions., Determine which candidate to recommend.          Strategy:         1. If any can (+41 more)

### Community 8 - "Comment Management"
Cohesion: 0.07
Nodes (43): CommentInput, CommentManager, CommentStatus, CommentThread, ProposalComment, Comment system for Review Desk.  This module provides the ability to add comment, Get a specific comment.          Args:             comment_id: The comment ID, List all comments for a proposal.          Args:             proposal_id: The pr (+35 more)

### Community 9 - "Donor Import Contracts"
Cohesion: 0.05
Nodes (57): DonorImporterContract, DonorTrust, ImportRunResult, SupportedArtifactContract, CharacterExportImportData, CharacterExportImportRow, load_character_export_import_data(), _read_rows() (+49 more)

### Community 10 - "AI Dialogue Engine"
Cohesion: 0.05
Nodes (32): DialogueResponse, DialogueState, DialogueStateMachine, IntentClassification, Reset a session to IDLE state., Check if a session is in IDLE state., Response from processing a dialogue turn., Result of intent classification. (+24 more)

### Community 11 - "Canonical Storage Layer"
Cohesion: 0.04
Nodes (29): _CanonicalMixin, _ChatMixin, _DerivedMixin, _ImportsMixin, _MetadataMixin, _ProposalsMixin, List all comments for a proposal., Mark a comment as resolved. (+21 more)

### Community 12 - "Skill Type Tests"
Cohesion: 0.08
Nodes (23): _base_payload(), Tests for expanded skill type support., Existing payloads with style_rule should validate unchanged., Build a minimal valid skill payload., TestBackwardCompatibility, TestCharacterVoiceValidation, TestDialogueStyleValidation, TestNarrativeModeValidation (+15 more)

### Community 13 - "Proposal & Audit Trail"
Cohesion: 0.09
Nodes (20): AuditEntry, Status of a revision request., Create a revision request, typically when a proposal is rejected., Get a revision request by ID., List all revision requests for a proposal., Mark a revision request as addressed., Record an audit entry for a proposal., Get the full audit trail for a proposal, ordered chronologically. (+12 more)

### Community 14 - "App Service Integration Tests"
Cohesion: 0.1
Nodes (12): SuperwriterApplicationService, _ChatGenerationService, _seed_basic_pipeline_objects(), _seed_pipeline_workspace(), _StubAIProvider, _StubbedService, test_additional_generated_plot_nodes_also_receive_nonblank_fallbacks(), test_outline_generation_falls_back_when_ai_returns_blank_strings() (+4 more)

### Community 15 - "AI Diagnosis"
Cohesion: 0.1
Nodes (15): DiagnosisIssue, DiagnosisReport, _merge_issues(), Build a serializable workspace summary for AI analysis., Use AI to analyze narrative structure, pacing, and gaps., Use AI to cross-validate characters, settings, and established facts., Analyze the structural integrity of the project., Check for consistency issues in the project. (+7 more)

### Community 16 - "Candidate Scoring"
Cohesion: 0.12
Nodes (16): CandidateScoreDetail, CandidateScorer, Candidate scorer for Review Desk multi-candidate selection.  Ported from fanbian, Score all candidates and return them ranked best-first.          Each candidate, Token overlap between content and outline., Fraction of expected character names that appear in content., Heuristic literary quality based on structural signals.          Bonuses:, Detailed breakdown of a candidate's quality scores. (+8 more)

### Community 17 - "Product Design Concepts"
Cohesion: 0.11
Nodes (25): AI Role (Expansion & Production), Author Role (Direction & Approval), 全书总控台 (Book Command Center), Core Creative Objects, Outline to Plot Transformation, 流水线工作台 (Pipeline Workbench), Novel Creation System Product, Product Boundary Constraints (+17 more)

### Community 18 - "AI Prompt Builders"
Cohesion: 0.16
Nodes (23): build_chapter_revision_prompt(), build_consistency_check_prompt(), build_diagnosis_prompt(), build_event_to_scene_prompt(), build_outline_to_plot_prompt(), build_partial_revision_prompt(), build_plot_to_event_prompt(), build_quality_score_prompt() (+15 more)

### Community 19 - "Workbench Session Storage"
Cohesion: 0.08
Nodes (12): Update the status of a workbench session., Increment the iteration counter for a session and return the new value., Create a new candidate draft for a workbench session., Get a candidate draft by ID., List candidate drafts for a session., Mark a candidate draft as selected (deselects others in the same session)., Create a feedback record for a candidate draft., Create a new workbench iteration session. (+4 more)

### Community 20 - "AI Provider Client"
Cohesion: 0.1
Nodes (14): AIProviderClient, AIProviderConfig, AIProviderTestResult, ProviderValidationError, Generate a completion from the AI provider.          Args:             messages:, Configuration for an AI provider using OpenAI-compatible API., Generate structured JSON output from the AI provider.          Args:, Test the provider connection with a simple request. (+6 more)

### Community 21 - "File Store"
Cohesion: 0.13
Nodes (10): FileStore, from_file_name(), NodeAddress, List all nodes in a layer, optionally filtered by parent coords., List direct children of a node., Return the next available sequence number under the given parent., Return (address, content) for all nodes in the first four layers., Node address, e.g. NodeAddress('outline', ('1',)) or NodeAddress('plot', ('1', ' (+2 more)

### Community 22 - "Scene-to-Chapter Service"
Cohesion: 0.16
Nodes (4): _build_object_diff(), _candidate_string_list(), _non_empty_candidate_text(), _payload_text()

### Community 23 - "Storage Engine"
Cohesion: 0.13
Nodes (10): _CanonicalMixin, _ChatMixin, _DerivedMixin, CanonicalStorage, _connection(), _ImportsMixin, _MetadataMixin, _ProposalsMixin (+2 more)

### Community 24 - "Object Contract Tests"
Cohesion: 0.16
Nodes (14): _field_names(), All three upstream request types follow the same create-vs-update contract:, All three upstream result types carry disposition, child IDs, proposal_id,     a, _replace_contract(), test_event_to_scene_request_has_required_contract_fields(), test_event_to_scene_result_has_required_contract_fields(), test_outline_to_plot_request_has_required_contract_fields(), test_outline_to_plot_result_has_required_contract_fields() (+6 more)

### Community 25 - "Review Revision Tests"
Cohesion: 0.11
Nodes (6): ledger(), Tests for review desk revision request workflow and audit trail., Entries should be ordered by timestamp., Create a ReviewLedger with a temporary SQLite storage., TestAuditTrail, TestRevisionRequest

### Community 26 - "Core Utilities"
Cohesion: 0.14
Nodes (4): extract_text_content(), _normalize_json_value(), _normalize_payload(), Extract the main text content from a payload using common content keys.

### Community 27 - "Provider Config Storage"
Cohesion: 0.14
Nodes (7): _ProvidersMixin, Get the currently active AI provider configuration., Delete an AI provider configuration., Set a provider as active (deactivates all others)., Save or update an AI provider configuration., Get a single AI provider configuration., List all AI provider configurations.

### Community 28 - "Chapter Quality Scorer"
Cohesion: 0.22
Nodes (7): QualityScore, QualityScorer, Chapter quality scorer.  Ported from fanbianyi qualityScoreService. Calls the AI, Quality scores for a single chapter (1–10 scale)., AI-powered chapter quality scorer.      Sends the chapter content to the AI prov, Score a chapter on four quality dimensions.          Truncates content to 5000 c, Parse AI JSON response into QualityScore.

### Community 29 - "Outline-to-Plot Tests"
Cohesion: 0.4
Nodes (8): _invoke_generate_outline_to_plot_workbench(), _seed_outline_to_plot_workspace(), test_outline_to_plot_drift_rejection(), test_outline_to_plot_happy_path_generation(), test_outline_to_plot_idempotent_approval_replay(), test_outline_to_plot_review_required_update(), test_outline_to_plot_stale_parent_rejection(), test_outline_to_plot_wrong_parent_or_family_rejection()

### Community 30 - "Plot-to-Event Tests"
Cohesion: 0.33
Nodes (9): Red test for Plot -> Event workbench: the canonical service path exists but, Seed a minimal canonical workspace with a plot_node and its downstream event., _seed_plot_to_event_workspace(), test_plot_to_event_workbench_red_drift_rejection(), test_plot_to_event_workbench_red_happy_path(), test_plot_to_event_workbench_red_idempotent_approval(), test_plot_to_event_workbench_red_review_required(), test_plot_to_event_workbench_red_stale_parent() (+1 more)

### Community 31 - "Review Desk Tests"
Cohesion: 0.39
Nodes (8): _seed_chapter_review_proposal(), _seed_plot_review_proposal(), test_review_desk_approve_applies_chapter_proposal_exactly_once(), test_review_desk_approve_replay_is_idempotent_for_upstream_scene_proposals(), test_review_desk_blocks_stale_proposals_with_explicit_revision_drift(), test_review_desk_reject_and_revise_preserve_state_and_keep_revise_loops_visible(), test_review_desk_upstream_proposal_blocks_stale_plot_drift_before_apply(), test_review_desk_upstream_revise_then_reject_keeps_plot_proposal_visible_until_rejected()

### Community 32 - "Event-to-Scene Tests"
Cohesion: 0.33
Nodes (2): _seed_event_to_scene_workspace(), test_event_to_scene_workbench_canonical_parent_generation()

### Community 33 - "Repo Scaffold Tests"
Cohesion: 0.67
Nodes (6): load_manifest(), test_manifest_freezes_ownership_boundaries(), test_required_directories_exist(), test_validation_rejects_forbidden_pattern_declared_as_allowed_donor(), test_validation_rejects_forbidden_top_level_path_as_dependency(), validate_manifest()

### Community 34 - "Retrieval Support Tests"
Cohesion: 0.57
Nodes (6): _count_rows(), _scope_document_markers(), _seed_retrieval_workspace(), test_retrieval_conflicts_become_warnings_and_review_hints_not_canonical_writes(), test_retrieval_degradation_warns_but_does_not_block_authoring_flows(), test_retrieval_rebuild_stays_support_only_and_replaces_current_scope_markers()

### Community 35 - "Local Server"
Cohesion: 0.6
Nodes (5): _db_path(), _frontend_dist_path(), main(), _preferred_command_center_url(), _server_port()

### Community 36 - "End-to-End Tests"
Cohesion: 0.53
Nodes (5): _seed_upstream_chain_workspace(), test_end_to_end_flow_imports_edits_reviews_skills_and_publishes_projection_only_bundle(), test_end_to_end_upstream_generation_chain_flows_into_scene_to_chapter_behavior(), test_publish_export_recovery_handles_stale_lineage_importer_mismatch_and_interrupted_writes(), _write_donor_project()

### Community 37 - "Importer Parity Tests"
Cohesion: 0.6
Nodes (4): _fetch_canonical_provenance(), _fetch_import_records(), test_fanbianyi_import_contract_revalidates_character_exports_without_runtime_dependency(), test_webnovel_writer_import_contract_imports_canonical_and_derived_objects()

### Community 38 - "Scene-to-Chapter Tests"
Cohesion: 0.67
Nodes (5): _json_object(), _seed_workbench_workspace(), test_scene_to_chapter_workbench_generates_artifact_with_pinned_revision_and_visible_metadata(), test_scene_to_chapter_workbench_rejects_missing_or_stale_source_revision(), test_scene_to_chapter_workbench_routes_unsafe_updates_into_review_desk()

### Community 39 - "Mutation Policy Tests"
Cohesion: 0.6
Nodes (3): _seed_scene(), test_ambiguous_chapter_edits_downgrade_to_review_proposal(), test_safe_chapter_prose_edits_auto_apply_as_derived_artifact_revision()

### Community 40 - "Multi-Gen Plot Tests"
Cohesion: 0.6
Nodes (3): _FakeOutlineToPlotAI, _seed_workspace(), test_outline_to_plot_generates_multiple_plot_nodes_with_content()

### Community 41 - "Skill Workshop Tests"
Cohesion: 0.7
Nodes (4): _seed_workspace(), test_skill_workshop_imports_prompt_templates_custom_agents_and_ai_roles_through_adapters(), test_skill_workshop_rejects_forbidden_fields_explicitly(), test_skill_workshop_versions_compare_and_rollback_stay_in_one_unified_skill_model()

### Community 42 - "Storage Ledger Tests"
Cohesion: 0.5
Nodes (0): 

### Community 43 - "E2E Delete Node Tests"
Cohesion: 0.67
Nodes (0): 

### Community 44 - "Debug Utilities"
Cohesion: 1.0
Nodes (0): 

### Community 45 - "Surface List UI"
Cohesion: 1.0
Nodes (0): 

### Community 46 - "AI Analyzer Init"
Cohesion: 1.0
Nodes (1): Initialize with an AI client for intelligent analysis.

### Community 47 - "Entity Extractor"
Cohesion: 1.0
Nodes (1): Extract entities from user message.          Looks for object IDs, operations, a

### Community 48 - "Schema Seed"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "API Server Tests"
Cohesion: 1.0
Nodes (0): 

### Community 50 - "ESLint Config"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "Playwright Config"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "Vite Config"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "Vitest Config"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Surface Metrics UI"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Test Setup"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Smoke Tests"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Issue Deduplication"
Cohesion: 1.0
Nodes (1): Merge AI-identified issues with rule-based issues, deduplicating by title.

### Community 58 - "Numeric Index Check"
Cohesion: 1.0
Nodes (1): Check if this target uses a numeric index.

### Community 59 - "Storage Format Parser"
Cohesion: 1.0
Nodes (1): Create from storage format.

### Community 60 - "CJK Tokenizer"
Cohesion: 1.0
Nodes (1): Extract CJK characters and ASCII words as tokens.

### Community 61 - "Payload Content Extractor"
Cohesion: 1.0
Nodes (1): Extract the main content from the payload.

### Community 62 - "Character Pair Extractor"
Cohesion: 1.0
Nodes (1): Extract all consecutive character pairs from text.

### Community 63 - "Candidate Title Getter"
Cohesion: 1.0
Nodes (1): Get a title for the candidate from its payload.

### Community 64 - "Feedback Revision Check"
Cohesion: 1.0
Nodes (1): Check if this feedback requests a revision.

### Community 65 - "Partial Revision Check"
Cohesion: 1.0
Nodes (1): Check if this is a partial revision request.

### Community 66 - "Graph Rule"
Cohesion: 1.0
Nodes (1): Graphify Knowledge Graph Rule

### Community 67 - "Canonical Storage Singleton"
Cohesion: 1.0
Nodes (1): CanonicalStorage

### Community 68 - "Dialogue Processor Singleton"
Cohesion: 1.0
Nodes (1): DialogueProcessor

### Community 69 - "App Service Singleton"
Cohesion: 1.0
Nodes (1): SuperwriterApplicationService

### Community 70 - "Chat Session Input"
Cohesion: 1.0
Nodes (1): ChatSessionInput

### Community 71 - "Intelligent Diagnoser"
Cohesion: 1.0
Nodes (1): IntelligentDiagnoser

### Community 72 - "Dialogue Request"
Cohesion: 1.0
Nodes (1): DialogueRequest

### Community 73 - "Canonical Write Request"
Cohesion: 1.0
Nodes (1): CanonicalWriteRequest

### Community 74 - "Mutation Policy Engine"
Cohesion: 1.0
Nodes (1): MutationPolicyEngine

### Community 75 - "Diagnosis Request"
Cohesion: 1.0
Nodes (1): DiagnosisRequest

### Community 76 - "Derived Record Input"
Cohesion: 1.0
Nodes (1): DerivedRecordInput

### Community 77 - "Node Address Parser"
Cohesion: 1.0
Nodes (1): 从字符串解析，如 'plot-1-1' → NodeAddress('plot', (1, 1))。

## Knowledge Gaps
- **236 isolated node(s):** `Request for intelligent project diagnosis.`, `A specific issue identified in the project.`, `Report from intelligent project analysis.`, `AI-powered project analysis and diagnosis.      Analyzes the project state and p`, `Initialize with an AI client for intelligent analysis.` (+231 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Debug Utilities`** (2 nodes): `debug_delete.py`, `debug_delete()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Surface List UI`** (2 nodes): `SurfaceList.tsx`, `SurfaceList()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `AI Analyzer Init`** (2 nodes): `.__init__()`, `Initialize with an AI client for intelligent analysis.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Entity Extractor`** (2 nodes): `.extract_entities()`, `Extract entities from user message.          Looks for object IDs, operations, a`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Schema Seed`** (2 nodes): `_schema.py`, `seed_family_catalog()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `API Server Tests`** (2 nodes): `test_api_server.py`, `test_workbench_delete_returns_json_error_when_storage_raises()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ESLint Config`** (1 nodes): `eslint.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Playwright Config`** (1 nodes): `playwright.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vite Config`** (1 nodes): `vite.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vitest Config`** (1 nodes): `vitest.config.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Surface Metrics UI`** (1 nodes): `SurfaceMetrics.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test Setup`** (1 nodes): `setup.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Smoke Tests`** (1 nodes): `smoke.spec.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Issue Deduplication`** (1 nodes): `Merge AI-identified issues with rule-based issues, deduplicating by title.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Numeric Index Check`** (1 nodes): `Check if this target uses a numeric index.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Storage Format Parser`** (1 nodes): `Create from storage format.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CJK Tokenizer`** (1 nodes): `Extract CJK characters and ASCII words as tokens.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Payload Content Extractor`** (1 nodes): `Extract the main content from the payload.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Character Pair Extractor`** (1 nodes): `Extract all consecutive character pairs from text.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Candidate Title Getter`** (1 nodes): `Get a title for the candidate from its payload.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Feedback Revision Check`** (1 nodes): `Check if this feedback requests a revision.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Partial Revision Check`** (1 nodes): `Check if this is a partial revision request.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Graph Rule`** (1 nodes): `Graphify Knowledge Graph Rule`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Canonical Storage Singleton`** (1 nodes): `CanonicalStorage`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Dialogue Processor Singleton`** (1 nodes): `DialogueProcessor`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `App Service Singleton`** (1 nodes): `SuperwriterApplicationService`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Chat Session Input`** (1 nodes): `ChatSessionInput`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Intelligent Diagnoser`** (1 nodes): `IntelligentDiagnoser`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Dialogue Request`** (1 nodes): `DialogueRequest`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Canonical Write Request`** (1 nodes): `CanonicalWriteRequest`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Mutation Policy Engine`** (1 nodes): `MutationPolicyEngine`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Diagnosis Request`** (1 nodes): `DiagnosisRequest`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Derived Record Input`** (1 nodes): `DerivedRecordInput`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Node Address Parser`** (1 nodes): `从字符串解析，如 'plot-1-1' → NodeAddress('plot', (1, 1))。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DialogueIntent` connect `Dialogue Context` to `Application Services Core`, `AI Dialogue Engine`, `Object Diff & Policy`, `Family Contract Registry`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Why does `SuperwriterApplicationService` connect `Object Diff & Policy` to `Application Services Core`, `Partial Revision Engine`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Are the 152 inferred relationships involving `DialogueProcessor` (e.g. with `CanonicalObjectSnapshot` and `CanonicalRevisionSnapshot`) actually correct?**
  _`DialogueProcessor` has 152 INFERRED edges - model-reasoned connections that need verification._
- **Are the 123 inferred relationships involving `PipelineGenerationService` (e.g. with `AIProviderError` and `CanonicalObjectSnapshot`) actually correct?**
  _`PipelineGenerationService` has 123 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `SuperwriterApplicationService` (e.g. with `DiagnosisRequest` and `IntelligentDiagnoser`) actually correct?**
  _`SuperwriterApplicationService` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 126 inferred relationships involving `IntelligentDiagnoser` (e.g. with `CanonicalObjectSnapshot` and `CanonicalRevisionSnapshot`) actually correct?**
  _`IntelligentDiagnoser` has 126 INFERRED edges - model-reasoned connections that need verification._
- **Are the 136 inferred relationships involving `DialogueRequest` (e.g. with `CanonicalObjectSnapshot` and `CanonicalRevisionSnapshot`) actually correct?**
  _`DialogueRequest` has 136 INFERRED edges - model-reasoned connections that need verification._
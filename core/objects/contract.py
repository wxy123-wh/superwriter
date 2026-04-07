from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


CORE_OBJECTS_OWNER = "structured-object-truth"
DEFAULT_PROVENANCE_FIELDS: tuple[str, ...] = (
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "source_kind",
    "source_ref",
    "ingest_run_id",
)
CANONICAL_PROVENANCE_FIELDS: tuple[str, ...] = DEFAULT_PROVENANCE_FIELDS + (
    "revision_created_at",
    "revision_created_by",
    "revision_reason",
    "revision_source_message_id",
)


class FamilyCategory(str, Enum):
    CANONICAL = "canonical"
    DERIVED = "derived"
    LEDGER = "ledger"
    SUPPORT = "support"


class RelationKind(str, Enum):
    PARENT = "parent"
    CHILD = "child"
    REFERENCE = "reference"
    REVISION_SOURCE = "revision_source"
    LINKAGE = "linkage"


class RevisionMode(str, Enum):
    CANONICAL_CHAIN = "canonical_chain"
    APPEND_ONLY_LEDGER = "append_only_ledger"
    SNAPSHOT_DERIVED = "snapshot_derived"
    RUNTIME_LINKAGE = "runtime_linkage"


@dataclass(frozen=True, slots=True)
class IdContract:
    field_name: str
    prefix: str
    opaque: bool
    assigned_by: str
    scope: str
    immutable_once_assigned: bool = True


@dataclass(frozen=True, slots=True)
class ProvenanceField:
    name: str
    description: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class RelationContract:
    field_name: str
    target_family: str
    kind: RelationKind
    cardinality: str
    required: bool
    description: str


@dataclass(frozen=True, slots=True)
class RevisionPolicy:
    mode: RevisionMode
    revision_id_field: str
    revision_number_field: str | None
    parent_revision_id_field: str | None
    base_object_id_field: str
    derived_from_revision_field: str | None
    allows_branching: bool
    description: str


@dataclass(frozen=True, slots=True)
class FamilyContract:
    family: str
    owner: str
    category: FamilyCategory
    description: str
    id_contract: IdContract
    provenance_fields: tuple[ProvenanceField, ...]
    relations: tuple[RelationContract, ...]
    revision_policy: RevisionPolicy


def _provenance_fields(*names: str) -> tuple[ProvenanceField, ...]:
    return tuple(
        ProvenanceField(name=name, description=name.replace("_", " ")) for name in names
    )


def _canonical_family(
    family: str,
    prefix: str,
    description: str,
    relations: tuple[RelationContract, ...],
) -> FamilyContract:
    return FamilyContract(
        family=family,
        owner=CORE_OBJECTS_OWNER,
        category=FamilyCategory.CANONICAL,
        description=description,
        id_contract=IdContract(
            field_name="object_id",
            prefix=prefix,
            opaque=True,
            assigned_by="superwriter",
            scope=f"family:{family}",
        ),
        provenance_fields=_provenance_fields(*CANONICAL_PROVENANCE_FIELDS),
        relations=relations,
        revision_policy=RevisionPolicy(
            mode=RevisionMode.CANONICAL_CHAIN,
            revision_id_field="revision_id",
            revision_number_field="revision_number",
            parent_revision_id_field="parent_revision_id",
            base_object_id_field="object_id",
            derived_from_revision_field=None,
            allows_branching=False,
            description="Stable family-scoped object identity with linear head revision chain.",
        ),
    )


def _family(
    *,
    family: str,
    category: FamilyCategory,
    prefix: str,
    description: str,
    relations: tuple[RelationContract, ...],
    revision_mode: RevisionMode,
    revision_id_field: str,
    revision_number_field: str | None,
    parent_revision_id_field: str | None,
    derived_from_revision_field: str | None,
    provenance_fields: tuple[str, ...] = DEFAULT_PROVENANCE_FIELDS,
) -> FamilyContract:
    return FamilyContract(
        family=family,
        owner=CORE_OBJECTS_OWNER,
        category=category,
        description=description,
        id_contract=IdContract(
            field_name="object_id",
            prefix=prefix,
            opaque=True,
            assigned_by="superwriter",
            scope=f"family:{family}",
        ),
        provenance_fields=_provenance_fields(*provenance_fields),
        relations=relations,
        revision_policy=RevisionPolicy(
            mode=revision_mode,
            revision_id_field=revision_id_field,
            revision_number_field=revision_number_field,
            parent_revision_id_field=parent_revision_id_field,
            base_object_id_field="object_id",
            derived_from_revision_field=derived_from_revision_field,
            allows_branching=False,
            description=description,
        ),
    )


FAMILY_REGISTRY: tuple[FamilyContract, ...] = (
    _canonical_family(
        family="project",
        prefix="prj",
        description="Top-level author workspace and ownership root.",
        relations=(
            RelationContract(
                field_name="child_novel_ids",
                target_family="novel",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Projects contain one or more novels.",
            ),
        ),
    ),
    _canonical_family(
        family="novel",
        prefix="nvl",
        description="Canonical book-level narrative root inside a project.",
        relations=(
            RelationContract(
                field_name="project_id",
                target_family="project",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Every novel belongs to exactly one project.",
            ),
            RelationContract(
                field_name="outline_root_ids",
                target_family="outline_node",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Novel owns the outline hierarchy root set.",
            ),
            RelationContract(
                field_name="character_ids",
                target_family="character",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Novel owns canonical character objects.",
            ),
            RelationContract(
                field_name="setting_ids",
                target_family="setting",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Novel owns canonical setting objects.",
            ),
            RelationContract(
                field_name="canon_rule_ids",
                target_family="canon_rule",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Novel owns canon rules.",
            ),
            RelationContract(
                field_name="style_rule_ids",
                target_family="style_rule",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Novel owns style controls.",
            ),
            RelationContract(
                field_name="skill_ids",
                target_family="skill",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Novel may attach skill definitions as author controls.",
            ),
            RelationContract(
                field_name="foreshadowing_ids",
                target_family="foreshadowing",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Novel owns foreshadowing tracking objects.",
            ),
        ),
    ),
    _canonical_family(
        family="outline_node",
        prefix="out",
        description="Canonical outline hierarchy node for high-level structure.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Outline nodes belong to one novel.",
            ),
            RelationContract(
                field_name="parent_outline_node_id",
                target_family="outline_node",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=False,
                description="Optional tree parent within the outline hierarchy.",
            ),
            RelationContract(
                field_name="plot_node_ids",
                target_family="plot_node",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Outline nodes feed downstream plot nodes.",
            ),
        ),
    ),
    _canonical_family(
        family="plot_node",
        prefix="plt",
        description="Canonical plot structure node under the outline chain.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Plot nodes belong to one novel.",
            ),
            RelationContract(
                field_name="outline_node_id",
                target_family="outline_node",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Plot nodes descend from outline nodes.",
            ),
            RelationContract(
                field_name="event_ids",
                target_family="event",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Plot nodes own ordered events.",
            ),
        ),
    ),
    _canonical_family(
        family="event",
        prefix="evt",
        description="Canonical event object in the narrative lineage.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Events belong to one novel.",
            ),
            RelationContract(
                field_name="plot_node_id",
                target_family="plot_node",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Events descend from plot nodes.",
            ),
            RelationContract(
                field_name="scene_ids",
                target_family="scene",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Events own ordered scenes.",
            ),
        ),
    ),
    _canonical_family(
        family="scene",
        prefix="scn",
        description="Canonical scene object and last structured narrative truth before prose artifacts.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Scenes belong to one novel.",
            ),
            RelationContract(
                field_name="event_id",
                target_family="event",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Scenes descend from events.",
            ),
            RelationContract(
                field_name="chapter_artifact_ids",
                target_family="chapter_artifact",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Scenes may produce many chapter artifact drafts over time.",
            ),
        ),
    ),
    _canonical_family(
        family="character",
        prefix="chr",
        description="Canonical character identity and evolving truth record.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Characters belong to one novel.",
            ),
            RelationContract(
                field_name="fact_state_record_ids",
                target_family="fact_state_record",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Fact/state records may track character-specific world truth.",
            ),
        ),
    ),
    _canonical_family(
        family="setting",
        prefix="stg",
        description="Canonical setting/location object.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Settings belong to one novel.",
            ),
            RelationContract(
                field_name="fact_state_record_ids",
                target_family="fact_state_record",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Fact/state records may track setting state.",
            ),
        ),
    ),
    _canonical_family(
        family="canon_rule",
        prefix="can",
        description="Canonical world rule or invariant.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Canon rules belong to one novel.",
            ),
            RelationContract(
                field_name="fact_state_record_ids",
                target_family="fact_state_record",
                kind=RelationKind.CHILD,
                cardinality="one_to_many",
                required=False,
                description="Fact/state records may cite canon rules they satisfy or violate.",
            ),
        ),
    ),
    _canonical_family(
        family="fact_state_record",
        prefix="fsr",
        description="Canonical world-state fact anchored to narrative and world objects.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Fact/state records belong to one novel.",
            ),
            RelationContract(
                field_name="subject_character_id",
                target_family="character",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Optional subject character for the state record.",
            ),
            RelationContract(
                field_name="subject_setting_id",
                target_family="setting",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Optional subject setting for the state record.",
            ),
            RelationContract(
                field_name="governing_canon_rule_id",
                target_family="canon_rule",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Optional canon rule that governs the fact record.",
            ),
            RelationContract(
                field_name="source_scene_id",
                target_family="scene",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Optional scene that established the recorded state.",
            ),
        ),
    ),
    _canonical_family(
        family="style_rule",
        prefix="sty",
        description="Canonical authorial style rule that guides prose generation.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Style rules belong to one novel.",
            ),
        ),
    ),
    _canonical_family(
        family="skill",
        prefix="skl",
        description="Canonical skill configuration available to author workflows.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Skills belong to one novel scope.",
            ),
        ),
    ),
    _canonical_family(
        family="foreshadowing",
        prefix="fsh",
        description="Canonical foreshadowing object tracking narrative setup and payoff across scenes.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Foreshadowing objects belong to one novel.",
            ),
            RelationContract(
                field_name="source_scene_id",
                target_family="scene",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Scene where the foreshadowing is planted.",
            ),
            RelationContract(
                field_name="target_scene_id",
                target_family="scene",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Scene where the foreshadowing is resolved. Null means unresolved.",
            ),
            RelationContract(
                field_name="character_id",
                target_family="character",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Optional character related to this foreshadowing.",
            ),
        ),
    ),
    _family(
        family="chapter_artifact",
        category=FamilyCategory.DERIVED,
        prefix="cha",
        description="Derived prose chapter artifact assembled from scene revisions rather than canonical truth.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Chapter artifacts belong to one novel output context.",
            ),
            RelationContract(
                field_name="source_scene_id",
                target_family="scene",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Artifact points back to the structured source scene object.",
            ),
            RelationContract(
                field_name="source_scene_revision_id",
                target_family="scene",
                kind=RelationKind.REVISION_SOURCE,
                cardinality="many_to_one",
                required=True,
                description="Artifact is derived from a concrete scene revision, not a new scene head.",
            ),
        ),
        revision_mode=RevisionMode.SNAPSHOT_DERIVED,
        revision_id_field="artifact_revision_id",
        revision_number_field=None,
        parent_revision_id_field=None,
        derived_from_revision_field="source_scene_revision_id",
    ),
    _family(
        family="proposal",
        category=FamilyCategory.LEDGER,
        prefix="prp",
        description="Review proposal against canonical objects and revisions.",
        relations=(
            RelationContract(
                field_name="target_family",
                target_family="project",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Proposal stores the target family name in a validated reference slot.",
            ),
            RelationContract(
                field_name="target_object_id",
                target_family="novel",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Proposal references the target object under review.",
            ),
            RelationContract(
                field_name="base_revision_id",
                target_family="mutation_record",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Proposal may pin the canonical base revision it was prepared from.",
            ),
        ),
        revision_mode=RevisionMode.APPEND_ONLY_LEDGER,
        revision_id_field="record_id",
        revision_number_field=None,
        parent_revision_id_field=None,
        derived_from_revision_field=None,
    ),
    _family(
        family="approval_record",
        category=FamilyCategory.LEDGER,
        prefix="apr",
        description="Approval or rejection decision for a proposal or mutation.",
        relations=(
            RelationContract(
                field_name="proposal_id",
                target_family="proposal",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Approval records point to the proposal they resolve.",
            ),
            RelationContract(
                field_name="mutation_record_id",
                target_family="mutation_record",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Approval may reference the resulting mutation record.",
            ),
        ),
        revision_mode=RevisionMode.APPEND_ONLY_LEDGER,
        revision_id_field="record_id",
        revision_number_field=None,
        parent_revision_id_field=None,
        derived_from_revision_field=None,
    ),
    _family(
        family="mutation_record",
        category=FamilyCategory.LEDGER,
        prefix="mut",
        description="Append-only mutation audit record that references canonical object revisions.",
        relations=(
            RelationContract(
                field_name="target_object_family",
                target_family="project",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Mutation records carry a validated target family name.",
            ),
            RelationContract(
                field_name="target_object_id",
                target_family="novel",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Mutation records reference the stable target object ID.",
            ),
            RelationContract(
                field_name="result_revision_id",
                target_family="novel",
                kind=RelationKind.REVISION_SOURCE,
                cardinality="many_to_one",
                required=False,
                description="Mutation records may point at the canonical revision they produced.",
            ),
        ),
        revision_mode=RevisionMode.APPEND_ONLY_LEDGER,
        revision_id_field="record_id",
        revision_number_field=None,
        parent_revision_id_field=None,
        derived_from_revision_field=None,
    ),
    _family(
        family="import_record",
        category=FamilyCategory.SUPPORT,
        prefix="imp",
        description="Structured ingest bookkeeping for external source material.",
        relations=(
            RelationContract(
                field_name="project_id",
                target_family="project",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Import records belong to a project ingest run.",
            ),
        ),
        revision_mode=RevisionMode.APPEND_ONLY_LEDGER,
        revision_id_field="record_id",
        revision_number_field=None,
        parent_revision_id_field=None,
        derived_from_revision_field=None,
    ),
    _family(
        family="export_artifact",
        category=FamilyCategory.DERIVED,
        prefix="exp",
        description="Downstream export package projected from approved canonical or chapter artifact inputs.",
        relations=(
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=True,
                description="Exports belong to one novel delivery context.",
            ),
            RelationContract(
                field_name="source_chapter_artifact_id",
                target_family="chapter_artifact",
                kind=RelationKind.REFERENCE,
                cardinality="many_to_one",
                required=False,
                description="Exports may package a chapter artifact.",
            ),
            RelationContract(
                field_name="source_scene_revision_id",
                target_family="scene",
                kind=RelationKind.REVISION_SOURCE,
                cardinality="many_to_one",
                required=False,
                description="Exports may cite the scene revision snapshot they were projected from.",
            ),
        ),
        revision_mode=RevisionMode.SNAPSHOT_DERIVED,
        revision_id_field="artifact_revision_id",
        revision_number_field=None,
        parent_revision_id_field=None,
        derived_from_revision_field="source_scene_revision_id",
    ),
    _family(
        family="chat_session",
        category=FamilyCategory.SUPPORT,
        prefix="chs",
        description="Runtime conversation session metadata linked to projects, novels, and tools rather than story truth.",
        relations=(
            RelationContract(
                field_name="project_id",
                target_family="project",
                kind=RelationKind.LINKAGE,
                cardinality="many_to_one",
                required=True,
                description="Chat sessions attach to a project context.",
            ),
            RelationContract(
                field_name="novel_id",
                target_family="novel",
                kind=RelationKind.LINKAGE,
                cardinality="many_to_one",
                required=False,
                description="Sessions may narrow to a single novel.",
            ),
        ),
        revision_mode=RevisionMode.RUNTIME_LINKAGE,
        revision_id_field="session_state_id",
        revision_number_field=None,
        parent_revision_id_field=None,
        derived_from_revision_field=None,
        provenance_fields=DEFAULT_PROVENANCE_FIELDS + ("runtime_origin",),
    ),
    _family(
        family="chat_message_link",
        category=FamilyCategory.SUPPORT,
        prefix="cml",
        description="Message-level linkage from runtime chat history to canonical objects without claiming narrative truth.",
        relations=(
            RelationContract(
                field_name="chat_session_id",
                target_family="chat_session",
                kind=RelationKind.PARENT,
                cardinality="many_to_one",
                required=True,
                description="Every chat message link belongs to a chat session.",
            ),
            RelationContract(
                field_name="linked_object_id",
                target_family="novel",
                kind=RelationKind.LINKAGE,
                cardinality="many_to_one",
                required=False,
                description="Message links may point at any validated canonical or support object.",
            ),
            RelationContract(
                field_name="linked_revision_id",
                target_family="mutation_record",
                kind=RelationKind.REVISION_SOURCE,
                cardinality="many_to_one",
                required=False,
                description="Message links may cite a revision or mutation reference they discussed.",
            ),
        ),
        revision_mode=RevisionMode.RUNTIME_LINKAGE,
        revision_id_field="message_state_id",
        revision_number_field=None,
        parent_revision_id_field=None,
        derived_from_revision_field=None,
        provenance_fields=DEFAULT_PROVENANCE_FIELDS + ("chat_message_id", "chat_role"),
    ),
)


CANONICAL_FAMILIES: tuple[str, ...] = tuple(
    contract.family
    for contract in FAMILY_REGISTRY
    if contract.category is FamilyCategory.CANONICAL
)
DERIVED_FAMILIES: tuple[str, ...] = tuple(
    contract.family
    for contract in FAMILY_REGISTRY
    if contract.category is FamilyCategory.DERIVED
)
LEDGER_FAMILIES: tuple[str, ...] = tuple(
    contract.family
    for contract in FAMILY_REGISTRY
    if contract.category is FamilyCategory.LEDGER
)
SUPPORT_FAMILIES: tuple[str, ...] = tuple(
    contract.family
    for contract in FAMILY_REGISTRY
    if contract.category is FamilyCategory.SUPPORT
)


def get_family_contract(family: str) -> FamilyContract:
    for contract in FAMILY_REGISTRY:
        if contract.family == family:
            return contract
    raise KeyError(f"Unknown object family: {family}")


def validate_registry(registry: tuple[FamilyContract, ...] = FAMILY_REGISTRY) -> None:
    family_names = tuple(contract.family for contract in registry)
    if len(family_names) != len(set(family_names)):
        raise ValueError("Object family names must be unique")

    allowed_categories = {category.value for category in FamilyCategory}
    allowed_relation_targets = set(family_names)
    canonical_families = {
        contract.family
        for contract in registry
        if contract.category is FamilyCategory.CANONICAL
    }

    for contract in registry:
        if contract.owner != CORE_OBJECTS_OWNER:
            raise ValueError(f"{contract.family} must be owned by {CORE_OBJECTS_OWNER}")

        if contract.category.value not in allowed_categories:
            raise ValueError(f"{contract.family} has unsupported category")

        id_contract = contract.id_contract
        if id_contract.field_name != "object_id":
            raise ValueError(f"{contract.family} must use object_id as stable identity field")
        if not id_contract.opaque:
            raise ValueError(f"{contract.family} IDs must be opaque")
        if id_contract.assigned_by != "superwriter":
            raise ValueError(f"{contract.family} IDs must be assigned by superwriter")
        if not id_contract.prefix or "_" in id_contract.prefix:
            raise ValueError(f"{contract.family} prefix must be non-empty and compact")

        provenance_names = tuple(field.name for field in contract.provenance_fields)
        if len(provenance_names) != len(set(provenance_names)):
            raise ValueError(f"{contract.family} provenance fields must be unique")
        for field_name in ("created_at", "created_by", "updated_at", "updated_by"):
            if field_name not in provenance_names:
                raise ValueError(f"{contract.family} missing provenance field {field_name}")

        for relation in contract.relations:
            if relation.target_family not in allowed_relation_targets:
                raise ValueError(
                    f"{contract.family} relation {relation.field_name} points to unknown family {relation.target_family}"
                )

        policy = contract.revision_policy
        if policy.base_object_id_field != "object_id":
            raise ValueError(f"{contract.family} must key revision policy by object_id")

        if contract.category is FamilyCategory.CANONICAL:
            if policy.mode is not RevisionMode.CANONICAL_CHAIN:
                raise ValueError(f"{contract.family} must use canonical revision chains")
            if policy.revision_number_field != "revision_number":
                raise ValueError(f"{contract.family} must expose revision_number")
            if policy.parent_revision_id_field != "parent_revision_id":
                raise ValueError(f"{contract.family} must expose parent_revision_id")
            if policy.derived_from_revision_field is not None:
                raise ValueError(f"{contract.family} cannot derive from another family's revision")
        else:
            if policy.mode is RevisionMode.CANONICAL_CHAIN:
                raise ValueError(
                    f"{contract.family} cannot share canonical mutation semantics with structured truth objects"
                )
            if policy.revision_number_field is not None:
                raise ValueError(
                    f"{contract.family} must not expose canonical revision_number semantics"
                )
            if policy.parent_revision_id_field is not None:
                raise ValueError(
                    f"{contract.family} must not expose canonical parent_revision_id semantics"
                )

        if contract.family in {"chapter_artifact", "export_artifact"}:
            if policy.mode is not RevisionMode.SNAPSHOT_DERIVED:
                raise ValueError(f"{contract.family} must stay snapshot-derived")
            if policy.derived_from_revision_field != "source_scene_revision_id":
                raise ValueError(
                    f"{contract.family} must cite source_scene_revision_id instead of becoming narrative truth"
                )

        if contract.family in {"chat_session", "chat_message_link"} and policy.mode is not RevisionMode.RUNTIME_LINKAGE:
            raise ValueError(f"{contract.family} must stay runtime linkage, not narrative revision")

    required_narrative_chain = (
        ("novel", "outline_node"),
        ("outline_node", "plot_node"),
        ("plot_node", "event"),
        ("event", "scene"),
    )
    for parent, child in required_narrative_chain:
        child_contract = get_family_contract_from_registry(registry, child)
        if not any(
            relation.target_family == parent and relation.kind is RelationKind.PARENT
            for relation in child_contract.relations
        ):
            raise ValueError(f"{child} must declare {parent} as a parent relation")

    world_state_targets = {
        relation.target_family
        for relation in get_family_contract_from_registry(registry, "fact_state_record").relations
    }
    if not {"character", "setting", "canon_rule"}.issubset(world_state_targets):
        raise ValueError("fact_state_record must reference character, setting, and canon_rule families")

    if not canonical_families:
        raise ValueError("At least one canonical family is required")


def get_family_contract_from_registry(
    registry: tuple[FamilyContract, ...], family: str
) -> FamilyContract:
    for contract in registry:
        if contract.family == family:
            return contract
    raise KeyError(f"Unknown object family: {family}")


validate_registry()

"""Fail-closed reviewed authority for Yellow map-background content."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


SCHEMA = "full-color-map-background-content-v1"
REVIEW_SCHEMA = "full-color-map-background-review-v2"
LEDGER_PATH = Path("specs/full-colors/inventory/map-background-content.json")
# Each independently reviewed record is pinned by the canonical JSON digest of
# the complete document. A plausible record copied beside the ledger therefore
# cannot grant itself promotion authority.
REVIEW_RECORD_SHA256_ALLOWLIST: dict[str, str] = {
    "specs/full-colors/evidence/map-background-reviews/overworld.json": (
        "5f56acc0ef6aed08609f8b5ce844c8c9a406ca37ddc59e2c8f225022db6f9361"
    ),
    "specs/full-colors/evidence/map-background-reviews/residential-services.json": (
        "e00b3b6f05fc0e4e7398e5a96888b97df6eeeb1da730fae077bbdc5a6745a27f"
    ),
    "specs/full-colors/evidence/map-background-reviews/"
    "challenge-special-interiors.json": (
        "6b80c6dea1d640132b05ee3cd2af4f5028767accb303ab1570178db430f635ae"
    ),
    "specs/full-colors/evidence/map-background-reviews/forest-cavern.json": (
        "593864b60c3bd55c4b96baf06a13fde549b8e546422750034aee556c99cd7f15"
    ),
    "specs/full-colors/evidence/map-background-reviews/transport-special.json": (
        "4759a850c63039bed2a12e28b55ede96d034d32b0768a597759d99f41f31a27d"
    ),
}
_REVIEW_BATCH_IDENTITIES = {
    "overworld": (
        "Codex independent visual review (overworld)",
        "phase3-overworld-pallet-route1-viridian",
        None,
        "test-results/full-color-map-background-atlases/manifest.json",
    ),
    "residential-services": (
        "Codex independent visual review (residential-services)",
        "phase3-residential-bedroom-mart",
        None,
        "test-results/full-color-map-background-atlases/manifest.json",
    ),
    "challenge-special-interiors": (
        "Codex independent visual review (challenge-special-interiors)",
        "phase3-challenge-oaks-lab-dojo",
        None,
        "test-results/full-color-map-background-atlases/manifest.json",
    ),
    "forest-cavern": (
        "Codex independent visual review (forest-cavern)",
        "phase4-forest-cavern-artifact-review",
        "artifact-only-atlas-and-linked-product-parity",
        "reviewer-local/forest-cavern/manifest.json",
    ),
    "transport-special": (
        "Codex independent visual review (transport-special)",
        "phase4-transport-special-artifact-review",
        "artifact-only-atlas-and-linked-product-parity",
        "reviewer-local/transport-special/manifest.json",
    ),
}
_REVIEWED_CANDIDATE_IDENTITIES = {
    "overworld": (
        "2447aef2be0eb1f891b4eb83758ad8e4b4f17c531d0fc4de9d431ff3014fb302",
        "3dcc146ab480219846f18eea232170ecf4716cfdf321599f16888d724c8ccedd",
        "7aa5dbd60715e553b26c1a9ce3f81ff28d420b6c109cd28b6ff41414de2a1009",
    ),
    "residential-services": (
        "2447aef2be0eb1f891b4eb83758ad8e4b4f17c531d0fc4de9d431ff3014fb302",
        "3dcc146ab480219846f18eea232170ecf4716cfdf321599f16888d724c8ccedd",
        "7aa5dbd60715e553b26c1a9ce3f81ff28d420b6c109cd28b6ff41414de2a1009",
    ),
    "challenge-special-interiors": (
        "2447aef2be0eb1f891b4eb83758ad8e4b4f17c531d0fc4de9d431ff3014fb302",
        "3dcc146ab480219846f18eea232170ecf4716cfdf321599f16888d724c8ccedd",
        "7aa5dbd60715e553b26c1a9ce3f81ff28d420b6c109cd28b6ff41414de2a1009",
    ),
    "forest-cavern": (
        "2447aef2be0eb1f891b4eb83758ad8e4b4f17c531d0fc4de9d431ff3014fb302",
        "3dcc146ab480219846f18eea232170ecf4716cfdf321599f16888d724c8ccedd",
        "7aa5dbd60715e553b26c1a9ce3f81ff28d420b6c109cd28b6ff41414de2a1009",
    ),
    "transport-special": (
        "2447aef2be0eb1f891b4eb83758ad8e4b4f17c531d0fc4de9d431ff3014fb302",
        "3dcc146ab480219846f18eea232170ecf4716cfdf321599f16888d724c8ccedd",
        "7aa5dbd60715e553b26c1a9ce3f81ff28d420b6c109cd28b6ff41414de2a1009",
    ),
}
_PHASE4_ATLAS_IDENTITIES = {
    "forest-cavern": (
        "7aa6f0e2a703c813d15c8dbbfa394b898abf2aa25c4098a05311841b2c644f52",
        42,
    ),
    "transport-special": (
        "6024178ee0eff83495574141e9b9f70ef34cab6bf8a2b4dcf544841490f9a26b",
        23,
    ),
}
# Yellow's source has one historical concrete-copy header whose internal block-data
# constant names its original map. Keep the exception exact across every identity
# axis so it cannot authorize another mismatch.
_MAP_HEADER_IDENTITY_COMPATIBILITY = frozenset(
    {
        (
            78,
            "UNDERGROUND_PATH_ROUTE_7_COPY",
            "UndergroundPathRoute7Copy_h",
            "UNDERGROUND_PATH_ROUTE_7",
            None,
        )
    }
)
_MAP_HEADER_POINTER_ALIAS_COMPATIBILITY = frozenset(
    {
        (11, "UNUSED_MAP_0B", "SaffronCity_h", "SAFFRON_CITY", "UNUSED_MAP_0B"),
        (
            69,
            "CERULEAN_TRASHED_HOUSE_COPY",
            "CeruleanTrashedHouse_h",
            "CERULEAN_TRASHED_HOUSE",
            "CERULEAN_TRASHED_HOUSE_COPY",
        ),
        (
            75,
            "UNDERGROUND_PATH_ROUTE_6_COPY",
            "UndergroundPathRoute6_h",
            "UNDERGROUND_PATH_ROUTE_6",
            "UNDERGROUND_PATH_ROUTE_6_COPY",
        ),
        (105, "UNUSED_MAP_69", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_69"),
        (106, "UNUSED_MAP_6A", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_6A"),
        (107, "UNUSED_MAP_6B", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_6B"),
        (109, "UNUSED_MAP_6D", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_6D"),
        (110, "UNUSED_MAP_6E", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_6E"),
        (111, "UNUSED_MAP_6F", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_6F"),
        (112, "UNUSED_MAP_70", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_70"),
        (114, "UNUSED_MAP_72", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_72"),
        (115, "UNUSED_MAP_73", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_73"),
        (116, "UNUSED_MAP_74", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_74"),
        (117, "UNUSED_MAP_75", "LancesRoom_h", "LANCES_ROOM", "UNUSED_MAP_75"),
        (
            173,
            "CINNABAR_MART_COPY",
            "CinnabarMart_h",
            "CINNABAR_MART",
            "CINNABAR_MART_COPY",
        ),
        (
            204,
            "UNUSED_MAP_CC",
            "RocketHideoutElevator_h",
            "ROCKET_HIDEOUT_ELEVATOR",
            "UNUSED_MAP_CC",
        ),
        (
            205,
            "UNUSED_MAP_CD",
            "RocketHideoutElevator_h",
            "ROCKET_HIDEOUT_ELEVATOR",
            "UNUSED_MAP_CD",
        ),
        (
            206,
            "UNUSED_MAP_CE",
            "RocketHideoutElevator_h",
            "ROCKET_HIDEOUT_ELEVATOR",
            "UNUSED_MAP_CE",
        ),
        (231, "UNUSED_MAP_E7", "Route16Gate1F_h", "ROUTE_16_GATE_1F", "UNUSED_MAP_E7"),
        (237, "UNUSED_MAP_ED", "SilphCo2F_h", "SILPH_CO_2F", "UNUSED_MAP_ED"),
        (238, "UNUSED_MAP_EE", "SilphCo2F_h", "SILPH_CO_2F", "UNUSED_MAP_EE"),
        (241, "UNUSED_MAP_F1", "SilphCo2F_h", "SILPH_CO_2F", "UNUSED_MAP_F1"),
        (242, "UNUSED_MAP_F2", "SilphCo2F_h", "SILPH_CO_2F", "UNUSED_MAP_F2"),
        (243, "UNUSED_MAP_F3", "SilphCo2F_h", "SILPH_CO_2F", "UNUSED_MAP_F3"),
        (244, "UNUSED_MAP_F4", "SilphCo2F_h", "SILPH_CO_2F", "UNUSED_MAP_F4"),
    }
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_REVISION_RE = re.compile(r"[0-9a-f]{40}\Z")
_SYMBOL_RE = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_AUTHORITY_RE = re.compile(r"[A-Za-z0-9_./#:+-]+\Z")
_RGBDS_SYMBOL_NAME = r"#?[A-Za-z_][A-Za-z0-9_#$@]*"
_RGBDS_LOCAL_LABEL_SUFFIX = r"[A-Za-z0-9_#$@]+"
_RGBDS_LOCAL_LABEL_NAME = (
    rf"(?:{_RGBDS_SYMBOL_NAME}\.{_RGBDS_LOCAL_LABEL_SUFFIX}|"
    rf"\.{_RGBDS_LOCAL_LABEL_SUFFIX})"
)
_RGBDS_LABEL_NAME = rf"(?:{_RGBDS_SYMBOL_NAME}|{_RGBDS_LOCAL_LABEL_NAME})"
_INCLUDE_DIRECTIVE_RE = re.compile(
    # A first-column bare symbol is ambiguous macro-like syntax, not a supported
    # effective include form. Detect it here so the literal-only check rejects it.
    rf"^(?:{_RGBDS_SYMBOL_NAME}[ \t]+|"
    rf"[ \t]*(?:(?::|{_RGBDS_LABEL_NAME}:{{1,2}})[ \t]*|"
    rf"{_RGBDS_LOCAL_LABEL_NAME}[ \t]+)?)(?i:INCLUDE)\b"
)
_LITERAL_INCLUDE_RE = re.compile(
    r'^[ \t]*(?i:INCLUDE)[ \t]+"([^"\r\n]+)"[ \t]*(?:;[^\r\n]*)?$'
)
_CONST_DEF_RE = re.compile(
    r"^[ \t]*const_def(?:[ \t]+([^,\s;]+)(?:[ \t]*,[ \t]*([^,\s;]+))?)?"
    r"[ \t]*(?:;.*)?$",
    re.MULTILINE,
)
_MAP_CONST_MACRO_CONTRACT = (
    r"MACRO map_const",
    r"const \1",
    r"DEF \1_WIDTH EQU \2",
    r"DEF \1_HEIGHT EQU \3",
    "ENDM",
)
_END_INDOOR_GROUP_MACRO_CONTRACT = (
    "DEF NUM_INDOOR_MAP_GROUPS EQU 0",
    "MACRO end_indoor_group",
    r"DEF INDOORGROUP_\1 EQU const_value",
    "REDEF NUM_INDOOR_MAP_GROUPS EQU NUM_INDOOR_MAP_GROUPS + 1",
    "ENDM",
)
_CONST_MACRO_CONTRACTS = {
    "const_def": (
        "MACRO? const_def",
        "IF _NARG >= 1",
        r"DEF const_value = \1",
        "ELSE",
        "DEF const_value = 0",
        "ENDC",
        "IF _NARG >= 2",
        r"DEF const_inc = \2",
        "ELSE",
        "DEF const_inc = 1",
        "ENDC",
        "ENDM",
    ),
    "const": (
        "MACRO? const",
        r"DEF \1 EQU const_value",
        "DEF const_value += const_inc",
        "ENDM",
    ),
    "const_skip": (
        "MACRO? const_skip",
        "IF _NARG >= 1",
        r"DEF const_value += const_inc * (\1)",
        "ELSE",
        "DEF const_value += const_inc",
        "ENDC",
        "ENDM",
    ),
    "const_next": (
        "MACRO? const_next",
        r"IF (const_value > 0 && \1 < const_value) || (const_value < 0 && \1 > const_value)",
        r'FAIL "const_next cannot go backwards from {const_value} to \1"',
        "ELSE",
        r"DEF const_value = \1",
        "ENDC",
        "ENDM",
    ),
}
_POSITIONAL_AUTHORITY_NAMES = frozenset(
    {*_CONST_MACRO_CONTRACTS.keys(), "const_value", "const_inc"}
)
_ASM_DIRECTIVES = frozenset(
    {
        "ASSERT",
        "DEF",
        "ELSE",
        "ENDC",
        "ENDM",
        "FAIL",
        "IF",
        "INCLUDE",
        "MACRO",
        "MACRO?",
        "PURGE",
        "REDEF",
    }
)
_BATCH_TILESETS = {
    "overworld": frozenset({"OVERWORLD"}),
    "residential-services": frozenset(
        {
            "REDS_HOUSE_1",
            "REDS_HOUSE_2",
            "MART",
            "POKECENTER",
            "HOUSE",
            "FOREST_GATE",
            "MUSEUM",
            "GATE",
            "LOBBY",
            "LAB",
            "CLUB",
        }
    ),
    "challenge-special-interiors": frozenset(
        {
            "DOJO",
            "GYM",
            "UNDERGROUND",
            "SHIP",
            "CEMETERY",
            "INTERIOR",
            "MANSION",
            "FACILITY",
        }
    ),
    "forest-cavern": frozenset({"FOREST", "CAVERN"}),
    "transport-special": frozenset({"SHIP_PORT", "PLATEAU", "BEACH_HOUSE"}),
}
_REPLACEMENT_IDENTITIES = (
    "CINNABAR_GYM_GATE_BLOCKS",
    "CUT_TREE",
    "REPLACE_TILE_BLOCK",
    "SPINNER_ARROW_TILES",
)
_GENERIC_REPLACE_TILE_BLOCK_MAPS = frozenset(
    {
        "AGATHAS_ROOM",
        "BRUNOS_ROOM",
        "GAME_CORNER",
        "LANCES_ROOM",
        "LORELEIS_ROOM",
        "POKEMON_MANSION_1F",
        "POKEMON_MANSION_2F",
        "ROCKET_HIDEOUT_B1F",
        "SILPH_CO_2F",
        "SILPH_CO_3F",
        "SILPH_CO_4F",
        "SILPH_CO_5F",
        "SILPH_CO_6F",
        "SILPH_CO_7F",
        "SILPH_CO_8F",
        "SILPH_CO_9F",
        "SILPH_CO_10F",
        "SILPH_CO_11F",
        "VERMILION_GYM",
        "VICTORY_ROAD_1F",
        "VICTORY_ROAD_2F",
        "VICTORY_ROAD_3F",
    }
)
_SPINNER_ARROW_MAPS = frozenset(
    {"ROCKET_HIDEOUT_B2F", "ROCKET_HIDEOUT_B3F", "VIRIDIAN_GYM"}
)
_CARD_KEY_MAPS = tuple(f"SILPH_CO_{floor}F" for floor in range(2, 12))
_ROOF_IDENTITIES = (
    "PALLET",
    "VIRIDIAN",
    "PEWTER",
    "CERULEAN",
    "LAVENDER",
    "VERMILION",
    "CELADON",
    "FUCHSIA",
    "CINNABAR",
    "INDIGO",
    "SAFFRON",
)
_MAP_OVERRIDE_IDENTITIES = {
    "CELADON_MART_ROOF": ("CELADON_MART_ROOF_TILES_4B_TO_4F_BLUE",),
    "CELADON_MART_1F": ("CELADON_MART_1F_TILES_07_08_17_18_YELLOW",),
}
_MAP_OVERRIDE_RULES = (
    {
        "identity": "CELADON_MART_ROOF_TILES_4B_TO_4F_BLUE",
        "map": "CELADON_MART_ROOF",
        "match": "inclusive-range",
        "tiles": [0x4B, 0x4C, 0x4D, 0x4E, 0x4F],
        "palette": "FULL_COLOR_INTERIOR_BLUE",
    },
    {
        "identity": "CELADON_MART_1F_TILES_07_08_17_18_YELLOW",
        "map": "CELADON_MART_1F",
        "match": "exact-set",
        "tiles": [0x07, 0x08, 0x17, 0x18],
        "palette": "FULL_COLOR_INTERIOR_YELLOW",
    },
)
_MISSING_FALLBACK_AUTHORITY = (
    "data/tilesets/full_color_interiors.asm#FullColorBGPalettePointers"
)
_ARCHITECTURE_BOUNDARY_AUTHORITY = (
    "engine/full_color/passive_overworld.asm#PassiveFullColorIsPresentedSliceMap"
)
_PRODUCTION_PRESENTATION_PREDICATE = (
    "PassiveFullColorIsPresentedSliceMap:",
    "ld a, [wCurMapTileset]",
    "cp OVERWORLD",
    "jr z, .overworld",
    "cp REDS_HOUSE_1",
    "jr c, .ineligible",
    "cp FACILITY + 1",
    "jr nc, .ineligible",
    "cp FOREST",
    "jr z, .ineligible",
    "cp SHIP_PORT",
    "jr z, .ineligible",
    "cp CAVERN",
    "jr z, .ineligible",
    "xor a",
    "ret",
    ".overworld",
    "ld a, [wCurMap]",
    "cp NUM_CITY_MAPS",
    "jr c, .eligible",
    "cp FIRST_ROUTE_MAP",
    "jr c, .ineligible",
    "cp FIRST_INDOOR_MAP",
    "jr c, .eligible",
    ".ineligible",
    "ld a, 1",
    "and a",
    "ret",
    ".eligible",
    "xor a",
    "ret",
)


class MapBackgroundContentError(ValueError):
    """The checked authority or its source universe is not contractual."""


def _reject_duplicate_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MapBackgroundContentError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _load_json(source: str) -> object:
    return json.loads(source, object_pairs_hook=_reject_duplicate_json_object)


class ContentStatus(StrEnum):
    COMPLETE = "complete"
    FALLBACK = "fallback"
    MISSING = "missing"


class Presentation(StrEnum):
    COLOR = "color"
    YELLOW = "yellow"


class FallbackKind(StrEnum):
    CONTENT_MISSING = "content-missing"
    ARCHITECTURE_BOUNDARY = "architecture-boundary"
    SCENE_OWNERSHIP = "scene-ownership"


def _object(raw: object, *, path: str, fields: set[str]) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise MapBackgroundContentError(f"{path}: expected object")
    keys = set(raw)
    if keys != fields:
        missing = sorted(fields - keys)
        extra = sorted(keys - fields)
        raise MapBackgroundContentError(
            f"{path}: exact fields required; missing={missing}, extra={extra}"
        )
    return raw


def _string(raw: object, *, path: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(raw, str) or not raw:
        raise MapBackgroundContentError(f"{path}: expected non-empty string")
    if pattern is not None and pattern.fullmatch(raw) is None:
        raise MapBackgroundContentError(f"{path}: invalid value {raw!r}")
    return raw


def _integer(raw: object, *, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise MapBackgroundContentError(f"{path}: expected non-negative integer")
    return raw


def _enum(enum_type: type[StrEnum], raw: object, *, path: str) -> Any:
    value = _string(raw, path=path)
    try:
        return enum_type(value)
    except ValueError as exc:
        raise MapBackgroundContentError(f"{path}: unknown value {value!r}") from exc


def _symbols(raw: object, *, path: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise MapBackgroundContentError(f"{path}: expected array")
    values = tuple(
        _string(value, path=f"{path}[{index}]", pattern=_SYMBOL_RE)
        for index, value in enumerate(raw)
    )
    if len(values) != len(set(values)):
        raise MapBackgroundContentError(f"{path}: duplicate identities")
    if values != tuple(sorted(values)):
        raise MapBackgroundContentError(f"{path}: identities must be lexical")
    return values


def _authority(raw: object, *, path: str, nullable: bool = False) -> str | None:
    if nullable and raw is None:
        return None
    value = _string(raw, path=path, pattern=_AUTHORITY_RE)
    parsed = PurePosixPath(value.split("#", 1)[0])
    if value.startswith("/") or ".." in parsed.parts or "\\" in value:
        raise MapBackgroundContentError(
            f"{path}: authority must be normalized and relative"
        )
    return value


@dataclass(frozen=True, slots=True)
class FallbackReason:
    kind: FallbackKind
    authority: str

    @classmethod
    def from_raw(cls, raw: object, *, path: str) -> FallbackReason | None:
        if raw is None:
            return None
        obj = _object(raw, path=path, fields={"kind", "authority"})
        return cls(
            kind=_enum(FallbackKind, obj["kind"], path=f"{path}.kind"),
            authority=_authority(obj["authority"], path=f"{path}.authority"),
        )

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "authority": self.authority}


@dataclass(frozen=True, slots=True)
class Review:
    authority: str
    atlas_sha256: str
    route: str
    revision: str

    @classmethod
    def from_raw(cls, raw: object, *, path: str) -> Review | None:
        if raw is None:
            return None
        obj = _object(
            raw,
            path=path,
            fields={"authority", "atlas_sha256", "route", "revision"},
        )
        return cls(
            authority=_authority(obj["authority"], path=f"{path}.authority"),
            atlas_sha256=_string(
                obj["atlas_sha256"], path=f"{path}.atlas_sha256", pattern=_SHA256_RE
            ),
            route=_string(obj["route"], path=f"{path}.route", pattern=_AUTHORITY_RE),
            revision=_string(
                obj["revision"], path=f"{path}.revision", pattern=_REVISION_RE
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "authority": self.authority,
            "atlas_sha256": self.atlas_sha256,
            "route": self.route,
            "revision": self.revision,
        }


def _review_status(status: ContentStatus, review: Review | None, *, path: str) -> None:
    if status is ContentStatus.COMPLETE and review is None:
        raise MapBackgroundContentError(
            f"{path}: complete content requires reviewed authority"
        )
    if status is not ContentStatus.COMPLETE and review is not None:
        raise MapBackgroundContentError(
            f"{path}: only complete content may carry reviewed authority"
        )


@dataclass(frozen=True, slots=True)
class TilesetContentRow:
    id: int
    name: str
    content_status: ContentStatus
    palette_authority: str | None
    attribute_authority: str | None
    animations: tuple[str, ...]
    replacements: tuple[str, ...]
    review: Review | None
    batch: str

    @classmethod
    def from_raw(cls, raw: object, *, path: str) -> TilesetContentRow:
        obj = _object(
            raw,
            path=path,
            fields={
                "id",
                "name",
                "content_status",
                "palette_authority",
                "attribute_authority",
                "animations",
                "replacements",
                "review",
                "batch",
            },
        )
        status = _enum(
            ContentStatus, obj["content_status"], path=f"{path}.content_status"
        )
        review = Review.from_raw(obj["review"], path=f"{path}.review")
        _review_status(status, review, path=path)
        palette = _authority(
            obj["palette_authority"], path=f"{path}.palette_authority", nullable=True
        )
        attributes = _authority(
            obj["attribute_authority"],
            path=f"{path}.attribute_authority",
            nullable=True,
        )
        if status is ContentStatus.MISSING and (
            palette is not None or attributes is not None
        ):
            raise MapBackgroundContentError(
                f"{path}: missing content cannot claim payload authority"
            )
        if status is not ContentStatus.MISSING and (
            palette is None or attributes is None
        ):
            raise MapBackgroundContentError(
                f"{path}: populated content requires both payload authorities"
            )
        return cls(
            id=_integer(obj["id"], path=f"{path}.id"),
            name=_string(obj["name"], path=f"{path}.name", pattern=_SYMBOL_RE),
            content_status=status,
            palette_authority=palette,
            attribute_authority=attributes,
            animations=_symbols(obj["animations"], path=f"{path}.animations"),
            replacements=_symbols(obj["replacements"], path=f"{path}.replacements"),
            review=review,
            batch=_string(obj["batch"], path=f"{path}.batch", pattern=_AUTHORITY_RE),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "content_status": self.content_status.value,
            "palette_authority": self.palette_authority,
            "attribute_authority": self.attribute_authority,
            "animations": list(self.animations),
            "replacements": list(self.replacements),
            "review": None if self.review is None else self.review.to_dict(),
            "batch": self.batch,
        }


@dataclass(frozen=True, slots=True)
class MapContentRow:
    id: int
    name: str
    tileset: str
    content_status: ContentStatus
    presentation: Presentation
    fallback_reason: FallbackReason | None
    roof: str | None
    overrides: tuple[str, ...]
    animations: tuple[str, ...]
    replacements: tuple[str, ...]
    review: Review | None
    batch: str

    @classmethod
    def from_raw(cls, raw: object, *, path: str) -> MapContentRow:
        obj = _object(
            raw,
            path=path,
            fields={
                "id",
                "name",
                "tileset",
                "content_status",
                "presentation",
                "fallback_reason",
                "roof",
                "overrides",
                "animations",
                "replacements",
                "review",
                "batch",
            },
        )
        status = _enum(
            ContentStatus, obj["content_status"], path=f"{path}.content_status"
        )
        presentation = _enum(
            Presentation, obj["presentation"], path=f"{path}.presentation"
        )
        fallback = FallbackReason.from_raw(
            obj["fallback_reason"], path=f"{path}.fallback_reason"
        )
        review = Review.from_raw(obj["review"], path=f"{path}.review")
        _review_status(status, review, path=path)
        if presentation is Presentation.YELLOW and fallback is None:
            raise MapBackgroundContentError(
                f"{path}: Yellow presentation requires fallback_reason"
            )
        if presentation is Presentation.COLOR and fallback is not None:
            raise MapBackgroundContentError(
                f"{path}: Color presentation cannot carry fallback_reason"
            )
        if status is ContentStatus.MISSING:
            if fallback is None or fallback.kind is not FallbackKind.CONTENT_MISSING:
                raise MapBackgroundContentError(
                    f"{path}: missing content requires content-missing fallback"
                )
        elif fallback is not None and fallback.kind is FallbackKind.CONTENT_MISSING:
            raise MapBackgroundContentError(
                f"{path}: content-missing fallback requires missing status"
            )
        roof_raw = obj["roof"]
        roof = (
            None
            if roof_raw is None
            else _string(roof_raw, path=f"{path}.roof", pattern=_SYMBOL_RE)
        )
        return cls(
            id=_integer(obj["id"], path=f"{path}.id"),
            name=_string(obj["name"], path=f"{path}.name", pattern=_SYMBOL_RE),
            tileset=_string(obj["tileset"], path=f"{path}.tileset", pattern=_SYMBOL_RE),
            content_status=status,
            presentation=presentation,
            fallback_reason=fallback,
            roof=roof,
            overrides=_symbols(obj["overrides"], path=f"{path}.overrides"),
            animations=_symbols(obj["animations"], path=f"{path}.animations"),
            replacements=_symbols(obj["replacements"], path=f"{path}.replacements"),
            review=review,
            batch=_string(obj["batch"], path=f"{path}.batch", pattern=_AUTHORITY_RE),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "tileset": self.tileset,
            "content_status": self.content_status.value,
            "presentation": self.presentation.value,
            "fallback_reason": None
            if self.fallback_reason is None
            else self.fallback_reason.to_dict(),
            "roof": self.roof,
            "overrides": list(self.overrides),
            "animations": list(self.animations),
            "replacements": list(self.replacements),
            "review": None if self.review is None else self.review.to_dict(),
            "batch": self.batch,
        }


@dataclass(frozen=True, slots=True)
class _DiscoveredMap:
    id: int
    name: str
    tileset: str


def _const_literal(token: str, *, path: Path, directive: str) -> int:
    try:
        value = int(token[1:], 16) if token.startswith("$") else int(token, 10)
    except ValueError as exc:
        raise MapBackgroundContentError(
            f"{path}: {directive} requires a literal integer"
        ) from exc
    return value


def _normalized_asm(source: str) -> tuple[str, ...]:
    return tuple(
        _canonicalize_asm_directives(code)
        for raw_line in source.splitlines()
        if (code := raw_line.split(";", 1)[0].strip())
    )


def _canonicalize_asm_directives(code: str) -> str:
    """Normalize RGBDS keywords without changing case-sensitive identifiers."""
    head_match = re.match(r"\S+", code)
    if head_match is not None and head_match.group().upper() in _ASM_DIRECTIVES:
        code = head_match.group().upper() + code[head_match.end() :]
    return re.sub(r"^(DEF|REDEF)(\s+\S+\s+)(?i:EQU)\b", r"\1\2EQU", code)


def _validate_no_positional_authority_shadow(path: Path) -> None:
    for line in _normalized_asm(path.read_text(encoding="utf-8")):
        declaration = re.match(
            r"(?:MACRO\??|DEF|REDEF)\s+([A-Za-z_][A-Za-z0-9_]*)", line
        )
        if declaration and declaration.group(1) in _POSITIONAL_AUTHORITY_NAMES:
            raise MapBackgroundContentError(
                f"{path}: effective dependency may not redefine positional "
                f"authority {declaration.group(1)}"
            )
        purge = re.fullmatch(r"PURGE\s+(.+)", line)
        if purge:
            purged = {
                token for token in re.split(r"[\s,]+", purge.group(1).strip()) if token
            }
            shadowed = sorted(purged & _POSITIONAL_AUTHORITY_NAMES)
            if shadowed:
                raise MapBackgroundContentError(
                    f"{path}: effective dependency may not purge positional "
                    f"authority {shadowed}"
                )


def _effective_literal_includes(source: str, *, path: Path) -> tuple[str, ...]:
    includes: list[str] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        if _INCLUDE_DIRECTIVE_RE.match(line) is None:
            continue
        match = _LITERAL_INCLUDE_RE.fullmatch(line)
        if match is None:
            raise MapBackgroundContentError(
                f"{path}:{line_number}: effective INCLUDE must be exactly one "
                "quoted literal path"
            )
        includes.append(match.group(1))
    return tuple(includes)


def _effective_asm_lines(
    root: Path, *, entry_names: tuple[str, ...] = ("main.asm",)
) -> tuple[tuple[Path, int, str], ...]:
    """Expand literal translation-root include universes in assembler order.

    Reconciliation fixtures intentionally contain only the map-background slice of
    the repository. Missing unrelated includes are therefore ignored, while every
    present dependency is expanded and checked. A real checkout contains the full
    graph and the build independently rejects a missing include.
    """
    entries = tuple(root / name for name in entry_names)
    if not all(entry.is_file() for entry in entries):
        return tuple(
            (path, line_number, raw_line)
            for path in sorted(root.rglob("*.asm"))
            for line_number, raw_line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            )
        )

    active: set[Path] = set()
    lines: list[tuple[Path, int, str]] = []

    def expand(path: Path) -> None:
        resolved = path.resolve()
        if resolved in active:
            raise MapBackgroundContentError(f"{path}: recursive INCLUDE dependency")
        if not path.is_file():
            return
        active.add(resolved)
        source = path.read_text(encoding="utf-8")
        for line_number, raw_line in enumerate(source.splitlines(), start=1):
            if _INCLUDE_DIRECTIVE_RE.match(raw_line) is None:
                lines.append((path, line_number, raw_line))
                continue
            match = _LITERAL_INCLUDE_RE.fullmatch(raw_line)
            if match is None:
                raise MapBackgroundContentError(
                    f"{path}:{line_number}: effective INCLUDE must be exactly one "
                    "quoted literal path"
                )
            relative = PurePosixPath(match.group(1))
            if relative.is_absolute() or ".." in relative.parts:
                raise MapBackgroundContentError(
                    f"{path}:{line_number}: effective INCLUDE dependency must be a "
                    "repo-root-contained relative path"
                )
            expand(root.joinpath(*relative.parts))
        active.remove(resolved)

    for entry in entries:
        expand(entry)
    return tuple(lines)


def _override_palette_values(root: Path) -> dict[str, int]:
    """Resolve immutable literal authorities for production override palettes."""
    authority_path = root / "data/tilesets/full_color_interiors.asm"
    required = {str(rule["palette"]) for rule in _MAP_OVERRIDE_RULES}
    values: dict[str, int] = {}
    conditional_depth = 0
    macro_depth = 0
    for path, line_number, raw_line in _effective_asm_lines(root):
        code = raw_line.split(";", 1)[0].strip()
        if not code:
            continue
        normalized = _canonicalize_asm_directives(code)

        if normalized == "ENDC":
            conditional_depth = max(conditional_depth - 1, 0)
        if normalized == "ENDM":
            macro_depth = max(macro_depth - 1, 0)

        declaration = re.match(r"^(DEF|REDEF)\s+(\S+)\b", normalized)
        legacy = re.match(
            r"^(\S+)\s+(?i:EQU|EQUS|SET)\b",
            code,
        )
        macro = re.match(r"^MACRO\??\s+(\S+)\b", normalized)
        purge = re.fullmatch(r"PURGE\s+(.+)", normalized)

        touched: set[str] = set()
        if declaration is not None and declaration.group(2) in required:
            touched.add(declaration.group(2))
        if legacy is not None and legacy.group(1) in required:
            touched.add(legacy.group(1))
        if macro is not None and macro.group(1) in required:
            touched.add(macro.group(1))
        if purge is not None:
            touched.update(
                token
                for token in re.split(r"[\s,]+", purge.group(1).strip())
                if token in required
            )

        for palette in touched:
            exact = re.fullmatch(
                rf"DEF\s+{re.escape(palette)}\s+EQU\s+(\$[0-9A-Fa-f]+|[0-9]+)",
                normalized,
            )
            if (
                path == authority_path
                and exact is not None
                and palette not in values
                and conditional_depth == 0
                and macro_depth == 0
            ):
                value = _const_literal(
                    exact.group(1), path=authority_path, directive=palette
                )
                if value > 7:
                    raise MapBackgroundContentError(
                        f"{authority_path}: {palette} exceeds the palette-bit range"
                    )
                values[palette] = value
                continue
            raise MapBackgroundContentError(
                f"{path}:{line_number}: {palette} has a non-authoritative "
                "definition, redefinition, purge, SET/EQUS alias, or macro shadow"
            )

        if re.match(r"^IF\b", normalized):
            conditional_depth += 1
        if re.match(r"^MACRO\??\s+", normalized):
            macro_depth += 1

    missing = sorted(required - values.keys())
    if missing:
        raise MapBackgroundContentError(
            f"{authority_path}: expected one exact palette authority for {missing}"
        )
    return values


def _validate_effective_include_dependencies(
    root: Path, include_paths: tuple[str, ...], *, excluded: frozenset[str]
) -> None:
    active: set[Path] = set()
    resolved_root = root.resolve()

    def validate(relative: str, *, top_level: bool) -> None:
        relative_path = PurePosixPath(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise MapBackgroundContentError(
                f"{relative}: effective INCLUDE dependency must be a "
                "repo-root-contained relative path"
            )
        path = root.joinpath(*relative_path.parts)
        resolved = path.resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise MapBackgroundContentError(
                f"{path}: effective INCLUDE dependency resolves outside repository root"
            ) from exc
        if resolved in active:
            raise MapBackgroundContentError(f"{path}: recursive INCLUDE dependency")
        if not top_level and relative in excluded:
            raise MapBackgroundContentError(
                f"{path}: positional authority may only appear at its exact "
                "top-level INCLUDE slot"
            )
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MapBackgroundContentError(
                f"{path}: cannot read effective INCLUDE dependency: {exc}"
            ) from exc
        if relative not in excluded:
            _validate_no_positional_authority_shadow(path)
        active.add(resolved)
        for child in _effective_literal_includes(source, path=path):
            validate(child, top_level=False)
        active.remove(resolved)

    for relative in include_paths:
        validate(relative, top_level=True)


def _validate_const_macro_authority(root: Path) -> None:
    includes_path = root / "includes.asm"
    macros_path = root / "macros/const.asm"
    includes = _normalized_asm(includes_path.read_text(encoding="utf-8"))
    macro_include = 'INCLUDE "macros/const.asm"'
    asserts_include = 'INCLUDE "macros/asserts.asm"'
    map_include = 'INCLUDE "constants/map_constants.asm"'
    tileset_include = 'INCLUDE "constants/tileset_constants.asm"'
    if (
        includes[:2] != (asserts_include, macro_include)
        or includes.count(asserts_include) != 1
        or includes.count(macro_include) != 1
        or includes.count(map_include) != 1
        or includes.count(tileset_include) != 1
        or not (
            includes.index(macro_include)
            < includes.index(map_include)
            < includes.index(tileset_include)
        )
    ):
        raise MapBackgroundContentError(
            f"{includes_path}: const macro dependency/order drifted from the "
            "positional authority contract"
        )
    _validate_no_positional_authority_shadow(includes_path)

    effective_include_paths = _effective_literal_includes(
        "\n".join(includes[: includes.index(tileset_include) + 1]),
        path=includes_path,
    )
    asserts_path = root / "macros/asserts.asm"
    asserts_source = asserts_path.read_text(encoding="utf-8")
    relevant_names = "|".join(map(re.escape, _CONST_MACRO_CONTRACTS))
    if re.search(r"^\s*(?i:INCLUDE)\b", asserts_source, re.MULTILINE) or re.search(
        rf"^\s*(?i:MACRO\??)\s+(?:{relevant_names})\s*$",
        asserts_source,
        re.MULTILINE,
    ):
        raise MapBackgroundContentError(
            f"{asserts_path}: pre-const dependency may not shadow positional macros"
        )

    _validate_effective_include_dependencies(
        root,
        effective_include_paths,
        excluded=frozenset(
            {
                "macros/const.asm",
                "constants/map_constants.asm",
                "constants/tileset_constants.asm",
            }
        ),
    )

    normalized = _normalized_asm(macros_path.read_text(encoding="utf-8"))
    index = 0
    while index < len(normalized):
        if re.fullmatch(r"MACRO\??\s+[A-Za-z_][A-Za-z0-9_]*", normalized[index]):
            try:
                index = normalized.index("ENDM", index + 1) + 1
            except ValueError as exc:
                raise MapBackgroundContentError(
                    f"{macros_path}: every macro definition must end with ENDM"
                ) from exc
            continue
        raise MapBackgroundContentError(
            f"{macros_path}: top-level executable statement is not authorized"
        )
    for name, expected in _CONST_MACRO_CONTRACTS.items():
        definitions = [
            index
            for index, line in enumerate(normalized)
            if re.fullmatch(rf"MACRO\??\s+{re.escape(name)}", line)
        ]
        if len(definitions) != 1:
            raise MapBackgroundContentError(
                f"{macros_path}: expected one exact {name} macro authority"
            )
        start = definitions[0]
        try:
            end = normalized.index("ENDM", start + 1)
        except ValueError as exc:
            raise MapBackgroundContentError(
                f"{macros_path}: {name} macro must end with ENDM"
            ) from exc
        if normalized[start : end + 1] != expected:
            raise MapBackgroundContentError(
                f"{macros_path}: {name} macro authority drifted from its exact contract"
            )


def _validate_terminal_suffix(
    suffix: str, *, path: Path, directive: str, terminal: str
) -> None:
    executable = _normalized_asm(suffix)
    if directive == "map_const":
        expected = (
            "DEF LAST_MAP EQU $ff",
            'ASSERT NUM_MAPS <= LAST_MAP, "map IDs overlap LAST_MAP"',
        )
    else:
        expected = ()
    if executable != expected:
        raise MapBackgroundContentError(
            f"{path}: executable statements after {terminal} drifted from the "
            "exact positional authority postlude"
        )


def _validate_map_const_macro(source: str, *, path: Path) -> None:
    normalized = _normalized_asm(source)
    starts = [
        index for index, line in enumerate(normalized) if line == "MACRO map_const"
    ]
    if len(starts) != 1:
        raise MapBackgroundContentError(
            f"{path}: expected exactly one exact map_const macro definition"
        )
    start = starts[0]
    try:
        end = normalized.index("ENDM", start + 1)
    except ValueError as exc:
        raise MapBackgroundContentError(
            f"{path}: map_const macro must end with ENDM"
        ) from exc
    actual = normalized[start : end + 1]
    if actual != _MAP_CONST_MACRO_CONTRACT:
        raise MapBackgroundContentError(
            f"{path}: map_const macro definition drifted from its exact contract"
        )


def _validate_end_indoor_group_macro(source: str, *, path: Path) -> None:
    normalized = _normalized_asm(source)
    starts = [
        index
        for index, line in enumerate(normalized)
        if line == "MACRO end_indoor_group"
    ]
    counter_declarations = tuple(
        line
        for line in normalized
        if re.match(r"(?:DEF|REDEF)\s+NUM_INDOOR_MAP_GROUPS\b", line)
    )
    expected_counter_declarations = (
        _END_INDOOR_GROUP_MACRO_CONTRACT[0],
        _END_INDOOR_GROUP_MACRO_CONTRACT[3],
    )
    if len(starts) != 1 or counter_declarations != expected_counter_declarations:
        raise MapBackgroundContentError(
            f"{path}: expected exactly one exact end_indoor_group macro authority"
        )
    start = starts[0]
    try:
        end = normalized.index("ENDM", start + 1)
    except ValueError as exc:
        raise MapBackgroundContentError(
            f"{path}: end_indoor_group macro must end with ENDM"
        ) from exc
    declaration_start = start - 1
    actual = normalized[declaration_start : end + 1]
    if declaration_start < 0 or actual != _END_INDOOR_GROUP_MACRO_CONTRACT:
        raise MapBackgroundContentError(
            f"{path}: end_indoor_group macro authority drifted from its exact contract"
        )


def _positional_constants(
    source: str,
    *,
    path: Path,
    directive: str,
    terminal: str,
) -> tuple[tuple[int, str], ...]:
    const_def_lines = re.findall(r"^[ \t]*const_def\b[^\n]*$", source, re.MULTILINE)
    matches = list(_CONST_DEF_RE.finditer(source))
    if len(const_def_lines) != 1 or len(matches) != 1:
        raise MapBackgroundContentError(f"{path}: expected exactly one const_def")
    const_def_match = matches[0]
    base_token, increment_token = const_def_match.groups()
    value = (
        0
        if not base_token
        else _const_literal(base_token, path=path, directive="const_def")
    )
    increment = (
        1
        if not increment_token
        else _const_literal(increment_token, path=path, directive="const_def increment")
    )
    if value < 0 or increment <= 0:
        raise MapBackgroundContentError(
            f"{path}: const_def requires a non-negative base and positive increment"
        )

    body_start = const_def_match.end()
    if body_start < len(source) and source[body_start] == "\n":
        body_start += 1
    terminal_match = re.search(
        rf"^(?i:DEF)[ \t]+{re.escape(terminal)}[ \t]+(?i:EQU)[ \t]+"
        r"const_value[ \t]*$",
        source[body_start:],
        re.MULTILINE,
    )
    if terminal_match is None:
        raise MapBackgroundContentError(
            f"{path}: expected {terminal} to terminate positional constants"
        )
    body = source[body_start : body_start + terminal_match.start()]
    terminal_end = body_start + terminal_match.end()
    _validate_terminal_suffix(
        source[terminal_end:], path=path, directive=directive, terminal=terminal
    )

    rows: list[tuple[int, str]] = []
    body_line = source[:body_start].count("\n") + 1
    for line_number, raw_line in enumerate(body.splitlines(), start=body_line):
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue
        if directive == "const":
            row_match = re.fullmatch(r"const\s+([A-Z][A-Z0-9_]*)", line)
        else:
            row_match = re.fullmatch(
                r"map_const\s+([A-Z][A-Z0-9_]*)\s*,\s*"
                r"([^,\s]+)\s*,\s*([^,\s]+)",
                line,
            )
        if row_match is not None:
            if directive == "map_const":
                _const_literal(
                    row_match.group(2), path=path, directive="map_const width"
                )
                _const_literal(
                    row_match.group(3), path=path, directive="map_const height"
                )
            rows.append((value, row_match.group(1)))
            value += increment
            continue
        skip_match = re.fullmatch(r"const_skip(?:\s+([^,\s]+))?", line)
        if skip_match is not None:
            count_token = skip_match.group(1)
            count = (
                1
                if count_token is None
                else _const_literal(count_token, path=path, directive="const_skip")
            )
            if count < 0:
                raise MapBackgroundContentError(
                    f"{path}: const_skip requires a non-negative literal"
                )
            value += increment * count
            continue
        next_match = re.fullmatch(r"const_next\s+([^,\s]+)", line)
        if next_match is not None:
            next_value = _const_literal(
                next_match.group(1), path=path, directive="const_next"
            )
            if next_value < value:
                raise MapBackgroundContentError(
                    f"{path}: const_next cannot move the counter backwards"
                )
            value = next_value
            continue
        if directive == "map_const" and re.fullmatch(
            r"end_indoor_group\s+[A-Z][A-Z0-9_]*", line
        ):
            continue
        if directive == "map_const" and re.fullmatch(
            r"(?i:DEF)\s+(?:NUM_CITY_MAPS|FIRST_ROUTE_MAP|FIRST_INDOOR_MAP)\s+"
            r"(?i:EQU)\s+const_value",
            line,
        ):
            continue
        raise MapBackgroundContentError(
            f"{path}:{line_number}: unsupported positional constant statement {line!r}"
        )
    return tuple(rows)


def _tilesets(root: Path) -> tuple[tuple[int, str], ...]:
    path = root / "constants/tileset_constants.asm"
    source = path.read_text(encoding="utf-8")
    rows = _positional_constants(
        source,
        path=path,
        directive="const",
        terminal="NUM_TILESETS",
    )
    names = [name for _, name in rows]
    if len(rows) != 25 or len(names) != len(set(names)):
        raise MapBackgroundContentError(
            f"{path}: expected 25 unique positional tilesets and NUM_TILESETS"
        )
    return rows


def _map_symbol_from_label(label: str) -> str:
    symbol = re.sub(r"(?<=[a-z])(?=\d)", "_", label)
    symbol = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", symbol)
    symbol = re.sub(r"([a-z])([A-Z])", r"\1_\2", symbol)
    return symbol.upper()


def _maps(root: Path) -> tuple[_DiscoveredMap, ...]:
    constants_path = root / "constants/map_constants.asm"
    pointers_path = root / "data/maps/map_header_pointers.asm"
    constants_source = constants_path.read_text(encoding="utf-8")
    _validate_map_const_macro(constants_source, path=constants_path)
    _validate_end_indoor_group_macro(constants_source, path=constants_path)
    constant_rows = _positional_constants(
        constants_source,
        path=constants_path,
        directive="map_const",
        terminal="NUM_MAPS",
    )
    pointer_lines = []
    pointer_table_started = False
    pointer_table_width_seen = False
    pointer_table_ended = False
    for line_number, source_line in enumerate(
        pointers_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = source_line.strip()
        if not line or line.startswith(";"):
            continue
        code = line.split(";", 1)[0].rstrip()
        if not pointer_table_started:
            if code != "MapHeaderPointers::":
                raise MapBackgroundContentError(
                    f"{pointers_path}:{line_number}: unexpected content before "
                    f"MapHeaderPointers {line!r}"
                )
            pointer_table_started = True
            continue
        if pointer_table_ended:
            raise MapBackgroundContentError(
                f"{pointers_path}:{line_number}: unexpected content after map header "
                f"pointer table {line!r}"
            )
        if not pointer_table_width_seen:
            if code != "table_width 2":
                raise MapBackgroundContentError(
                    f"{pointers_path}:{line_number}: map header pointer table requires "
                    "exact table_width 2 declaration"
                )
            pointer_table_width_seen = True
            continue
        if code == "assert_table_length NUM_MAPS":
            pointer_table_ended = True
            continue
        if re.match(r"dw\b", code) is None:
            raise MapBackgroundContentError(
                f"{pointers_path}:{line_number}: unauthorized map header pointer table "
                f"statement {line!r}"
            )
        pointer_match = re.fullmatch(
            r"dw\s+([A-Za-z][A-Za-z0-9_]*_h)(?:\s+;\s*([A-Z][A-Z0-9_]*))?",
            line,
        )
        if pointer_match is None:
            raise MapBackgroundContentError(
                f"{pointers_path}:{line_number}: malformed map header pointer {line!r}"
            )
        pointer_lines.append(pointer_match.groups())
    if (
        not pointer_table_started
        or not pointer_table_width_seen
        or not pointer_table_ended
    ):
        raise MapBackgroundContentError(
            f"{pointers_path}: incomplete MapHeaderPointers table contract"
        )
    constant_names = [name for _, name in constant_rows]
    if len(constant_rows) != len(pointer_lines) or len(constant_names) != len(
        set(constant_names)
    ):
        raise MapBackgroundContentError(
            "map constants and header pointer ABI do not align uniquely"
        )
    headers: dict[str, tuple[str, str]] = {}
    for path in sorted((root / "data/maps/headers").glob("*.asm")):
        matches = re.findall(
            r"^\s*map_header\s+([A-Za-z0-9_]+),\s*([A-Z][A-Z0-9_]*),\s*([A-Z][A-Z0-9_]*),",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if len(matches) != 1 or matches[0][0] != path.stem:
            raise MapBackgroundContentError(
                f"{path}: expected one matching concrete map_header"
            )
        label, map_constant, tileset = matches[0]
        headers[f"{label}_h"] = (map_constant, tileset)
    rows = []
    used_labels: set[str] = set()
    discovered_aliases: set[tuple[int, str, str, str, str | None]] = set()
    for (map_id, name), pointer_row in zip(constant_rows, pointer_lines, strict=True):
        pointer, annotated_identity = pointer_row
        annotated_identity = annotated_identity or None
        if pointer in {"0", "$0000"}:
            continue
        if pointer not in headers:
            raise MapBackgroundContentError(
                f"{pointers_path}: unknown concrete header {pointer}"
            )
        declared_identity, tileset = headers[pointer]
        alias_identity = (
            map_id,
            name,
            pointer,
            declared_identity,
            annotated_identity,
        )
        if alias_identity in _MAP_HEADER_POINTER_ALIAS_COMPATIBILITY:
            discovered_aliases.add(alias_identity)
            continue
        if pointer in used_labels:
            raise MapBackgroundContentError(
                f"{pointers_path}: duplicate header alias {name} is not an exact "
                "historical compatibility slot"
            )
        pointer_name = _map_symbol_from_label(pointer.removesuffix("_h"))
        identity = (map_id, name, pointer, declared_identity, annotated_identity)
        if pointer_name != name or declared_identity != name:
            if identity in _MAP_HEADER_IDENTITY_COMPATIBILITY:
                pass
            else:
                raise MapBackgroundContentError(
                    f"{pointers_path}: positional map constant {name} points to "
                    f"header identity {pointer_name} declaring {declared_identity}"
                )
        elif annotated_identity:
            raise MapBackgroundContentError(
                f"{pointers_path}: concrete header identity {name} cannot use an "
                "alias annotation"
            )
        used_labels.add(pointer)
        rows.append(_DiscoveredMap(map_id, name, tileset))
    if (
        set(headers) != used_labels
        or discovered_aliases != _MAP_HEADER_POINTER_ALIAS_COMPATIBILITY
        or len(rows) != 224
    ):
        raise MapBackgroundContentError(
            f"map source universe must contain exactly 224 one-to-one concrete headers; got {len(rows)}"
        )
    return tuple(rows)


def _asm_table_body(source: str, *, path: Path, label: str) -> tuple[str, ...]:
    start_marker = f"{label}::"
    end_marker = f"{label}End::"
    lines = source.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == start_marker]
    ends = [index for index, line in enumerate(lines) if line.strip() == end_marker]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise MapBackgroundContentError(
            f"{path}: expected one exact {label}/{label}End source authority"
        )
    return tuple(lines[starts[0] + 1 : ends[0]])


def _payload_pointer_authorities(
    root: Path, tilesets: tuple[tuple[int, str], ...]
) -> dict[str, tuple[str | None, str | None]]:
    path = root / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")

    def pointers(label: str) -> dict[str, str | None]:
        rows: dict[str, str | None] = {}
        for line_number, raw_line in enumerate(
            _asm_table_body(source, path=path, label=label), start=1
        ):
            if not raw_line.strip():
                continue
            match = re.fullmatch(
                r"\s*dw\s+(0|[A-Za-z][A-Za-z0-9_]*)\s*;\s*"
                r"([A-Z][A-Z0-9_]*)\s*",
                raw_line,
            )
            if match is None:
                raise MapBackgroundContentError(
                    f"{path}:{line_number}: malformed {label} authority row"
                )
            pointer, name = match.groups()
            if name in rows:
                raise MapBackgroundContentError(
                    f"{path}: duplicate {label} tileset identity {name}"
                )
            rows[name] = None if pointer == "0" else pointer
        return rows

    palettes = pointers("FullColorBGPalettePointers")
    attributes = pointers("FullColorTileAttributePointers")
    expected_prefix = tuple(name for _, name in tilesets[: len(palettes)])
    if (
        tuple(palettes) != expected_prefix
        or tuple(attributes) != expected_prefix
        or len(palettes) != len(tilesets)
    ):
        raise MapBackgroundContentError(
            f"{path}: palette/attribute pointer identities drifted from tileset ABI"
        )
    result: dict[str, tuple[str | None, str | None]] = {}
    for _, name in tilesets:
        palette = palettes.get(name)
        attribute = attributes.get(name)
        if (palette is None) != (attribute is None):
            raise MapBackgroundContentError(
                f"{path}: {name} must have both payload pointers or neither"
            )
        for symbol in (palette, attribute):
            if (
                symbol is not None
                and re.search(rf"^\s*{re.escape(symbol)}::\s*$", source, re.MULTILINE)
                is None
            ):
                overworld = (root / "data/tilesets/full_color_overworld.asm").read_text(
                    encoding="utf-8"
                )
                if (
                    re.search(
                        rf"^\s*{re.escape(symbol)}::\s*$", overworld, re.MULTILINE
                    )
                    is None
                ):
                    raise MapBackgroundContentError(
                        f"{path}: pointer target {symbol} has no source-owned label"
                    )
        result[name] = (palette, attribute)
    return result


def _roof_authorities(root: Path) -> dict[int, tuple[str, str]]:
    path = root / "data/tilesets/full_color_overworld.asm"
    source = path.read_text(encoding="utf-8")
    rows: dict[int, tuple[str, str]] = {}
    for map_id, raw_line in enumerate(
        _asm_table_body(source, path=path, label="FullColorOverworldRoofAssignments")
    ):
        match = re.fullmatch(
            r"\s*db\s+FULL_COLOR_ROOF_([A-Z][A-Z0-9_]*)\s*;\s*"
            r"([A-Z][A-Z0-9_]*)\s*",
            raw_line,
        )
        if match is None:
            raise MapBackgroundContentError(
                f"{path}: malformed roof assignment at positional ID {map_id}"
            )
        rows[map_id] = match.groups()
    if len(rows) != 37:
        raise MapBackgroundContentError(
            f"{path}: expected 37 positional outdoor roof assignments"
        )
    return rows


def _tileset_animation_authorities(
    root: Path, tilesets: tuple[tuple[int, str], ...]
) -> dict[str, tuple[str, ...]]:
    animation_constants = (root / "constants/map_data_constants.asm").read_text(
        encoding="utf-8"
    )
    header_path = root / "data/tilesets/tileset_headers.asm"
    tileset_headers = header_path.read_text(encoding="utf-8")
    rows = re.findall(
        r"^\s*tileset\s+([A-Za-z][A-Za-z0-9_]*),.*?,\s*"
        r"(TILEANIM_[A-Z_]+)\s*$",
        tileset_headers,
        re.MULTILINE,
    )
    if len(rows) != len(tilesets):
        raise MapBackgroundContentError(
            f"{header_path}: animation rows drifted from the tileset ABI"
        )
    authorities: dict[str, tuple[str, ...]] = {}
    for (tileset_id, tileset), (source_name, identity) in zip(
        tilesets, rows, strict=True
    ):
        expected_source_name = tileset.title().replace("_", "")
        if source_name != expected_source_name:
            raise MapBackgroundContentError(
                f"{header_path}: positional tileset {tileset_id} names "
                f"{source_name}, expected {expected_source_name}"
            )
        authorities[tileset] = () if identity == "TILEANIM_NONE" else (identity,)

    animation_identities = {identity for _, identity in rows}
    for identity in animation_identities:
        if (
            re.search(
                rf"^\s*const\s+{re.escape(identity)}\b",
                animation_constants,
                re.MULTILINE,
            )
            is None
        ):
            raise MapBackgroundContentError(
                f"{identity} lacks its source-owned constant identity"
            )
    return authorities


def production_roof_region_rules(root: Path | str) -> tuple[dict[str, object], ...]:
    """Return the fixed reviewed coordinate-dependent roof records."""
    root = Path(root)
    path = root / "data/tilesets/full_color_overworld.asm"
    source = path.read_text(encoding="utf-8")
    definitions = tuple(
        re.findall(
            r"^\s*DEF\s+(FULL_COLOR_ROOF_REGION_RULE_SIZE|"
            r"NUM_FULL_COLOR_ROOF_REGION_RULES)\s+EQU\s+([0-9]+)\s*$",
            source,
            re.MULTILINE,
        )
    )
    body = tuple(
        line.strip()
        for line in _asm_table_body(
            source, path=path, label="FullColorOverworldRoofRegionRules"
        )
        if line.split(";", 1)[0].strip()
    )
    expected = ("db ROUTE_6, 2, FULL_COLOR_ROOF_SAFFRON, FULL_COLOR_ROOF_VERMILION",)
    if definitions != (
        ("FULL_COLOR_ROOF_REGION_RULE_SIZE", "4"),
        ("NUM_FULL_COLOR_ROOF_REGION_RULES", "1"),
    ) or body != expected:
        raise MapBackgroundContentError(
            f"{path}: roof-region identities, data shape, or exact values drifted"
        )
    return (
        {
            "map": "ROUTE_6",
            "y_split": 2,
            "upper_roof": "SAFFRON",
            "lower_roof": "VERMILION",
        },
    )


def production_map_override_rules(root: Path | str) -> tuple[dict[str, object], ...]:
    """Return the exact reviewed data-table overrides after validating source."""
    root = Path(root)
    path = root / "data/tilesets/full_color_interiors.asm"
    source = path.read_text(encoding="utf-8")
    count_definitions = re.findall(
        r"^\s*DEF\s+NUM_FULL_COLOR_MAP_ATTRIBUTE_OVERRIDE_GROUPS\s+EQU\s+"
        r"([0-9]+)\s*$",
        source,
        re.MULTILINE,
    )
    body = tuple(
        line.split(";", 1)[0].strip()
        for line in _asm_table_body(
            source, path=path, label="FullColorMapAttributeOverrides"
        )
        if line.split(";", 1)[0].strip()
    )
    expected_body = (
        "db CELADON_MART_ROOF, 5, FULL_COLOR_INTERIOR_BLUE",
        "db $4b, $4c, $4d, $4e, $4f",
        "db CELADON_MART_1F, 4, FULL_COLOR_INTERIOR_YELLOW",
        "db $07, $08, $17, $18",
    )
    if count_definitions != ["2"] or body != expected_body:
        raise MapBackgroundContentError(
            f"{path}: override identities, data shape, or exact values drifted"
        )
    palette_values = _override_palette_values(root)
    if palette_values != {
        "FULL_COLOR_INTERIOR_BLUE": 3,
        "FULL_COLOR_INTERIOR_YELLOW": 4,
    }:
        raise MapBackgroundContentError(
            f"{path}: override identities, data shape, or exact values drifted"
        )
    rules: list[dict[str, object]] = []
    for template in _MAP_OVERRIDE_RULES:
        rule = dict(template)
        palette = str(rule["palette"])
        rule["palette_value"] = palette_values[palette]
        rules.append(rule)
    return tuple(rules)


def _production_replacement_authorities(
    root: Path, discovered_maps: tuple[_DiscoveredMap, ...]
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    """Discover exact tileset capabilities and concrete map-callable writers."""
    map_tilesets = {row.name: row.tileset for row in discovered_maps}
    # Caller discovery must follow the assembler's effective dependency graph.
    # Besides being the reviewed authority, this also keeps isolated shadow
    # repositories honest: Path.rglob() does not descend into their symlinked
    # source directories and would otherwise report every callable writer absent.
    source_lines = _effective_asm_lines(
        root, entry_names=("main.asm", "home.asm", "maps.asm")
    )

    generic_callers: list[Path] = []
    spinner_callers: list[Path] = []
    for path, _line_number, raw_line in source_lines:
        code = raw_line.split(";", 1)[0].strip()
        if re.fullmatch(r"(?:predef|predef_jump)\s+ReplaceTileBlock", code):
            generic_callers.append(path.relative_to(root))
        if re.search(r"\b(?:call|jp|jr|farjp)\s+(?:nz,\s*)?LoadSpinnerArrowTiles\b", code):
            spinner_callers.append(path.relative_to(root))

    expected_generic_paths = {
        Path("engine/events/card_key.asm"),
        *(Path("scripts") / f"{name}.asm" for name in (
            "AgathasRoom", "BrunosRoom", "GameCorner", "LancesRoom",
            "LoreleisRoom", "PokemonMansion1F", "PokemonMansion2F",
            "RocketHideoutB1F", "SilphCo2F", "SilphCo3F", "SilphCo4F",
            "SilphCo5F", "SilphCo6F", "SilphCo7F", "SilphCo8F",
            "SilphCo9F", "SilphCo10F", "SilphCo11F", "VermilionGym",
            "VictoryRoad1F", "VictoryRoad2F", "VictoryRoad3F",
        )),
    }
    expected_spinner_paths = {
        Path("home/overworld.asm"),
        Path("scripts/RocketHideoutB2F.asm"),
        Path("scripts/RocketHideoutB3F.asm"),
        Path("scripts/ViridianGym.asm"),
    }
    expected_generic_counts = {path: 1 for path in expected_generic_paths}
    expected_generic_counts.update(
        {
            Path("scripts/GameCorner.asm"): 2,
            Path("scripts/SilphCo2F.asm"): 2,
            Path("scripts/SilphCo3F.asm"): 2,
            Path("scripts/SilphCo4F.asm"): 2,
            Path("scripts/SilphCo5F.asm"): 3,
            Path("scripts/SilphCo7F.asm"): 3,
            Path("scripts/SilphCo9F.asm"): 4,
        }
    )
    if Counter(generic_callers) != expected_generic_counts:
        raise MapBackgroundContentError(
            "REPLACE_TILE_BLOCK: concrete caller identities or dependencies drifted"
        )
    if Counter(spinner_callers) != {path: 1 for path in expected_spinner_paths}:
        raise MapBackgroundContentError(
            "SPINNER_ARROW_TILES: concrete caller identities or dependencies drifted"
        )

    maps_assembly_path = root / "maps.asm"
    if not maps_assembly_path.is_file():
        raise MapBackgroundContentError(
            f"{maps_assembly_path}: replacement caller dependency is stale or absent"
        )
    included_scripts = {
        Path(match.group(1))
        for match in re.finditer(
            r'^\s*INCLUDE\s+"(scripts/[A-Za-z0-9_]+\.asm)"\s*$',
            maps_assembly_path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    }
    expected_map_scripts = (
        expected_generic_paths - {Path("engine/events/card_key.asm")}
    ) | (expected_spinner_paths - {Path("home/overworld.asm")})
    if not expected_map_scripts <= included_scripts:
        raise MapBackgroundContentError(
            f"{maps_assembly_path}: replacement caller dependency is stale or absent"
        )

    card_key_path = root / "data/events/card_key_maps.asm"
    card_key_lines = tuple(
        match.group(1)
        for match in re.finditer(
            r"^\s*db\s+(SILPH_CO_[0-9]+F)\s*$",
            card_key_path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )
    if card_key_lines != _CARD_KEY_MAPS:
        raise MapBackgroundContentError(
            f"{card_key_path}: Card Key ReplaceTileBlock map identities drifted"
        )
    card_key_writer = (root / "engine/events/card_key.asm").read_text(
        encoding="utf-8"
    )
    if (
        len(re.findall(r"^\s*cp\s+SILPH_CO_11F\s*$", card_key_writer, re.MULTILINE)) != 2
        or len(re.findall(r"^\s*ld\s+a,\s*\$3\s*$", card_key_writer, re.MULTILINE)) != 1
        or len(re.findall(r"^\s*ld\s+a,\s*\$e\s*$", card_key_writer, re.MULTILINE)) != 1
    ):
        raise MapBackgroundContentError(
            f"{card_key_path}: Card Key ReplaceTileBlock exact block semantics drifted"
        )

    cut_path = root / "engine/overworld/cut.asm"
    cut_source = _normalized_asm(cut_path.read_text(encoding="utf-8"))
    cut_contract = (
        "ld a, [wCurMapTileset]", "and a", "jr z, .overworld", "cp GYM",
        "jr nz, .nothingToCut", "ld a, [wTileInFrontOfPlayer]", "cp $50",
        "jr nz, .nothingToCut", "jr .canCut", ".overworld", "dec a",
        "ld a, [wTileInFrontOfPlayer]", "cp $3d", "jr z, .canCut", "cp $52",
        "jr z, .canCut",
    )
    try:
        cut_start = cut_source.index(cut_contract[0])
    except ValueError as exc:
        raise MapBackgroundContentError(
            f"{cut_path}: CUT_TREE tileset callability authority is absent"
        ) from exc
    if cut_source[cut_start : cut_start + len(cut_contract)] != cut_contract:
        raise MapBackgroundContentError(
            f"{cut_path}: CUT_TREE tileset callability authority drifted"
        )
    cut_blocks_path = root / "data/tilesets/cut_tree_blocks.asm"
    cut_blocks_source = cut_blocks_path.read_text(encoding="utf-8")
    pairs = re.findall(
        r"^\s*db\s+\$([0-9A-Fa-f]{2}),\s*\$([0-9A-Fa-f]{2})\s*$",
        cut_blocks_source,
        re.MULTILINE,
    )
    if (
        len(re.findall(r"^CutTreeBlockSwaps:\s*$", cut_blocks_source, re.MULTILINE)) != 1
        or len(re.findall(r"^\s*db\s+-1\s*;\s*end\s*$", cut_blocks_source, re.MULTILINE)) != 1
        or pairs != [
        ("32", "6D"), ("33", "6C"), ("34", "6F"), ("35", "4C"),
        ("60", "6E"), ("0B", "0A"), ("3C", "35"), ("3F", "35"),
        ("3D", "36"),
        ]
    ):
        raise MapBackgroundContentError(
            f"{cut_blocks_path}: CUT_TREE replacement authority or blockset semantics drifted"
        )

    cinnabar_path = root / "engine/events/hidden_events/cinnabar_gym_quiz.asm"
    cinnabar_source = cinnabar_path.read_text(encoding="utf-8")
    # Keep coordinates and symbolic orientation exact without deriving them from
    # the FACILITY tileset used by this one map.
    gate_rows_raw = re.findall(
        r"^\s*gym_gate_coord\s+([0-9]+),\s*([0-9]+),\s*"
        r"(HORIZONTAL_GATE_BLOCK|VERTICAL_GATE_BLOCK)\s*$",
        cinnabar_source,
        re.MULTILINE,
    )
    if (
        len(re.findall(r"^\s*call\s+CinnabarGym_ReplaceTileBlock\s*$", cinnabar_source, re.MULTILINE)) != 1
        or len(re.findall(r"^CinnabarGym_ReplaceTileBlock:\s*$", cinnabar_source, re.MULTILINE)) != 1
        or re.findall(
            r"^\s*DEF\s+(HORIZONTAL_GATE_BLOCK|VERTICAL_GATE_BLOCK)\s+EQU\s+"
            r"(\$[0-9A-Fa-f]{2})\s*$",
            cinnabar_source,
            re.MULTILINE,
        )
        != [("HORIZONTAL_GATE_BLOCK", "$54"), ("VERTICAL_GATE_BLOCK", "$5f")]
        or gate_rows_raw
        != [
            ("9", "3", "HORIZONTAL_GATE_BLOCK"),
            ("6", "3", "HORIZONTAL_GATE_BLOCK"),
            ("6", "6", "HORIZONTAL_GATE_BLOCK"),
            ("3", "8", "VERTICAL_GATE_BLOCK"),
            ("2", "6", "HORIZONTAL_GATE_BLOCK"),
            ("2", "3", "HORIZONTAL_GATE_BLOCK"),
        ]
    ):
        raise MapBackgroundContentError(
            f"{cinnabar_path}: CINNABAR_GYM_GATE_BLOCKS writer semantics drifted"
        )

    map_authorities: dict[str, set[str]] = {name: set() for name in map_tilesets}
    for name, tileset in map_tilesets.items():
        if tileset in {"OVERWORLD", "GYM"}:
            map_authorities[name].add("CUT_TREE")
    for name in _GENERIC_REPLACE_TILE_BLOCK_MAPS:
        map_authorities[name].add("REPLACE_TILE_BLOCK")
    for name in _SPINNER_ARROW_MAPS:
        map_authorities[name].add("SPINNER_ARROW_TILES")
    map_authorities["CINNABAR_GYM"].add("CINNABAR_GYM_GATE_BLOCKS")
    normalized_maps = {
        name: tuple(sorted(identities)) for name, identities in map_authorities.items()
    }
    tileset_authorities: dict[str, set[str]] = {}
    for name, identities in normalized_maps.items():
        tileset_authorities.setdefault(map_tilesets[name], set()).update(identities)
    normalized_tilesets = {
        name: tuple(sorted(identities))
        for name, identities in tileset_authorities.items()
    }
    return normalized_tilesets, normalized_maps


def _expected_batch(tileset: str) -> str | None:
    matches = [batch for batch, names in _BATCH_TILESETS.items() if tileset in names]
    if len(matches) != 1:
        return None
    return matches[0]


def _production_presentation(tileset_id: int, tileset: str) -> Presentation:
    admitted = tileset == "OVERWORLD" or (
        1 <= tileset_id <= 22 and tileset not in {"FOREST", "SHIP_PORT", "CAVERN"}
    )
    return Presentation.COLOR if admitted else Presentation.YELLOW


def _validate_production_presentation_predicate(root: Path) -> None:
    path = root / "engine/full_color/passive_overworld.asm"
    normalized = _normalized_asm(path.read_text(encoding="utf-8"))
    try:
        start = normalized.index("PassiveFullColorIsPresentedSliceMap:")
        end = normalized.index("PassiveFullColorApplyMap:", start + 1)
    except ValueError as exc:
        raise MapBackgroundContentError(
            f"{path}: production presentation predicate boundary is absent"
        ) from exc
    if normalized[start:end] != _PRODUCTION_PRESENTATION_PREDICATE:
        raise MapBackgroundContentError(
            f"{path}: production presentation predicate drifted from the Phase 1 contract"
        )


def _review_finding(
    root: Path,
    *,
    content_kind: str,
    content_id: int,
    content_name: str,
    batch: str,
    batch_tilesets: tuple[dict[str, object], ...],
    batch_maps: tuple[dict[str, object], ...],
    review: Review,
) -> str | None:
    authority_path, separator, record_id = review.authority.partition("#")
    if not separator or not record_id:
        return f"{content_kind} {content_name}: review authority must name a record"
    path = root / authority_path
    if path == root / LEDGER_PATH:
        return f"{content_kind} {content_name}: review authority must be independent"
    allowlisted_sha256 = REVIEW_RECORD_SHA256_ALLOWLIST.get(authority_path)
    if allowlisted_sha256 is None:
        return (
            f"{content_kind} {content_name}: review authority path is not "
            "independently allowlisted"
        )
    if _SHA256_RE.fullmatch(allowlisted_sha256) is None:
        return (
            f"{content_kind} {content_name}: review authority allowlist digest "
            "is invalid"
        )
    try:
        raw = _load_json(path.read_text(encoding="utf-8"))
        canonical = json.dumps(
            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        actual_sha256 = hashlib.sha256(canonical).hexdigest()
        if actual_sha256 != allowlisted_sha256:
            raise MapBackgroundContentError(
                f"{path}: canonical SHA-256 does not match independent allowlist"
            )
        document = _object(
            raw,
            path=str(path),
            fields={
                "schema",
                "batch",
                "review",
                "atlas",
                "reviewed_candidate",
                "content",
                "retained_artifacts",
                "reviews",
            },
        )
        if document["schema"] != REVIEW_SCHEMA:
            raise MapBackgroundContentError(
                f"{path}.schema: expected {REVIEW_SCHEMA!r}"
            )
        if document["batch"] != batch:
            raise MapBackgroundContentError(f"{path}.batch: wrong batch identity")
        try:
            expected_reviewer, expected_route, expected_purpose, expected_atlas_path = (
                _REVIEW_BATCH_IDENTITIES[batch]
            )
        except KeyError as exc:
            raise MapBackgroundContentError(
                f"{path}.batch: unknown review batch"
            ) from exc
        review_fields = {
            "review_kind",
            "reviewer",
            "result",
            "revision",
            "route",
            "products",
            "observations",
        }
        if expected_purpose is not None:
            review_fields.add("purpose")
        review_summary = _object(
            document["review"],
            path=f"{path}.review",
            fields=review_fields,
        )
        if review_summary["review_kind"] != "independent-ai-visual":
            raise MapBackgroundContentError(
                f"{path}.review.review_kind: independent AI review required"
            )
        if review_summary["result"] != "accepted":
            raise MapBackgroundContentError(
                f"{path}.review.result: review not accepted"
            )
        if review_summary["reviewer"] != expected_reviewer:
            raise MapBackgroundContentError(f"{path}.review.reviewer: wrong identity")
        if review_summary["revision"] != review.revision:
            raise MapBackgroundContentError(
                f"{path}.review.revision: identity mismatch"
            )
        if review_summary["route"] != review.route:
            raise MapBackgroundContentError(f"{path}.review.route: identity mismatch")
        if review.route != expected_route:
            raise MapBackgroundContentError(f"{path}.review.route: wrong batch route")
        if (
            expected_purpose is not None
            and review_summary["purpose"] != expected_purpose
        ):
            raise MapBackgroundContentError(
                f"{path}.review.purpose: wrong evidence purpose"
            )
        products = review_summary["products"]
        expected_products = [
            {"product": product, "mode": mode}
            for product in ("pokeyellow", "pokeyellow_debug")
            for mode in ("color", "yellow")
        ]
        if expected_purpose is not None:
            expected_products = [
                {"product": product, "claim": "linked-artifact-parity"}
                for product in (
                    "pokeyellow",
                    "pokeyellow_debug",
                    "pokeyellow_vc",
                    "pokeyellow_phase2_audit",
                )
            ]
        if products != expected_products:
            raise MapBackgroundContentError(
                f"{path}.review.products: exact evidence claim set required"
            )
        observations = review_summary["observations"]
        if (
            not isinstance(observations, list)
            or len(observations) < 2
            or any(
                not isinstance(value, str) or not value.strip()
                for value in observations
            )
        ):
            raise MapBackgroundContentError(
                f"{path}.review.observations: concrete observations required"
            )
        atlas = _object(
            document["atlas"],
            path=f"{path}.atlas",
            fields={"path", "manifest_sha256", "content_sha256", "artifacts"},
        )
        if atlas["path"] != expected_atlas_path:
            raise MapBackgroundContentError(f"{path}.atlas.path: wrong producer path")
        if atlas["manifest_sha256"] != review.atlas_sha256:
            raise MapBackgroundContentError(
                f"{path}.atlas.manifest_sha256: identity mismatch"
            )
        _string(
            atlas["content_sha256"],
            path=f"{path}.atlas.content_sha256",
            pattern=_SHA256_RE,
        )
        atlas_artifacts = atlas["artifacts"]
        if not isinstance(atlas_artifacts, list) or not atlas_artifacts:
            raise MapBackgroundContentError(f"{path}.atlas.artifacts: expected array")
        for index, artifact in enumerate(atlas_artifacts):
            artifact_row = _object(
                artifact,
                path=f"{path}.atlas.artifacts[{index}]",
                fields={"path", "sha256"},
            )
            artifact_path = _string(
                artifact_row["path"], path=f"{path}.atlas.artifacts[{index}].path"
            )
            if not artifact_path.startswith(f"{batch}/"):
                raise MapBackgroundContentError(
                    f"{path}.atlas.artifacts[{index}].path: outside batch"
                )
            _string(
                artifact_row["sha256"],
                path=f"{path}.atlas.artifacts[{index}].sha256",
                pattern=_SHA256_RE,
            )
        if expected_purpose is not None:
            expected_content_sha256, expected_artifact_count = _PHASE4_ATLAS_IDENTITIES[
                batch
            ]
            if atlas["content_sha256"] != expected_content_sha256:
                raise MapBackgroundContentError(
                    f"{path}.atlas.content_sha256: wrong reviewed content"
                )
            if len(atlas_artifacts) != expected_artifact_count:
                raise MapBackgroundContentError(
                    f"{path}.atlas.artifacts: incomplete reviewed content"
                )
        candidate = _object(
            document["reviewed_candidate"],
            path=f"{path}.reviewed_candidate",
            fields={
                "path",
                "sha256",
                "ledger_canonical_sha256",
                "source_semantic_sha256",
            },
        )
        if (
            candidate["path"]
            != "test-results/full-color-proposals/map-background-content.proposal.json"
        ):
            raise MapBackgroundContentError(
                f"{path}.reviewed_candidate.path: wrong proposal path"
            )
        for field in ("sha256", "ledger_canonical_sha256", "source_semantic_sha256"):
            _string(
                candidate[field],
                path=f"{path}.reviewed_candidate.{field}",
                pattern=_SHA256_RE,
            )
        expected_candidate = _REVIEWED_CANDIDATE_IDENTITIES[batch]
        if (
            tuple(
                candidate[field]
                for field in (
                    "sha256",
                    "ledger_canonical_sha256",
                    "source_semantic_sha256",
                )
            )
            != expected_candidate
        ):
            raise MapBackgroundContentError(
                f"{path}.reviewed_candidate: stale or unreviewed candidate identity"
            )
        content = _object(
            document["content"],
            path=f"{path}.content",
            fields={"tilesets", "maps"},
        )
        if content["tilesets"] != list(batch_tilesets) or content["maps"] != list(
            batch_maps
        ):
            raise MapBackgroundContentError(
                f"{path}.content: exact promoted batch membership required"
            )
        retained = document["retained_artifacts"]
        if not isinstance(retained, list) or len(retained) != 4:
            raise MapBackgroundContentError(
                f"{path}.retained_artifacts: exact four product/mode manifests required"
            )
        retained_products: list[dict[str, str]] = []
        for index, retained_raw in enumerate(retained):
            retained_fields = {
                "manifest_path",
                "manifest_sha256",
                "product",
                "mode",
                "artifacts",
            }
            if expected_purpose is not None:
                retained_fields.add("purpose")
            retained_row = _object(
                retained_raw,
                path=f"{path}.retained_artifacts[{index}]",
                fields=retained_fields,
            )
            product = _string(
                retained_row["product"],
                path=f"{path}.retained_artifacts[{index}].product",
            )
            mode = _string(
                retained_row["mode"],
                path=f"{path}.retained_artifacts[{index}].mode",
            )
            retained_products.append({"product": product, "mode": mode})
            if (
                expected_purpose is not None
                and retained_row["purpose"] != expected_purpose
            ):
                raise MapBackgroundContentError(
                    f"{path}.retained_artifacts[{index}].purpose: wrong evidence purpose"
                )
            _string(
                retained_row["manifest_sha256"],
                path=f"{path}.retained_artifacts[{index}].manifest_sha256",
                pattern=_SHA256_RE,
            )
            artifact_rows = retained_row["artifacts"]
            if not isinstance(artifact_rows, list) or not artifact_rows:
                raise MapBackgroundContentError(
                    f"{path}.retained_artifacts[{index}].artifacts: expected array"
                )
            for artifact_index, artifact in enumerate(artifact_rows):
                frame = _object(
                    artifact,
                    path=f"{path}.retained_artifacts[{index}].artifacts[{artifact_index}]",
                    fields={"path", "sha256"},
                )
                _string(
                    frame["path"],
                    path=f"{path}.retained_artifacts[{index}].artifacts[{artifact_index}].path",
                )
                _string(
                    frame["sha256"],
                    path=f"{path}.retained_artifacts[{index}].artifacts[{artifact_index}].sha256",
                    pattern=_SHA256_RE,
                )
        expected_retained_products = expected_products
        if expected_purpose is not None:
            expected_retained_products = [
                {"product": product, "mode": "artifact-only"}
                for product in (
                    "pokeyellow",
                    "pokeyellow_debug",
                    "pokeyellow_vc",
                    "pokeyellow_phase2_audit",
                )
            ]
        if retained_products != expected_retained_products:
            raise MapBackgroundContentError(
                f"{path}.retained_artifacts: product/mode order or membership drifted"
            )
        records = document["reviews"]
        if not isinstance(records, dict):
            raise MapBackgroundContentError(f"{path}.reviews: expected object")
        expected_record_ids = {
            *(f"tileset-{row['id']}" for row in batch_tilesets),
            *(f"map-{row['id']}" for row in batch_maps),
        }
        if set(records) != expected_record_ids:
            raise MapBackgroundContentError(
                f"{path}.reviews: exact promoted identities required"
            )
        record = _object(
            records.get(record_id),
            path=f"{path}#{record_id}",
            fields={
                "content_kind",
                "content_id",
                "content_name",
                "atlas_sha256",
                "route",
                "revision",
            },
        )
        expected = {
            "content_kind": content_kind,
            "content_id": content_id,
            "content_name": content_name,
            "atlas_sha256": review.atlas_sha256,
            "route": review.route,
            "revision": review.revision,
        }
        if record != expected:
            raise MapBackgroundContentError(
                f"{path}#{record_id}: record does not match ledger review identity"
            )
    except (OSError, json.JSONDecodeError, MapBackgroundContentError) as exc:
        return f"{content_kind} {content_name}: review authority is not durable: {exc}"
    return None


@dataclass(frozen=True, slots=True)
class MapBackgroundAuthority:
    tilesets: tuple[TilesetContentRow, ...]
    maps: tuple[MapContentRow, ...]

    @classmethod
    def from_dict(cls, raw: object) -> MapBackgroundAuthority:
        obj = _object(raw, path="ledger", fields={"schema", "tilesets", "maps"})
        if obj["schema"] != SCHEMA:
            raise MapBackgroundContentError(f"ledger.schema: expected {SCHEMA!r}")
        if not isinstance(obj["tilesets"], list) or not isinstance(obj["maps"], list):
            raise MapBackgroundContentError("ledger tilesets/maps must be arrays")
        authority = cls(
            tilesets=tuple(
                TilesetContentRow.from_raw(row, path=f"tilesets[{i}]")
                for i, row in enumerate(obj["tilesets"])
            ),
            maps=tuple(
                MapContentRow.from_raw(row, path=f"maps[{i}]")
                for i, row in enumerate(obj["maps"])
            ),
        )
        authority._validate_identity_order()
        return authority

    @classmethod
    def load(
        cls, repository_root: Path | str, authority_path: Path | None = None
    ) -> MapBackgroundAuthority:
        root = Path(repository_root)
        path = authority_path or root / LEDGER_PATH
        try:
            raw = _load_json(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MapBackgroundContentError(
                f"{path}: cannot load canonical JSON: {exc}"
            ) from exc
        authority = cls.from_dict(raw)
        findings = authority.reconcile(root)
        if findings:
            raise MapBackgroundContentError("; ".join(findings))
        return authority

    def _validate_identity_order(self) -> None:
        tileset_ids = [row.id for row in self.tilesets]
        tileset_names = [row.name for row in self.tilesets]
        map_keys = [(row.name, row.id) for row in self.maps]
        if tileset_ids != list(range(len(self.tilesets))):
            raise MapBackgroundContentError(
                "tilesets: IDs must be contiguous numeric order"
            )
        if len(tileset_names) != len(set(tileset_names)):
            raise MapBackgroundContentError("tilesets: duplicate name")
        if map_keys != sorted(map_keys):
            raise MapBackgroundContentError(
                "maps: rows must be lexical by name then ID"
            )
        if len(map_keys) != len(set(map_keys)):
            raise MapBackgroundContentError("maps: duplicate identity")
        ids = [row.id for row in self.maps]
        if len(ids) != len(set(ids)):
            raise MapBackgroundContentError("maps: duplicate positional ID")

    def reconcile(self, repository_root: Path | str) -> tuple[str, ...]:
        root = Path(repository_root)
        _validate_const_macro_authority(root)
        discovered_tilesets = _tilesets(root)
        discovered_maps = _maps(root)
        payloads = _payload_pointer_authorities(root, discovered_tilesets)
        roofs = _roof_authorities(root)
        production_roof_region_rules(root)
        production_map_override_rules(root)
        tileset_replacements, map_replacements = _production_replacement_authorities(
            root, discovered_maps
        )
        animation_authorities = _tileset_animation_authorities(
            root, discovered_tilesets
        )
        _validate_production_presentation_predicate(root)
        findings: list[str] = []
        ledger_tilesets = tuple((row.id, row.name) for row in self.tilesets)
        if ledger_tilesets != discovered_tilesets:
            findings.append(
                "tileset identities/order drift from constants/tileset_constants.asm"
            )
        ledger_maps = tuple((row.id, row.name, row.tileset) for row in self.maps)
        source_maps = tuple(
            sorted(
                ((row.id, row.name, row.tileset) for row in discovered_maps),
                key=lambda row: (row[1], row[0]),
            )
        )
        if ledger_maps != source_maps:
            findings.append(
                "map identities/order/tileset joins drift from the concrete source universe"
            )
        tileset_status = {row.name: row.content_status for row in self.tilesets}
        tileset_ids = {name: tileset_id for tileset_id, name in discovered_tilesets}
        for row in self.tilesets:
            palette, attribute = payloads.get(row.name, (None, None))
            if (row.palette_authority, row.attribute_authority) != (
                palette,
                attribute,
            ):
                findings.append(
                    f"tileset {row.name}: payload authorities disagree with "
                    "repository-owned pointer tables"
                )
            expected_missing = palette is None
            if (row.content_status is ContentStatus.MISSING) != expected_missing:
                findings.append(
                    f"tileset {row.name}: content_status disagrees with payload existence"
                )
            expected_batch = _expected_batch(row.name)
            if row.batch != expected_batch:
                findings.append(
                    f"tileset {row.name}: batch is outside the Phase 1 closed partition"
                )
            expected_animations = animation_authorities.get(row.name, ())
            expected_replacements = tileset_replacements.get(row.name, ())
            if row.animations != expected_animations:
                findings.append(
                    f"tileset {row.name}: animations disagree with Phase 1 metadata contract"
                )
            if row.replacements != expected_replacements:
                findings.append(
                    f"tileset {row.name}: replacements disagree with Phase 1 metadata contract"
                )
            if row.review is not None:
                finding = _review_finding(
                    root,
                    content_kind="tileset",
                    content_id=row.id,
                    content_name=row.name,
                    batch=row.batch,
                    batch_tilesets=tuple(
                        {"id": candidate.id, "name": candidate.name}
                        for candidate in self.tilesets
                        if candidate.batch == row.batch
                    ),
                    batch_maps=tuple(
                        {
                            "id": candidate.id,
                            "name": candidate.name,
                            "tileset": candidate.tileset,
                        }
                        for candidate in self.maps
                        if candidate.batch == row.batch
                    ),
                    review=row.review,
                )
                if finding is not None:
                    findings.append(finding)
        for row in self.maps:
            expected = tileset_status.get(row.tileset)
            if expected is None:
                findings.append(f"map {row.name}: unknown tileset {row.tileset}")
            elif row.content_status is not expected:
                findings.append(
                    f"map {row.name}: content_status disagrees with tileset {row.tileset}"
                )
            expected_batch = _expected_batch(row.tileset)
            if row.batch != expected_batch:
                findings.append(
                    f"map {row.name}: batch disagrees with the Phase 1 tileset partition"
                )
            expected_animations = animation_authorities.get(row.tileset, ())
            expected_replacements = map_replacements.get(row.name, ())
            if row.animations != expected_animations:
                findings.append(
                    f"map {row.name}: animations disagree with Phase 1 metadata contract"
                )
            if row.replacements != expected_replacements:
                findings.append(
                    f"map {row.name}: replacements disagree with Phase 1 metadata contract"
                )
            expected_overrides = _MAP_OVERRIDE_IDENTITIES.get(row.name, ())
            if row.overrides != expected_overrides:
                findings.append(
                    f"map {row.name}: overrides disagree with exact production source"
                )
            tileset_id = tileset_ids.get(row.tileset)
            if tileset_id is not None:
                expected_presentation = _production_presentation(
                    tileset_id, row.tileset
                )
                if row.presentation is not expected_presentation:
                    findings.append(
                        f"map {row.name}: presentation disagrees with the unchanged "
                        "production admission predicate"
                    )
            roof_row = roofs.get(row.id)
            expected_roof: str | None = None
            if row.tileset == "OVERWORLD":
                if roof_row is None or roof_row[1] != row.name:
                    findings.append(
                        f"map {row.name}: positional roof source identity is absent or drifted"
                    )
                else:
                    expected_roof = roof_row[0]
            if row.roof != expected_roof:
                findings.append(
                    f"map {row.name}: roof disagrees with repository-owned assignment table"
                )
            if row.content_status is ContentStatus.MISSING:
                expected_fallback = _MISSING_FALLBACK_AUTHORITY
            elif row.presentation is Presentation.YELLOW:
                expected_fallback = _ARCHITECTURE_BOUNDARY_AUTHORITY
            else:
                expected_fallback = None
            actual_fallback = (
                None if row.fallback_reason is None else row.fallback_reason.authority
            )
            if actual_fallback != expected_fallback:
                findings.append(
                    f"map {row.name}: fallback authority lacks exact source identity"
                )
            if row.review is not None:
                finding = _review_finding(
                    root,
                    content_kind="map",
                    content_id=row.id,
                    content_name=row.name,
                    batch=row.batch,
                    batch_tilesets=tuple(
                        {"id": candidate.id, "name": candidate.name}
                        for candidate in self.tilesets
                        if candidate.batch == row.batch
                    ),
                    batch_maps=tuple(
                        {
                            "id": candidate.id,
                            "name": candidate.name,
                            "tileset": candidate.tileset,
                        }
                        for candidate in self.maps
                        if candidate.batch == row.batch
                    ),
                    review=row.review,
                )
                if finding is not None:
                    findings.append(finding)
        return tuple(findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "tilesets": [row.to_dict() for row in self.tilesets],
            "maps": [row.to_dict() for row in self.maps],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

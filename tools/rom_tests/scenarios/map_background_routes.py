"""Bounded natural routes used to review Phase 3 map-background batches.

The declarations are evidence expectations, not acceptance records.  Oak's Lab is
the short natural DOJO/Gym-authority checkpoint for the challenge batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


PRODUCTS = ("pokeyellow", "pokeyellow_debug")
MODES = ("color", "yellow")
# The role is part of the sample's semantic identity, not free-form review prose.
# Keying it to the linked tile/attribute authority makes an allowed but incorrect
# role fail closed (for example, tile $03 is not generic vegetation).
TILE_SAMPLE_PURPOSES = {
    ("FullColorOverworldTileAttributes", 0x03, 1): "animated flower",
    ("FullColorOverworldTileAttributes", 0x2C, 2): "vegetation",
    ("FullColorOverworldTileAttributes", 0x52, 2): "grass edge",
    ("FullColorOverworldTileAttributes", 0x55, 5): "building detail",
    ("FullColorRedsHouseTileAttributes", 0x06, 3): "furniture detail",
    ("FullColorRedsHouseTileAttributes", 0x44, 2): "wall detail",
    ("FullColorPokecenterTileAttributes", 0x0C, 1): "counter edge",
    ("FullColorPokecenterTileAttributes", 0x28, 3): "shop detail",
    ("FullColorGymTileAttributes", 0x0D, 5): "shared bookshelf identity",
    ("FullColorGymTileAttributes", 0x29, 5): "shared counter identity",
}
NATURAL_DRIVERS = {
    "overworld": (
        "reach_bedroom_overworld",
        "select_renderer_mode",
        "walk_from_bedroom_to_oak",
        "follow_oak_and_receive_pikachu",
        "finish_rival_battle_and_leave_lab",
        "walk_from_oaks_lab_to_viridian",
    ),
    "residential-services": (
        "reach_bedroom_overworld",
        "select_renderer_mode",
        "walk_from_bedroom_to_oak",
        "follow_oak_and_receive_pikachu",
        "finish_rival_battle_and_leave_lab",
        "walk_from_oaks_lab_to_viridian",
        "collect_oaks_parcel",
    ),
    "challenge-special-interiors": (
        "reach_bedroom_overworld",
        "select_renderer_mode",
        "walk_from_bedroom_to_oak",
        "follow_oak_and_receive_pikachu",
    ),
}
MAP_IDENTITIES = {
    0x00: "PALLET_TOWN",
    0x01: "VIRIDIAN_CITY",
    0x0C: "ROUTE_1",
    0x26: "REDS_HOUSE_2F",
    0x28: "OAKS_LAB",
    0x2A: "VIRIDIAN_MART",
}


@dataclass(frozen=True, slots=True)
class TileSample:
    tile_id: int
    attribute_authority: str
    expected_attribute: int
    purpose: str


@dataclass(frozen=True, slots=True)
class RouteCheckpoint:
    name: str
    map_id: int
    map_name: str
    coordinates: tuple[int, int]
    tileset: str
    expected_presentation: tuple[str, str]
    expected_effective_mode: tuple[str, str]
    yellow_pointer_ids: tuple[int, int, int, int]
    yellow_palette_ids: tuple[int, int, int, int, int, int, int, int]
    palette_authority: str
    tile_samples: tuple[TileSample, ...]
    retained_screenshot: str
    retained_frame_strip: str


@dataclass(frozen=True, slots=True)
class BatchRoute:
    batch: str
    route: str
    natural_driver: tuple[str, ...]
    checkpoints: tuple[RouteCheckpoint, ...]

    def id_for(self, product: str, mode: str) -> str:
        if product not in PRODUCTS or mode not in MODES:
            raise ValueError("route identity requires a declared product and mode")
        return f"{self.route}/{product}/{mode}"


def _checkpoint(
    batch: str,
    name: str,
    map_id: int,
    map_name: str,
    coordinates: tuple[int, int],
    tileset: str,
    palette: str,
    attributes: str,
    yellow_palette_id: int,
    samples: tuple[tuple[int, int, str], ...],
    *,
    yellow_palette_ids: tuple[int, int, int, int, int, int, int, int] | None = None,
) -> RouteCheckpoint:
    base = f"{batch}/{name}"
    return RouteCheckpoint(
        name=name,
        map_id=map_id,
        map_name=map_name,
        coordinates=coordinates,
        tileset=tileset,
        expected_presentation=("authored-full-color", "yellow-baseline"),
        expected_effective_mode=("color", "yellow"),
        yellow_pointer_ids=(yellow_palette_id, 0, 0, 0),
        yellow_palette_ids=yellow_palette_ids or (yellow_palette_id,) * 8,
        palette_authority=palette,
        tile_samples=tuple(
            TileSample(tile_id, attributes, expected_attribute, purpose)
            for tile_id, expected_attribute, purpose in samples
        ),
        retained_screenshot=f"{base}/screenshot.png",
        retained_frame_strip=f"{base}/frame-strip.png",
    )


BATCH_ROUTES = (
    BatchRoute(
        batch="overworld",
        route="phase3-overworld-pallet-route1-viridian",
        natural_driver=NATURAL_DRIVERS["overworld"],
        checkpoints=(
            _checkpoint(
                "overworld",
                "pallet-after-lab",
                0x00,
                "PALLET_TOWN",
                (12, 12),
                "OVERWORLD",
                "FullColorOverworldBGPalettes",
                "FullColorOverworldTileAttributes",
                1,
                ((0x03, 1, "animated flower"), (0x2C, 2, "vegetation")),
                yellow_palette_ids=(1, 0, 0, 0, 1, 1, 1, 1),
            ),
            _checkpoint(
                "overworld",
                "route1-mid",
                0x0C,
                "ROUTE_1",
                (15, 9),
                "OVERWORLD",
                "FullColorOverworldBGPalettes",
                "FullColorOverworldTileAttributes",
                0,
                ((0x03, 1, "animated flower"), (0x52, 2, "grass edge")),
                yellow_palette_ids=(0, 0, 0, 0, 1, 1, 1, 1),
            ),
            _checkpoint(
                "overworld",
                "viridian-entry",
                0x01,
                "VIRIDIAN_CITY",
                (35, 20),
                "OVERWORLD",
                "FullColorOverworldBGPalettes",
                "FullColorOverworldTileAttributes",
                2,
                ((0x2C, 2, "vegetation"), (0x55, 5, "building detail")),
                yellow_palette_ids=(2, 0, 0, 0, 1, 1, 1, 1),
            ),
        ),
    ),
    BatchRoute(
        batch="residential-services",
        route="phase3-residential-bedroom-mart",
        natural_driver=NATURAL_DRIVERS["residential-services"],
        checkpoints=(
            _checkpoint(
                "residential-services",
                "bedroom",
                0x26,
                "REDS_HOUSE_2F",
                (6, 3),
                "REDS_HOUSE_2",
                "FullColorIndoorBGPalettes",
                "FullColorRedsHouseTileAttributes",
                1,
                ((0x06, 3, "furniture detail"), (0x44, 2, "wall detail")),
            ),
            _checkpoint(
                "residential-services",
                "viridian-mart",
                0x2A,
                "VIRIDIAN_MART",
                (5, 2),
                "MART",
                "FullColorIndoorPCBGPalettes",
                "FullColorPokecenterTileAttributes",
                2,
                ((0x0C, 1, "counter edge"), (0x28, 3, "shop detail")),
            ),
        ),
    ),
    BatchRoute(
        batch="challenge-special-interiors",
        route="phase3-challenge-oaks-lab-dojo",
        natural_driver=NATURAL_DRIVERS["challenge-special-interiors"],
        checkpoints=(
            _checkpoint(
                "challenge-special-interiors",
                "oaks-lab-dojo",
                0x28,
                "OAKS_LAB",
                (3, 5),
                "DOJO",
                "FullColorIndoorBGPalettes",
                "FullColorGymTileAttributes",
                1,
                (
                    (0x0D, 5, "shared bookshelf identity"),
                    (0x29, 5, "shared counter identity"),
                ),
            ),
        ),
    ),
)

ROUTES_BY_BATCH = {route.batch: route for route in BATCH_ROUTES}


def _normalized_retained_path(path: str) -> str:
    candidate = PurePosixPath(path)
    if (
        not path
        or "\\" in path
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.as_posix() != path
    ):
        raise ValueError(f"retained artifact path is not normalized: {path!r}")
    return path


def _route_retained_paths(route: BatchRoute) -> tuple[str, ...]:
    return tuple(
        _normalized_retained_path(f"{route.id_for(product, mode)}/{relative_name}")
        for product in PRODUCTS
        for mode in MODES
        for checkpoint in route.checkpoints
        for relative_name in (
            _normalized_retained_path(checkpoint.retained_screenshot),
            _normalized_retained_path(checkpoint.retained_frame_strip),
        )
    )


def validate_route(route: BatchRoute) -> None:
    if route.natural_driver != NATURAL_DRIVERS.get(route.batch):
        raise ValueError(f"{route.batch}: replay driver metadata is not exact")
    if not route.checkpoints:
        raise ValueError(f"{route.batch}: route has no checkpoint")
    names = [checkpoint.name for checkpoint in route.checkpoints]
    if len(names) != len(set(names)):
        raise ValueError(f"{route.batch}: duplicate checkpoint")
    for checkpoint in route.checkpoints:
        if MAP_IDENTITIES.get(checkpoint.map_id) != checkpoint.map_name:
            raise ValueError(
                f"{route.batch}/{checkpoint.name}: map identity is not exact"
            )
        if checkpoint.expected_presentation != (
            "authored-full-color",
            "yellow-baseline",
        ):
            raise ValueError(f"{route.batch}/{checkpoint.name}: wrong presentation")
        if checkpoint.expected_effective_mode != ("color", "yellow"):
            raise ValueError(f"{route.batch}/{checkpoint.name}: wrong effective mode")
        if len(checkpoint.yellow_pointer_ids) != 4:
            raise ValueError(f"{route.batch}/{checkpoint.name}: wrong pointer count")
        if len(checkpoint.yellow_palette_ids) != 8:
            raise ValueError(f"{route.batch}/{checkpoint.name}: wrong palette count")
        if not checkpoint.tile_samples:
            raise ValueError(f"{route.batch}/{checkpoint.name}: no tile samples")
        if any(
            not 0 <= sample.expected_attribute <= 7
            for sample in checkpoint.tile_samples
        ):
            raise ValueError(f"{route.batch}/{checkpoint.name}: invalid attribute")
        for sample in checkpoint.tile_samples:
            identity = (
                sample.attribute_authority,
                sample.tile_id,
                sample.expected_attribute,
            )
            if TILE_SAMPLE_PURPOSES.get(identity) != sample.purpose:
                raise ValueError(
                    f"{route.batch}/{checkpoint.name}: sample purpose is not exact"
                )
        if not checkpoint.retained_screenshot.endswith("/screenshot.png"):
            raise ValueError("checkpoint screenshot identity is not durable")
        if not checkpoint.retained_frame_strip.endswith("/frame-strip.png"):
            raise ValueError("checkpoint frame-strip identity is not durable")
    retained_paths = _route_retained_paths(route)
    if len(retained_paths) != len(set(retained_paths)):
        raise ValueError("retained artifact paths must be globally unique")


def validate_routes() -> None:
    expected = {
        "overworld",
        "residential-services",
        "challenge-special-interiors",
    }
    if set(ROUTES_BY_BATCH) != expected or len(ROUTES_BY_BATCH) != len(BATCH_ROUTES):
        raise ValueError("Phase 3 routes must form one exact batch partition")
    retained_paths: list[str] = []
    for route in BATCH_ROUTES:
        validate_route(route)
        retained_paths.extend(_route_retained_paths(route))
    if len(retained_paths) != len(set(retained_paths)):
        raise ValueError("retained artifact paths must be globally unique")


validate_routes()

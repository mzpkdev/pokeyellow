# Scope and ownership boundary

This document defines the included production scenes. Mandatory owner,
handoff, reconstruction, and write behavior remains defined in
[requirements.md](requirements.md).

## Bounded production inclusion

Color production scope is only ordinary base-map presentation in the 34 city
and route maps whose headers select `OVERWORLD` plus conventional interiors
using tileset IDs `REDS_HOUSE_1` through `FACILITY`, excluding `FOREST`,
`SHIP_PORT`, and `CAVERN` (19 tilesets and 162 maps), while the saved preference
is `COLOR`. `PLATEAU` and `BEACH_HOUSE`
remain unsupported. Within those intervals the passive Color layer includes:

- the supported maps' CGB BG palettes, map-specific roof palettes, and tile-ID-to-attribute data;
- initial map entry and reload, horizontal and vertical scrolling, and the
  connections between supported maps; and
- restoration of the authored background after Yellow-owned overlays close.

Yellow remains authoritative for bank-0 tile graphics, animation and field-
replacement tile data, OAM and sprites, mechanics, overlay/menu construction,
fade progression, timing, battles, and cutscenes. The shipped passive layer may
project paired bank-1 attributes for its explicitly integrated overlays and
transform authored BG palettes at Yellow's fade seam without entering retained
Color ownership.

The saved preference is policy input only. It never grants write authority.
The effective-owner rules below describe the retained renderer target. In the
shipped passive product, `COLOR` is a presentation policy label rather than an
acquired `RENDERER_FULL_COLOR_OVERWORLD` token: the retained owner stays Yellow
and the bounded hooks may write only the palette/attribute resources listed
above.
The effective background presentation is Color if and only if the preference
is `COLOR`, the lifecycle is ordinary map presentation, and the map is in the
supported outdoor/conventional-interior slice.
Every other cell is Yellow-owned. Exactly one effective owner is selected at
every instant.

## Yellow-owned production scope

Yellow's existing renderer continues to own:

- every map, including supported `OVERWORLD` maps, under `YELLOW` preference;
- every unsupported map under either preference;
- boot, reset, soft reset, new-game, and continue presentation;
- dialogue, text boxes, and transient start, list, yes/no, field-move, and
  other menu or overlay presentation;
- battle backgrounds, HUD, Pokémon, trainers, transitions, and animations;
- title, splash, Oak speech, Yellow intro, and credits;
- party, status, Pokédex, town map, trainer card, naming, and PC screens;
- evolution, Hall of Fame, and trade presentation;
- slots, printer, and link-room presentation;
- Pikachu front-picture and emotion-picture screens;
- Pikachu's Beach and Surfing Pikachu; and
- any other standalone or unlisted lifecycle.

Follower Pikachu and every other sprite remain Yellow-owned in all contexts.

## Classification and ownership rule

`ORDINARY_BASE_MAP` means the ordinary simulation and viewport of a supported
map without dialogue, text, a menu, or any other overlay active.
`FORCED_YELLOW` means any overlay, dialogue, menu, battle, standalone,
boot/reset, unsupported-map, or `YELLOW`-preference lifecycle.
`SCENE_BOUNDARY` means a concrete directed edge on which the effective owner
changes. A real owner change completes the ordered handoff and destination
reconstruction contract before the arriving owner's first display write.

`OVERWORLD_OVERLAY` is reserved and unreachable in this bounded production
product. An overlay never acquires or preserves retained Color ownership and
never enters the retained Color scheduler pipeline. In the shipped passive
product, selected Yellow-owned dialogue, Start/Options, two-option, and
Pokecenter redisplay structures may receive a paired bank-1 projection while
the passive base-map presentation remains latched. A Yellow full-screen
attribute packet instead suspends projection and invalidates the passive base
certificate until explicit reconstruction. A retained-owner implementation
would use the complete handoffs below; passive projection does not invent such
an owner transition.

Every unlisted lifecycle or directed transition must receive a reviewed
`SC-...` row in [replacement-inventory.md](replacement-inventory.md) before an
implementation phase makes it reachable, as required by
[R12.8](requirements.md#r12-isolation-and-removal).

Owner selection is defined by
[R1.1 and R1.29-R1.33](requirements.md#r1-renderer-ownership).
Transition and reconstruction behavior is defined by
[R2.1-R2.13](requirements.md#r2-generation-handoff-reset-and-reconstruction).

## Scene-lifecycle table

| Lifecycle or directed edge | Classification | Effective owner or transfer |
|---|---|---|
| ordinary supported `OVERWORLD` map presentation with `COLOR` preference | `ORDINARY_BASE_MAP` | Color |
| ordinary supported interior map presentation with `COLOR` preference | `ORDINARY_BASE_MAP` | Color |
| ordinary supported `OVERWORLD` map presentation with `YELLOW` preference | `FORCED_YELLOW` | Yellow |
| ordinary supported interior map presentation with `YELLOW` preference | `FORCED_YELLOW` | Yellow |
| any unsupported map under either preference | `FORCED_YELLOW` | Yellow |
| dialogue, text, menu, or transient overlay on any map | `FORCED_YELLOW` | Yellow construction; selected shipped seams may receive paired passive bank-1 projection; `OVERWORLD_OVERLAY` is unreachable |
| battle or standalone presentation | `FORCED_YELLOW` | Yellow |
| boot, reset, soft reset, new-game, or continue presentation | `FORCED_YELLOW` | Yellow |
| retained Color-owned base presentation to any forced-Yellow context | `SCENE_BOUNDARY` | complete Color-to-Yellow handoff |
| Yellow-owned context to eligible retained Color presentation with `COLOR` preference | `SCENE_BOUNDARY` | complete Yellow-to-Color handoff |
| supported-map connection while Color remains effective | `ORDINARY_BASE_MAP` | Color to Color; no handoff |
| any edge whose effective owner remains Yellow | `FORCED_YELLOW` | Yellow to Yellow; no handoff |

## Quarantined diagnostic and future material

The completed all-25-tileset palette/attribute corpus, overlay request oracle,
precedence and clipping matrices, and diagnostic `OVERWORLD_OVERLAY` model may
remain as content, synthetic-conformance, or audit evidence only. They are
explicitly non-production and non-gating for this bounded release. They cannot
expand the supported-map allowlist, make a production Color overlay reachable,
select an owner, or authorize any production write.

The completed Color authoring for maps using other tilesets does not make those
maps production-eligible. Color rendering of those maps, dialogue, text, menus,
or overlays is future product work and requires a separately reviewed scope
change.

## Compatibility

Backward compatibility is not a goal. The project may:

- become CGB-only;
- reject DMG/SGB execution;
- change ROM and renderer RAM layout;
- remove only obsolete competing overworld ownership or repair APIs;
- discard the failed full-color-overworld runtime implementation; and
- change save format if a later implementation has a concrete reviewed reason.

Required Yellow paths remain because `YELLOW` preference and every
forced-Yellow context depend on them. Non-Color behavior is protected by
baseline and handoff regression gates.

## Forbidden scope growth

Implementation work must not expand into:

- retained Color ownership of dialogue, text, menus, or overlays;
- recoloring battles or battle animations;
- species/trainer picture palettes;
- standalone menu redesign;
- title/intro/minigame renderer replacement;
- Color ownership outside ordinary presentation of the supported map slice;
- treating the preference as write authority; or
- concurrent or overlapping ownership by the two renderers.

Yellow-owned tests are baseline, policy, handoff, return, and regression tests
only. Diagnostic and future authoring evidence cannot satisfy or enlarge the
bounded production acceptance gate.

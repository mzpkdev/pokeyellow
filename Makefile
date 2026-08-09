roms := \
	pokeyellow.gbc \
	pokeyellow_debug.gbc
patches := \
	pokeyellow.patch

rom_obj := \
	audio.o \
	home.o \
	main.o \
	maps.o \
	ram.o \
	text.o \
	gfx/pics.o \
	gfx/pikachu.o \
	gfx/sprites.o \
	gfx/surfing_pikachu.o \
	gfx/tilesets.o

pokeyellow_obj       := $(rom_obj)
pokeyellow_debug_obj := $(rom_obj:.o=_debug.o)
pokeyellow_phase2_audit_obj := $(rom_obj:.o=_phase2_audit.o)
pokeyellow_vc_obj    := $(rom_obj:.o=_vc.o)


### Build tools

ifeq (,$(shell command -v sha1sum 2>/dev/null))
SHA1 := shasum
else
SHA1 := sha1sum
endif

RGBDS ?=
RGBASM  ?= $(RGBDS)rgbasm
RGBFIX  ?= $(RGBDS)rgbfix
RGBGFX  ?= $(RGBDS)rgbgfx
RGBLINK ?= $(RGBDS)rgblink
PYTHON  ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

RGBASMFLAGS  ?= -Weverything -Wtruncation=1
RGBLINKFLAGS ?= -Weverything -Wtruncation=1
RGBFIXFLAGS  ?= -Weverything
RGBGFXFLAGS  ?= -Weverything


### Build targets

.SUFFIXES:
.SECONDEXPANSION:
.PRECIOUS:
.SECONDARY:
.PHONY: \
	all \
	yellow \
	yellow_debug \
	yellow_phase2_audit \
	yellow_vc \
	clean \
	tidy \
	compare \
	tools \
	test-full-color-setup \
	measure-full-color-phase1 \
	measure-full-color-source-transition \
	measure-full-color-audit-evidence-identities \
	measure-full-color-phase2-audit \
	_rom-test-debug-products \
	_rom-test-gameplay-products \
	_rom-test-all-products \
	test-unit \
	test-full-color-content-contract \
	test-full-color-donor-contract \
	test-full-color-harness-contracts \
	test-full-color-evidence \
	test-full-color-audit \
	test-full-color-renderer-contracts \
	test-full-color-renderer-runtime \
	test-full-color-smoke \
	test-full-color-e2e-core \
	test-full-color-e2e-renderer \
	test-full-color-e2e-journey \
	test-full-color-fast \
	test-full-color-certify \
	test-full-color-handoffs \
	test-full-color-soak

all: $(roms)
yellow:       pokeyellow.gbc
yellow_debug: pokeyellow_debug.gbc
yellow_phase2_audit: pokeyellow_phase2_audit.gbc
yellow_vc:    pokeyellow.patch

clean: tidy
	find gfx \
	     \( -iname '*.1bpp' \
	        -o -iname '*.2bpp' \
	        -o -iname '*.pic' \) \
	     -delete
	find audio/pikachu_cries \
	     \( -iname '*.pcm' \) \
	     -delete

tidy:
	$(RM) $(roms) \
	      $(roms:.gbc=.sym) \
	      $(roms:.gbc=.map) \
	      $(patches) \
	      $(patches:.patch=_vc.gbc) \
	      $(patches:.patch=_vc.sym) \
	      $(patches:.patch=_vc.map) \
	      $(patches:%.patch=vc/%.constants.sym) \
	      pokeyellow_phase2_audit.gbc \
	      pokeyellow_phase2_audit.sym \
	      pokeyellow_phase2_audit.map \
	      $(pokeyellow_obj) \
	      $(pokeyellow_vc_obj) \
	      $(pokeyellow_debug_obj) \
	      $(pokeyellow_phase2_audit_obj) \
	      rgbdscheck.o
	$(MAKE) clean -C tools/

compare: $(roms) $(patches)
	@$(SHA1) -c roms.sha1

tools:
	$(MAKE) -C tools/

FULL_COLOR_EVIDENCE_RESULTS ?= test-results/full-color-evidence
FULL_COLOR_CONTRACT_RESULTS ?= test-results/full-color-contracts
FULL_COLOR_SMOKE_RESULTS ?= test-results/full-color-smoke
FULL_COLOR_RENDERER_CONTRACT_RESULTS ?= test-results/full-color-renderer-contracts
FULL_COLOR_RUNTIME_RESULTS ?= test-results/full-color-renderer-runtime
FULL_COLOR_HARNESS_RESULTS ?= test-results/full-color-harness
FULL_COLOR_PROPOSALS ?= test-results/full-color-proposals
ROM_TEST_PREBUILT_PRODUCTS ?= 0

ROM_TEST_DEBUG_PRODUCTS := \
	pokeyellow_debug.gbc pokeyellow_debug.map pokeyellow_debug.sym
ROM_TEST_GAMEPLAY_PRODUCTS := \
	pokeyellow.gbc pokeyellow.map pokeyellow.sym \
	$(ROM_TEST_DEBUG_PRODUCTS)
ROM_TEST_ALL_PRODUCTS := \
	$(ROM_TEST_GAMEPLAY_PRODUCTS) \
	pokeyellow_vc.gbc pokeyellow_vc.map pokeyellow_vc.sym \
	pokeyellow_phase2_audit.gbc pokeyellow_phase2_audit.map pokeyellow_phase2_audit.sym

define require-rom-test-products
	@missing=0; \
	for artifact in $(1); do \
		if [ ! -f "$$artifact" ]; then \
			echo "Missing required ROM test artifact: $$artifact" >&2; \
			missing=1; \
		fi; \
	done; \
	test "$$missing" -eq 0
endef

ifeq ($(ROM_TEST_PREBUILT_PRODUCTS),1)
_rom-test-debug-products:
	$(call require-rom-test-products,$(ROM_TEST_DEBUG_PRODUCTS))

_rom-test-gameplay-products:
	$(call require-rom-test-products,$(ROM_TEST_GAMEPLAY_PRODUCTS))

_rom-test-all-products:
	$(call require-rom-test-products,$(ROM_TEST_ALL_PRODUCTS))
else
_rom-test-debug-products: yellow_debug

_rom-test-gameplay-products: yellow yellow_debug

_rom-test-all-products: yellow yellow_debug yellow_vc yellow_phase2_audit
endif

measure-full-color-phase1: yellow_debug
	$(PYTHON) -m tools.rom_tests.full_color.phase1_measurements --root . --output "$(FULL_COLOR_PROPOSALS)/phase1-ownership-placement.proposal.json"

measure-full-color-source-transition: yellow yellow_debug yellow_vc yellow_phase2_audit
	$(PYTHON) -m tools.rom_tests.full_color.source_transition --root . --proposal-output "$(FULL_COLOR_PROPOSALS)/phase1-source-transition.proposal.json"

measure-full-color-audit-evidence-identities: measure-full-color-source-transition
	$(PYTHON) -m tools.rom_tests.full_color.audit_evidence_identities --root . --transition-proposal "$(FULL_COLOR_PROPOSALS)/phase1-source-transition.proposal.json" --proposal-output "$(FULL_COLOR_PROPOSALS)/audit-evidence-identities.proposal.json"

measure-full-color-phase2-audit: measure-full-color-audit-evidence-identities
	$(PYTHON) -m tools.rom_tests.full_color.phase2_measurements --root . --proposal-output "$(FULL_COLOR_PROPOSALS)/phase2-subjects.proposal.json"

test-full-color-setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r tools/rom_tests/requirements.txt

test-unit: _rom-test-all-products
	$(PYTHON) -m pytest tools/rom_tests/tests/unit \
		--ignore=tools/rom_tests/tests/unit/full_color/test_overworld_color_data_donor.py -q

test-full-color-content-contract:
	$(PYTHON) -m pytest \
		tools/rom_tests/tests/unit/full_color/test_map_background_content.py -q

test-full-color-donor-contract:
	@test -n "$(POKERED_GBC_ROOT)" || \
		{ echo "POKERED_GBC_ROOT is required" >&2; exit 1; }
	POKERED_GBC_ROOT="$(POKERED_GBC_ROOT)" $(PYTHON) -m pytest \
		tools/rom_tests/tests/unit/full_color/test_overworld_color_data_donor.py -q

test-full-color-harness-contracts: _rom-test-debug-products
	$(PYTHON) -m tools.rom_tests.full_color.baseline_discovery --repository .
	$(PYTHON) -m tools.rom_tests.full_color.baseline_inventory --repository .
	$(PYTHON) -m tools.rom_tests.full_color.bank_torture --rom pokeyellow_debug.gbc

test-full-color-evidence: _rom-test-debug-products
	$(PYTHON) -m tools.rom_tests.full_color.evidence_runner \
		--root . --results "$(FULL_COLOR_EVIDENCE_RESULTS)"

test-full-color-audit: _rom-test-all-products
	$(PYTHON) -m tools.rom_tests.full_color.phase2_measurements --root . --output specs/full-colors/evidence/phase2-hostile-slice-representation.json --verify

test-full-color-renderer-contracts:
	$(PYTHON) -m tools.rom_tests.full_color.renderer_conformance_runner --root . --results "$(FULL_COLOR_RENDERER_CONTRACT_RESULTS)"

test-full-color-renderer-runtime: _rom-test-debug-products
	$(PYTHON) -m tools.rom_tests.full_color.renderer_runtime_runner --root . --results "$(FULL_COLOR_RUNTIME_RESULTS)"

test-full-color-smoke: _rom-test-debug-products
	$(PYTHON) -m tools.rom_tests.full_color.runtime_observability --root . --results "$(FULL_COLOR_SMOKE_RESULTS)"

test-full-color-e2e-core: _rom-test-gameplay-products
	$(PYTHON) -m pytest tools/rom_tests/tests/e2e/core -q

test-full-color-e2e-renderer: _rom-test-gameplay-products
	$(PYTHON) -m pytest tools/rom_tests/tests/e2e/renderer -q

test-full-color-e2e-journey: _rom-test-gameplay-products
	$(PYTHON) -m pytest tools/rom_tests/tests/e2e/journey -q

test-full-color-fast:
	@$(PYTHON) -m tools.rom_tests.full_color.harness_runner --profile fast --root . --results "$(FULL_COLOR_HARNESS_RESULTS)"

test-full-color-certify:
	@$(PYTHON) -m tools.rom_tests.full_color.harness_runner --profile certify --root . --results "$(FULL_COLOR_HARNESS_RESULTS)"

test-full-color-handoffs:
	$(PYTHON) -m pytest tools/rom_tests/tests/unit/full_color/test_model.py -k 'handoff or reconstruction or reset'

test-full-color-soak:
	$(PYTHON) -m pytest tools/rom_tests/tests/unit/full_color/test_model.py -k seeded_valid_sequences


RGBASMFLAGS += -Q8 -P includes.asm
# Create a sym/map for debug purposes if `make` run with `DEBUG=1`
ifeq ($(DEBUG),1)
RGBASMFLAGS += -E
endif

$(pokeyellow_debug_obj): RGBASMFLAGS += -D _DEBUG
$(pokeyellow_phase2_audit_obj): RGBASMFLAGS += -D _DEBUG -D PHASE2_AUDIT
$(pokeyellow_vc_obj):    RGBASMFLAGS += -D _YELLOW_VC

%.patch: %_vc.gbc %.gbc vc/%.patch.template
	tools/make_patch $*_vc.sym $^ $@

rgbdscheck.o: rgbdscheck.asm
	$(RGBASM) -o $@ $<

# Build tools when building the rom.
# This has to happen before the rules are processed, since that's when scan_includes is run.
ifeq (,$(filter clean tidy tools,$(MAKECMDGOALS)))

$(info $(shell $(MAKE) -C tools))

# The dep rules have to be explicit or else missing files won't be reported.
# As a side effect, they're evaluated immediately instead of when the rule is invoked.
# It doesn't look like $(shell) can be deferred so there might not be a better way.
preinclude_deps := includes.asm $(shell tools/scan_includes includes.asm)
define DEP
$1: $2 $$(shell tools/scan_includes $2) $(preinclude_deps) | rgbdscheck.o
	$$(RGBASM) $$(RGBASMFLAGS) -o $$@ $$<
endef

# Dependencies for objects
$(foreach obj, $(pokeyellow_obj), $(eval $(call DEP,$(obj),$(obj:.o=.asm))))
$(foreach obj, $(pokeyellow_debug_obj), $(eval $(call DEP,$(obj),$(obj:_debug.o=.asm))))
$(foreach obj, $(pokeyellow_phase2_audit_obj), $(eval $(call DEP,$(obj),$(obj:_phase2_audit.o=.asm))))
$(foreach obj, $(pokeyellow_vc_obj), $(eval $(call DEP,$(obj),$(obj:_vc.o=.asm))))

endif


pokeyellow.gbc:       RGBLINKFLAGS += -p 0x00
pokeyellow_debug.gbc: RGBLINKFLAGS += -p 0xff
pokeyellow_phase2_audit.gbc: RGBLINKFLAGS += -p 0xff
pokeyellow_vc.gbc:    RGBLINKFLAGS += -p 0x00

RGBFIXFLAGS += -Cjsv -k 01 -l 0x33 -m MBC5+RAM+BATTERY -r 03 -t "POKEMON YELLOW"
pokeyellow.gbc:       RGBFIXFLAGS += -p 0x00
pokeyellow_debug.gbc: RGBFIXFLAGS += -p 0xff
pokeyellow_phase2_audit.gbc: RGBFIXFLAGS += -p 0xff
pokeyellow_vc.gbc:    RGBFIXFLAGS += -p 0x00

%.gbc: $$(%_obj) layout.link
	$(RGBLINK) $(RGBLINKFLAGS) -l layout.link -m $*.map -n $*.sym -o $@ $(filter %.o,$^)
	$(RGBFIX) $(RGBFIXFLAGS) $@


### Misc file-specific graphics rules

gfx/battle/move_anim_0.2bpp: tools/gfx += --trim-whitespace
gfx/battle/move_anim_1.2bpp: tools/gfx += --trim-whitespace

gfx/credits/the_end.2bpp: tools/gfx += --interleave --png=$<

gfx/diploma/diploma.2bpp: tools/gfx += --trim-whitespace

gfx/slots/slots_1.2bpp: tools/gfx += --trim-whitespace

gfx/tilesets/%.2bpp: tools/gfx += --trim-whitespace
gfx/tilesets/reds_house.2bpp: tools/gfx += --preserve=0x48

gfx/title/pokemon_logo.2bpp: tools/gfx += --trim-whitespace

gfx/trade/game_boy.2bpp: tools/gfx += --remove-duplicates

gfx/sgb/border.2bpp: tools/gfx += --trim-whitespace

gfx/surfing_pikachu/surfing_pikachu_1c.2bpp: tools/gfx += --trim-whitespace


### Catch-all graphics rules

%.2bpp: %.png
	$(RGBGFX) --colors dmg $(RGBGFXFLAGS) -o $@ $<
	$(if $(tools/gfx),\
		tools/gfx $(tools/gfx) -o $@ $@ || $$($(RM) $@ && false))

%.1bpp: %.png
	$(RGBGFX) --colors dmg $(RGBGFXFLAGS) --depth 1 -o $@ $<
	$(if $(tools/gfx),\
		tools/gfx $(tools/gfx) --depth 1 -o $@ $@ || $$($(RM) $@ && false))

%.pic: %.2bpp
	tools/pkmncompress $< $@


### Catch-all audio rules

%.pcm: %.wav
	tools/pcm $< $@


### File extensions that are never generated and should be manually created

%.asm: ;
%.inc: ;
%.png: ;
%.pal: ;
%.bin: ;
%.blk: ;
%.bst: ;
%.rle: ;
%.wav: ;

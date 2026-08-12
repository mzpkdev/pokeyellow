#include <errno.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "Core/gb.h"

/* SameBoy v1.0.3 exports this debugger symbol-table entry point from the
 * pinned static library but omits it from the public header. */
#define DRIVER_VERSION "sameboy-phase5-driver-v1"
#define SCREEN_WIDTH 160
#define SCREEN_HEIGHT 144
#define MAX_SAMPLES 1024
#define STRESS_BYTES 11
#define SCENARIO_BYTES 11
#define TRACE_BYTES 194
#define MAX_PAIRED_PAYLOAD_BYTES 720
#define DESCRIPTOR_BYTES 20
#define DESCRIPTOR_CAPACITY 8
#define KEY1_ADDRESS 0xFF4D
#define SVBK_ADDRESS 0xFF70
#define LY_ADDRESS 0xFF44
#define STAT_ADDRESS 0xFF41
#define IE_ADDRESS 0xFFFF
#define IF_ADDRESS 0xFF0F
#define CALIBRATION_NOPS 16
#define MAX_DIAGNOSTIC_BREAKPOINTS 32

typedef struct {
    uint16_t bank;
    uint16_t address;
    bool found;
} symbol_t;

typedef struct {
    uint64_t ticks;
    uint64_t start_offset;
    uint64_t end_offset;
    uint64_t deadline_offset;
    uint32_t public_target_writes;
    uint32_t preparation_buffer_writes;
    uint32_t post_end_public_target_writes;
    uint32_t semantic_unit_public_target_writes;
    uint8_t active_descriptor_state_at_end;
    uint8_t active_descriptor_state_at_deadline;
    uint8_t fast_cache_valid_at_end;
    uint8_t fast_cache_valid_at_deadline;
    uint8_t request_count_at_end;
    uint8_t request_count_at_deadline;
    uint16_t active_descriptor_address_at_end;
    uint16_t active_descriptor_address_at_deadline;
    uint16_t active_descriptor_destination_at_end;
    uint16_t active_descriptor_destination_at_deadline;
    uint8_t key1;
    uint8_t end_ly;
    uint8_t end_stat;
    uint8_t deadline_ly;
    uint8_t deadline_stat;
    uint8_t stress[STRESS_BYTES];
    uint8_t scenario[SCENARIO_BYTES];
    uint8_t post_scenario[SCENARIO_BYTES];
    uint8_t post_owner;
    uint8_t post_phase;
    uint8_t trace[TRACE_BYTES];
    uint8_t presentation_trace[TRACE_BYTES];
    uint8_t descriptor_class;
    uint8_t descriptor_width;
    uint8_t descriptor_height;
    uint16_t descriptor_extent;
    uint16_t descriptor_reservation;
    bool descriptor_found;
    uint8_t descriptor_snapshot[DESCRIPTOR_BYTES];
    bool descriptor_snapshot_found;
    uint16_t descriptor_home_address;
    uint8_t descriptor_home_state;
    uint8_t descriptor_home_cache;
    uint32_t descriptor_home_post_end_public_writes;
    bool descriptor_home_seen;
    uint16_t descriptor_deferred_address;
    uint8_t descriptor_deferred_state;
    uint8_t descriptor_deferred_cache;
    bool descriptor_deferred_seen;
    uint8_t enqueued_mask_at_end;
    uint8_t drained_mask_at_end;
    uint8_t enqueued_mask_at_deadline;
    uint8_t drained_mask_at_deadline;
    uint16_t available_cycles_at_end;
    uint16_t required_cycles_at_end;
    uint16_t available_cycles_at_deadline;
    uint16_t required_cycles_at_deadline;
    uint8_t producer_class;
    uint8_t producer_width;
    uint8_t producer_height;
    uint16_t producer_destination;
    uint16_t producer_extent;
    uint16_t producer_payload_bytes;
    uint8_t producer_payload[MAX_PAIRED_PAYLOAD_BYTES];
    bool producer_snapshot_found;
    unsigned retry_admit_hits;
    unsigned retry_finish_hits;
    unsigned retry_publish_hits;
    uint8_t retry_publish_result;
    uint16_t producer_bound_descriptor_address;
    uint16_t producer_bound_descriptor_destination;
    uint8_t producer_bound_descriptor_state;
} sample_t;

typedef struct {
    uint64_t nop_ticks;
    uint64_t scanline_ticks;
    uint64_t scanline_register_ticks;
    uint64_t vblank_ticks;
    uint64_t frame_ticks;
} calibration_t;

typedef struct {
    const char *rom;
    const char *sym;
    const char *boot_rom;
    const char *json;
    const char *frame_dir;
    const char *start_label;
    const char *end_label;
    const char *origin_label;
    const char *deadline_label;
    const char *deadline_kind;
    const char *movement_axis;
    const char *control_symbol;
    const char *scenario_symbol;
    const char *stress_symbol;
    const char *scenario_state_symbol;
    const char *trace_symbol;
    unsigned scenario_value;
    unsigned control_value;
    unsigned state_stable_value;
    unsigned state_complete_value;
    unsigned result_passed_value;
    unsigned ledger_all_value;
    unsigned barrier_stable_value;
    unsigned yellow_owner_value;
    unsigned yellow_phase_value;
    unsigned color_owner_value;
    unsigned color_phase_value;
    unsigned descriptor_class_value;
    unsigned oam_class_value;
    unsigned descriptor_committing_value;
    unsigned descriptor_complete_value;
    unsigned samples;
    unsigned warmup_frames;
    unsigned max_frames;
    const char *diagnostic_labels[MAX_DIAGNOSTIC_BREAKPOINTS];
    unsigned diagnostic_count;
} options_t;

typedef enum {
    EXPECT_ORIGIN,
    EXPECT_START,
    EXPECT_END,
    EXPECT_DEADLINE,
} expected_breakpoint_t;

typedef struct {
    options_t options;
    GB_gameboy_t *gb;
    symbol_t control;
    symbol_t origin;
    symbol_t operation_start;
    symbol_t operation_end;
    symbol_t deadline;
    symbol_t owner_end;
    symbol_t deferred_accounting_start;
    symbol_t scenario;
    symbol_t stress;
    symbol_t scenario_state;
    symbol_t trace;
    symbol_t top_menu_y;
    symbol_t top_menu_x;
    symbol_t max_menu_item;
    symbol_t watched_keys;
    symbol_t current_menu_item;
    symbol_t current_map;
    symbol_t x_coord;
    symbol_t y_coord;
    symbol_t status_flags6;
    symbol_t oaks_lab_script;
    symbol_t party_count;
    symbol_t shadow_oam;
    symbol_t preparation_start;
    symbol_t preparation_end;
    symbol_t request_descriptors;
    symbol_t active_descriptor;
    symbol_t request_cursor;
    symbol_t producer_pending;
    symbol_t producer_tiles;
    symbol_t producer_attributes;
    symbol_t producer_destination;
    symbol_t producer_width;
    symbol_t producer_height;
    symbol_t producer_class;
    symbol_t fast_cache_valid;
    symbol_t fast_cache_descriptor;
    symbol_t fast_cache_snapshot;
    symbol_t fast_cache_required_cycles;
    symbol_t request_count;
    symbol_t frame_available_cycles;
    symbol_t frame_required_cycles;
    symbol_t pressure_enqueued_mask;
    symbol_t pressure_drained_mask;
    symbol_t loaded_rom_bank;
    symbol_t renderer_owner;
    symbol_t renderer_phase;
    symbol_t renderer_generation;
    symbol_t current_tileset;
    symbol_t map_width;
    symbol_t map_height;
    symbol_t joy_held;
    symbol_t retry_admit;
    symbol_t retry_finish;
    symbol_t retry_publish;
    expected_breakpoint_t expected;
    unsigned command_stage;
    unsigned completed;
    unsigned start_count;
    uint64_t last_logged_ticks;
    uint64_t start_offset;
    uint64_t end_offset;
    uint32_t public_target_writes;
    uint32_t preparation_buffer_writes;
    uint32_t post_end_public_target_writes;
    uint32_t semantic_unit_public_target_writes;
    int captured_descriptor_slot;
    bool origin_is_start;
    bool end_is_deadline;
    bool north_input_released;
    bool producer_snapshot_valid;
    uint8_t producer_snapshot_class;
    uint8_t producer_snapshot_width;
    uint8_t producer_snapshot_height;
    uint16_t producer_snapshot_destination;
    uint16_t producer_snapshot_extent;
    bool failed;
    symbol_t diagnostic_symbols[MAX_DIAGNOSTIC_BREAKPOINTS];
    int diagnostic_pending;
    unsigned diagnostic_hits[MAX_DIAGNOSTIC_BREAKPOINTS];
    char failure[256];
    sample_t records[MAX_SAMPLES];
    calibration_t calibration;
} driver_t;

static const char *boot_rom_path;
static const char *journey_stage = "boot";
static uint8_t journey_initial_map, journey_initial_x, journey_initial_y;
static uint32_t pixels[SCREEN_WIDTH * SCREEN_HEIGHT];

static void fail(driver_t *driver, const char *message)
{
    if (!driver->failed) {
        driver->failed = true;
        snprintf(driver->failure, sizeof(driver->failure), "%s", message);
    }
}

static bool parse_unsigned(const char *text, unsigned *value)
{
    char *end = NULL;
    errno = 0;
    unsigned long parsed = strtoul(text, &end, 0);
    if (errno || !end || *end || parsed > UINT32_MAX) return false;
    *value = (unsigned)parsed;
    return true;
}

static const char *required_value(int argc, char **argv, int *index)
{
    if (*index + 1 >= argc) {
        fprintf(stderr, "missing value after %s\n", argv[*index]);
        exit(64);
    }
    return argv[++*index];
}

static options_t parse_options(int argc, char **argv)
{
    options_t options = {
        .control_symbol = "wFullColorPhase5ScenarioControl",
        .scenario_symbol = "wFullColorPhase5Scenario",
        .stress_symbol = "wFullColorPhase5StressStateStart",
        .scenario_state_symbol = "wFullColorPhase5ScenarioControl",
        .trace_symbol = "wFullColorDebugTraceCountPhase2",
        .descriptor_class_value = UINT32_MAX,
        .oam_class_value = UINT32_MAX,
        .descriptor_committing_value = UINT32_MAX,
        .movement_axis = "row",
        .samples = 32,
        .warmup_frames = 120,
        .max_frames = 3600,
    };
    for (int index = 1; index < argc; index++) {
        const char *argument = argv[index];
        if (strcmp(argument, "--version") == 0) {
            puts(DRIVER_VERSION);
            exit(0);
        }
        if (strcmp(argument, "--rom") == 0) options.rom = required_value(argc, argv, &index);
        else if (strcmp(argument, "--sym") == 0) options.sym = required_value(argc, argv, &index);
        else if (strcmp(argument, "--boot-rom") == 0) options.boot_rom = required_value(argc, argv, &index);
        else if (strcmp(argument, "--json") == 0) options.json = required_value(argc, argv, &index);
        else if (strcmp(argument, "--frame-dir") == 0) options.frame_dir = required_value(argc, argv, &index);
        else if (strcmp(argument, "--start") == 0) options.start_label = required_value(argc, argv, &index);
        else if (strcmp(argument, "--end") == 0) options.end_label = required_value(argc, argv, &index);
        else if (strcmp(argument, "--origin") == 0) options.origin_label = required_value(argc, argv, &index);
        else if (strcmp(argument, "--deadline") == 0) options.deadline_label = required_value(argc, argv, &index);
        else if (strcmp(argument, "--deadline-kind") == 0) options.deadline_kind = required_value(argc, argv, &index);
        else if (strcmp(argument, "--movement-axis") == 0) options.movement_axis = required_value(argc, argv, &index);
        else if (strcmp(argument, "--control-symbol") == 0) options.control_symbol = required_value(argc, argv, &index);
        else if (strcmp(argument, "--scenario-symbol") == 0) options.scenario_symbol = required_value(argc, argv, &index);
        else if (strcmp(argument, "--stress-symbol") == 0) options.stress_symbol = required_value(argc, argv, &index);
        else if (strcmp(argument, "--scenario-state-symbol") == 0) options.scenario_state_symbol = required_value(argc, argv, &index);
        else if (strcmp(argument, "--trace-symbol") == 0) options.trace_symbol = required_value(argc, argv, &index);
        else if (strcmp(argument, "--scenario-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.scenario_value)) exit(64);
        }
        else if (strcmp(argument, "--control-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.control_value)) exit(64);
        }
        else if (strcmp(argument, "--state-stable-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.state_stable_value)) exit(64);
        }
        else if (strcmp(argument, "--state-complete-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.state_complete_value)) exit(64);
        }
        else if (strcmp(argument, "--result-passed-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.result_passed_value)) exit(64);
        }
        else if (strcmp(argument, "--ledger-all-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.ledger_all_value)) exit(64);
        }
        else if (strcmp(argument, "--barrier-stable-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.barrier_stable_value)) exit(64);
        }
        else if (strcmp(argument, "--yellow-owner-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.yellow_owner_value)) exit(64);
        }
        else if (strcmp(argument, "--yellow-phase-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.yellow_phase_value)) exit(64);
        }
        else if (strcmp(argument, "--color-owner-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.color_owner_value)) exit(64);
        }
        else if (strcmp(argument, "--color-phase-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.color_phase_value)) exit(64);
        }
        else if (strcmp(argument, "--descriptor-class-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.descriptor_class_value)) exit(64);
        }
        else if (strcmp(argument, "--oam-class-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.oam_class_value)) exit(64);
        }
        else if (strcmp(argument, "--descriptor-complete-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.descriptor_complete_value)) exit(64);
        }
        else if (strcmp(argument, "--descriptor-committing-value") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.descriptor_committing_value)) exit(64);
        }
        else if (strcmp(argument, "--samples") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.samples)) exit(64);
        }
        else if (strcmp(argument, "--warmup-frames") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.warmup_frames)) exit(64);
        }
        else if (strcmp(argument, "--max-frames") == 0) {
            if (!parse_unsigned(required_value(argc, argv, &index), &options.max_frames)) exit(64);
        }
        else if (strcmp(argument, "--diagnostic-breakpoint") == 0) {
            if (options.diagnostic_count >= MAX_DIAGNOSTIC_BREAKPOINTS) exit(64);
            options.diagnostic_labels[options.diagnostic_count++] =
                required_value(argc, argv, &index);
        }
        else {
            fprintf(stderr, "unknown argument: %s\n", argument);
            exit(64);
        }
    }
    if (!options.rom || !options.sym || !options.boot_rom || !options.json ||
        !options.frame_dir || !options.start_label || !options.end_label ||
        !options.origin_label || !options.deadline_label ||
        (strcmp(options.deadline_kind, "FIXED_VBLANK") != 0 &&
         strcmp(options.deadline_kind, "LINKED_PRESENTATION") != 0) ||
        (strcmp(options.movement_axis, "row") != 0 &&
         strcmp(options.movement_axis, "column") != 0) ||
        options.scenario_value > 0xFF || options.control_value > 0xFF ||
        options.state_stable_value > 0xFF || options.state_complete_value > 0xFF ||
        options.result_passed_value > 0xFF ||
        options.ledger_all_value > 0xFF || options.barrier_stable_value > 0xFF ||
        options.yellow_owner_value > 0xFF || options.yellow_phase_value > 0xFF ||
        options.color_owner_value > 0xFF || options.color_phase_value > 0xFF ||
        options.oam_class_value > 0x0F ||
        options.descriptor_committing_value > 0x0F ||
        options.descriptor_complete_value > 0x0F ||
        options.samples == 0 || options.samples > MAX_SAMPLES ||
        options.max_frames == 0) {
        fprintf(stderr, "invalid or incomplete SameBoy driver arguments\n");
        exit(64);
    }
    return options;
}

static symbol_t find_symbol(const char *path, const char *wanted)
{
    FILE *file = fopen(path, "r");
    if (!file) return (symbol_t){0};
    char line[1024];
    symbol_t result = {0};
    while (fgets(line, sizeof(line), file)) {
        unsigned bank = 0;
        unsigned address = 0;
        char name[768];
        if (sscanf(line, "%x:%x %767s", &bank, &address, name) == 3 &&
            strcmp(name, wanted) == 0) {
            if (result.found && (result.bank != bank || result.address != address)) {
                result.found = false;
                break;
            }
            result = (symbol_t){(uint16_t)bank, (uint16_t)address, true};
        }
    }
    fclose(file);
    return result;
}

static uint8_t read_banked(GB_gameboy_t *gb, symbol_t symbol, unsigned offset)
{
    uint16_t address = (uint16_t)(symbol.address + offset);
    if (address >= 0xC000 && address <= 0xDFFF) {
        size_t size = 0;
        uint8_t *ram = GB_get_direct_access(gb, GB_DIRECT_ACCESS_RAM, &size, NULL);
        size_t index = address < 0xD000
            ? (size_t)(address - 0xC000)
            : (size_t)symbol.bank * 0x1000 + address - 0xD000;
        if (ram && index < size) return ram[index];
    }
    return GB_safe_read_memory(gb, address);
}

static void write_banked(GB_gameboy_t *gb, symbol_t symbol, unsigned offset, uint8_t value)
{
    uint16_t address = (uint16_t)(symbol.address + offset);
    if (address >= 0xC000 && address <= 0xDFFF) {
        size_t size = 0;
        uint8_t *ram = GB_get_direct_access(gb, GB_DIRECT_ACCESS_RAM, &size, NULL);
        size_t index = address < 0xD000
            ? (size_t)(address - 0xC000)
            : (size_t)symbol.bank * 0x1000 + address - 0xD000;
        if (ram && index < size) {
            ram[index] = value;
            return;
        }
    }
    GB_write_memory(gb, address, value);
}

static void arm_scenario(driver_t *driver)
{
    write_banked(driver->gb, driver->scenario, 0, (uint8_t)driver->options.scenario_value);
    write_banked(driver->gb, driver->control, 0, (uint8_t)driver->options.control_value);
}

static void run_frames(driver_t *driver, unsigned frames)
{
    for (unsigned i = 0; i < frames && !driver->failed; i++) GB_run_frame(driver->gb);
}

static void press_key(driver_t *driver, GB_key_t key)
{
    GB_set_key_state(driver->gb, key, true);
    run_frames(driver, 2);
    GB_set_key_state(driver->gb, key, false);
    run_frames(driver, 121);
}

static void pulse_movement_key(driver_t *driver, GB_key_t key)
{
    /* Match Emulator.press in the natural PyBoy scrolling proof: a fresh
     * two-frame press followed by the complete 121-frame released wait.
     * Keeping a direction asserted
     * indefinitely changes coordinates initially but does not repeatedly
     * exercise Yellow's new-press movement-row/column producer. */
    GB_set_key_state(driver->gb, key, true);
    run_frames(driver, 2);
    GB_set_key_state(driver->gb, key, false);
    run_frames(driver, 121);
}

static bool value_is(driver_t *driver, symbol_t symbol, uint8_t value)
{
    return read_banked(driver->gb, symbol, 0) == value;
}

static bool clean_column_measurement_seam(
    driver_t *driver, uint8_t initial_map, const uint8_t initial_generation[4]
)
{
    if (
        read_banked(driver->gb, driver->current_map, 0) != initial_map ||
        read_banked(driver->gb, driver->x_coord, 0) != 9 ||
        read_banked(driver->gb, driver->y_coord, 0) != 12 ||
        read_banked(driver->gb, driver->renderer_owner, 0) !=
            driver->options.color_owner_value ||
        read_banked(driver->gb, driver->renderer_phase, 0) !=
            driver->options.color_phase_value ||
        read_banked(driver->gb, driver->joy_held, 0) != 0 ||
        read_banked(driver->gb, driver->producer_pending, 0) != 0
    ) return false;
    for (unsigned byte = 0; byte < 4; byte++) {
        if (read_banked(driver->gb, driver->renderer_generation, byte) !=
            initial_generation[byte]) return false;
    }
    for (unsigned slot = 0; slot < DESCRIPTOR_CAPACITY; slot++) {
        uint8_t state_class = read_banked(
            driver->gb, driver->request_descriptors,
            slot * DESCRIPTOR_BYTES
        );
        uint8_t state = state_class >> 4;
        uint8_t request_class = state_class & 0x0F;
        if ((state == 1 || state == 2) &&
            request_class != driver->options.oam_class_value) return false;
    }
    if (read_banked(driver->gb, driver->fast_cache_valid, 0) != 0) {
        uint8_t cached_class = read_banked(
            driver->gb, driver->fast_cache_descriptor, 0
        ) & 0x0F;
        if (cached_class != driver->options.oam_class_value) return false;
    }
    return true;
}

static bool advance_value(driver_t *driver, symbol_t symbol, uint8_t value,
                          GB_key_t key, unsigned max_presses)
{
    for (unsigned i = 0; i < max_presses; i++) {
        if (value_is(driver, symbol, value)) return true;
        press_key(driver, key);
    }
    return value_is(driver, symbol, value);
}

static bool preset_menu_ready(driver_t *driver)
{
    return value_is(driver, driver->top_menu_y, 2) &&
           value_is(driver, driver->top_menu_x, 1) &&
           value_is(driver, driver->max_menu_item, 3) &&
           value_is(driver, driver->watched_keys, 1);
}

static bool advance_to_preset_menu(driver_t *driver, unsigned max_presses)
{
    for (unsigned i = 0; i < max_presses; i++) {
        if (preset_menu_ready(driver)) return true;
        press_key(driver, GB_KEY_A);
    }
    return preset_menu_ready(driver);
}

static bool bedroom_ready(driver_t *driver)
{
    return value_is(driver, driver->current_map, 0x26) &&
           value_is(driver, driver->x_coord, 3) &&
           value_is(driver, driver->y_coord, 6) &&
           value_is(driver, driver->current_tileset, 4) &&
           value_is(driver, driver->map_width, 4) &&
           value_is(driver, driver->map_height, 4) &&
           (GB_safe_read_memory(driver->gb, 0xFF40) & 0x80) != 0 &&
           GB_get_registers(driver->gb)->pc != 0x0038 &&
           (read_banked(driver->gb, driver->status_flags6, 0) & 1) != 0;
}

static bool screen_has_content(void)
{
    uint32_t first = pixels[0];
    for (unsigned i = 1; i < SCREEN_WIDTH * SCREEN_HEIGHT; i++) {
        if (pixels[i] != first) return true;
    }
    return false;
}

static void wait_for_ly_transition(driver_t *driver, uint8_t line)
{
    while (GB_safe_read_memory(driver->gb, LY_ADDRESS) == line && !driver->failed) {
        GB_run(driver->gb);
    }
    while (GB_safe_read_memory(driver->gb, LY_ADDRESS) != line && !driver->failed) {
        GB_run(driver->gb);
    }
}

static uint64_t measure_ly_span(driver_t *driver, uint8_t start, uint8_t end)
{
    wait_for_ly_transition(driver, start);
    uint64_t ticks = 0;
    bool left_start = end != start;
    while ((!left_start || GB_safe_read_memory(driver->gb, LY_ADDRESS) != end) &&
           !driver->failed) {
        ticks += GB_run(driver->gb);
        if (GB_safe_read_memory(driver->gb, LY_ADDRESS) != start) left_start = true;
    }
    return ticks;
}

static bool calibrate_tick_units(driver_t *driver)
{
    if ((GB_safe_read_memory(driver->gb, KEY1_ADDRESS) & 0x80) == 0) {
        fail(driver, "SameBoy calibration did not run at CGB double speed");
        return false;
    }
    size_t state_size = GB_get_save_state_size(driver->gb);
    uint8_t *state = malloc(state_size);
    if (!state) {
        fail(driver, "SameBoy calibration could not allocate a save-state buffer");
        return false;
    }
    GB_save_state_to_buffer(driver->gb, state);
    GB_write_memory(driver->gb, IE_ADDRESS, 0);
    GB_write_memory(driver->gb, IF_ADDRESS, 0);
    for (unsigned i = 0; i < CALIBRATION_NOPS; i++) {
        GB_write_memory(driver->gb, (uint16_t)(0xFF80 + i), 0x00);
    }
    GB_get_registers(driver->gb)->pc = 0xFF80;
    for (unsigned i = 0; i < CALIBRATION_NOPS; i++) {
        driver->calibration.nop_ticks += GB_run(driver->gb);
    }
    if (GB_load_state_from_buffer(driver->gb, state, state_size) != 0) {
        free(state);
        fail(driver, "SameBoy calibration could not restore the natural audit state");
        return false;
    }
    free(state);
    driver->calibration.scanline_register_ticks = measure_ly_span(driver, 144, 145);
    driver->calibration.vblank_ticks = measure_ly_span(driver, 144, 0);
    driver->calibration.frame_ticks = measure_ly_span(driver, 144, 144);
    /* A register-poll boundary can overshoot by the current instruction.  The
     * full 154-line PPU frame is exact; retain both raw LY observations while
     * deriving the physical scanline and ten-line VBlank deadline from it. */
    if (driver->calibration.frame_ticks % 154 != 0) {
        fail(driver, "SameBoy frame tick calibration is not divisible by 154 scanlines");
        return false;
    }
    driver->calibration.scanline_ticks = driver->calibration.frame_ticks / 154;
    if (driver->calibration.nop_ticks != CALIBRATION_NOPS * 4) {
        fail(driver, "SameBoy debugger/GB_run tick unit failed the known NOP calibration");
        return false;
    }
    return !driver->failed;
}

static bool advance_to_bedroom(driver_t *driver)
{
    for (unsigned i = 0; i < 100; i++) {
        if (bedroom_ready(driver)) {
            run_frames(driver, 120);
            if (bedroom_ready(driver) && screen_has_content()) return true;
        }
        press_key(driver, GB_KEY_A);
    }
    return bedroom_ready(driver);
}

static bool stable_owned_pallet(driver_t *driver)
{
    return value_is(driver, driver->current_map, 0) &&
           read_banked(driver->gb, driver->x_coord, 0) < 20 &&
           read_banked(driver->gb, driver->y_coord, 0) < 18 &&
           value_is(driver, driver->renderer_owner, 1) &&
           value_is(driver, driver->renderer_phase, 3) &&
           GB_get_registers(driver->gb)->pc != 0x0038 && screen_has_content();
}

static bool prepare_natural_pallet(driver_t *driver, bool require_post_lab)
{
    /* Mirror the checked host new-game/Oak journey using only controller input. */
    journey_stage = "title";
    run_frames(driver, 600);
    press_key(driver, GB_KEY_START);
    journey_stage = "player-name-menu";
    if (!advance_to_preset_menu(driver, 30)) return false;
    press_key(driver, GB_KEY_DOWN);
    press_key(driver, GB_KEY_A);
    journey_stage = "rival-name-menu";
    if (!advance_to_preset_menu(driver, 20)) return false;
    press_key(driver, GB_KEY_DOWN);
    press_key(driver, GB_KEY_A);
    journey_stage = "oak-introduction";
    if (!advance_to_bedroom(driver)) return false;
    journey_initial_map = read_banked(driver->gb, driver->current_map, 0);
    journey_initial_x = read_banked(driver->gb, driver->x_coord, 0);
    journey_initial_y = read_banked(driver->gb, driver->y_coord, 0);

    journey_stage = "bedroom-to-pallet";
    if (!advance_value(driver, driver->x_coord, 5, GB_KEY_RIGHT, 140)) return false;
    if (!advance_value(driver, driver->y_coord, 1, GB_KEY_UP, 140)) return false;
    if (!advance_value(driver, driver->current_map, 0x25, GB_KEY_RIGHT, 140)) return false;
    if (!advance_value(driver, driver->y_coord, 6, GB_KEY_DOWN, 140)) return false;
    if (!advance_value(driver, driver->x_coord, 3, GB_KEY_LEFT, 140)) return false;
    if (!advance_value(driver, driver->current_map, 0x00, GB_KEY_DOWN, 140)) return false;
    run_frames(driver, 60);
    if (!require_post_lab) return stable_owned_pallet(driver);

    journey_stage = "pallet-to-oak";
    if (!advance_value(driver, driver->x_coord, 10, GB_KEY_RIGHT, 140)) return false;
    if (!advance_value(driver, driver->y_coord, 0, GB_KEY_UP, 140)) return false;
    run_frames(driver, 60);
    journey_stage = "oak-follow";
    if (!advance_value(driver, driver->current_map, 0x28, GB_KEY_A, 140)) return false;
    if (!advance_value(driver, driver->oaks_lab_script, 6, GB_KEY_A, 140)) return false;
    if (!advance_value(driver, driver->y_coord, 4, GB_KEY_DOWN, 140)) return false;
    if (!advance_value(driver, driver->x_coord, 7, GB_KEY_RIGHT, 140)) return false;
    press_key(driver, GB_KEY_UP);
    press_key(driver, GB_KEY_A);
    journey_stage = "starter";
    if (!advance_value(driver, driver->party_count, 1, GB_KEY_A, 140)) return false;
    journey_stage = "rival-battle";
    if (!advance_value(driver, driver->oaks_lab_script, 12, GB_KEY_A, 140)) return false;
    if (!advance_value(driver, driver->y_coord, 6, GB_KEY_DOWN, 140)) return false;
    /* Repeated A naturally starts and completes either outcome of the battle. */
    if (!advance_value(driver, driver->oaks_lab_script, 22, GB_KEY_A, 380)) return false;
    journey_stage = "lab-exit";
    if (!advance_value(driver, driver->y_coord, 10, GB_KEY_DOWN, 140)) return false;
    uint8_t x = read_banked(driver->gb, driver->x_coord, 0);
    if (x < 4 && !advance_value(driver, driver->x_coord, 4, GB_KEY_RIGHT, 140)) return false;
    if (x > 5 && !advance_value(driver, driver->x_coord, 5, GB_KEY_LEFT, 140)) return false;
    if (!advance_value(driver, driver->current_map, 0x00, GB_KEY_DOWN, 140)) return false;
    run_frames(driver, 120);
    return stable_owned_pallet(driver);
}

static uint8_t active_descriptor_state(driver_t *driver);
static uint16_t active_descriptor_address(driver_t *driver);
static uint16_t active_descriptor_destination(driver_t *driver);

static bool vertical_path(driver_t *driver)
{
    return strstr(driver->options.start_label, "Vertical") != NULL;
}

static bool bind_vertical_descriptor_at_start(driver_t *driver)
{
    if (!vertical_path(driver)) return true;
    sample_t *sample = &driver->records[driver->completed];
    uint16_t address = active_descriptor_address(driver);
    uint16_t pool_start = driver->request_descriptors.address;
    uint16_t pool_end = pool_start + DESCRIPTOR_CAPACITY * DESCRIPTOR_BYTES;
    uint16_t cached = read_banked(driver->gb, driver->fast_cache_descriptor, 0) |
        ((uint16_t)read_banked(driver->gb, driver->fast_cache_descriptor, 1) << 8);
    if (
        address < pool_start || address >= pool_end ||
        (address - pool_start) % DESCRIPTOR_BYTES != 0 || address != cached
    ) return false;
    unsigned base = address - pool_start;
    for (unsigned byte = 0; byte < DESCRIPTOR_BYTES; byte++) {
        sample->descriptor_snapshot[byte] = read_banked(
            driver->gb, driver->request_descriptors, base + byte
        );
    }
    uint8_t state_class = sample->descriptor_snapshot[0];
    uint16_t destination = sample->descriptor_snapshot[6] |
        ((uint16_t)sample->descriptor_snapshot[7] << 8);
    uint16_t source = sample->descriptor_snapshot[8] |
        ((uint16_t)sample->descriptor_snapshot[9] << 8);
    uint16_t extent = sample->descriptor_snapshot[14] |
        ((uint16_t)sample->descriptor_snapshot[15] << 8);
    uint16_t reservation = sample->descriptor_snapshot[16] |
        ((uint16_t)sample->descriptor_snapshot[17] << 8);
    uint16_t destination_offset = (uint16_t)(destination - 0x9800);
    if (
        (state_class >> 4) != driver->options.descriptor_committing_value ||
        (state_class & 0x0F) != driver->options.descriptor_class_value ||
        sample->descriptor_snapshot[1] != read_banked(
            driver->gb, driver->renderer_owner, 0
        ) ||
        source != driver->producer_tiles.address ||
        sample->descriptor_snapshot[10] != 2 ||
        sample->descriptor_snapshot[11] != 18 ||
        extent != 36 || reservation != 72 ||
        destination < 0x9800 || destination > 0x9BFF ||
        (destination & 0xFC00) != 0x9800 || destination_offset > 478
    ) return false;
    for (unsigned byte = 0; byte < 4; byte++) {
        if (sample->descriptor_snapshot[2 + byte] != read_banked(
            driver->gb, driver->renderer_generation, byte
        )) return false;
    }
    driver->captured_descriptor_slot = (int)(base / DESCRIPTOR_BYTES);
    sample->descriptor_found = true;
    sample->descriptor_snapshot_found = true;
    sample->descriptor_class = state_class & 0x0F;
    sample->descriptor_width = sample->descriptor_snapshot[10];
    sample->descriptor_height = sample->descriptor_snapshot[11];
    sample->descriptor_extent = extent;
    sample->descriptor_reservation = reservation;
    return true;
}

static bool vertical_descriptor_identity_is_stable(driver_t *driver)
{
    if (!vertical_path(driver)) return true;
    sample_t *sample = &driver->records[driver->completed];
    if (!sample->descriptor_snapshot_found || driver->captured_descriptor_slot < 0) {
        return false;
    }
    unsigned base = (unsigned)driver->captured_descriptor_slot * DESCRIPTOR_BYTES;
    for (unsigned byte = 1; byte < DESCRIPTOR_BYTES; byte++) {
        if (read_banked(driver->gb, driver->request_descriptors, base + byte) !=
            sample->descriptor_snapshot[byte]) return false;
    }
    return active_descriptor_address(driver) ==
        driver->request_descriptors.address + base;
}

static void capture_state(driver_t *driver)
{
    sample_t *sample = &driver->records[driver->completed];
    sample->start_offset = driver->start_offset;
    sample->end_offset = driver->end_offset;
    sample->deadline_offset = driver->last_logged_ticks;
    sample->ticks = driver->end_offset - driver->start_offset;
    sample->public_target_writes = driver->public_target_writes;
    sample->preparation_buffer_writes = driver->preparation_buffer_writes;
    sample->key1 = GB_safe_read_memory(driver->gb, KEY1_ADDRESS);
    sample->end_ly = GB_safe_read_memory(driver->gb, LY_ADDRESS);
    sample->end_stat = GB_safe_read_memory(driver->gb, STAT_ADDRESS);
    sample->active_descriptor_state_at_end = active_descriptor_state(driver);
    sample->fast_cache_valid_at_end = read_banked(driver->gb, driver->fast_cache_valid, 0);
    sample->request_count_at_end = read_banked(driver->gb, driver->request_count, 0);
    sample->active_descriptor_address_at_end = active_descriptor_address(driver);
    sample->active_descriptor_destination_at_end = active_descriptor_destination(driver);
    for (unsigned i = 0; i < STRESS_BYTES; i++) sample->stress[i] = read_banked(driver->gb, driver->stress, i);
    for (unsigned i = 0; i < SCENARIO_BYTES; i++) sample->scenario[i] = read_banked(driver->gb, driver->scenario_state, i);
    for (unsigned i = 0; i < TRACE_BYTES; i++) sample->trace[i] = read_banked(driver->gb, driver->trace, i);
    sample->enqueued_mask_at_end = read_banked(driver->gb, driver->pressure_enqueued_mask, 0);
    sample->drained_mask_at_end = read_banked(driver->gb, driver->pressure_drained_mask, 0);
    sample->available_cycles_at_end =
        read_banked(driver->gb, driver->frame_available_cycles, 0) |
        ((uint16_t)read_banked(driver->gb, driver->frame_available_cycles, 1) << 8);
    sample->required_cycles_at_end =
        read_banked(driver->gb, driver->frame_required_cycles, 0) |
        ((uint16_t)read_banked(driver->gb, driver->frame_required_cycles, 1) << 8);

    if (strstr(driver->options.origin_label, "NorthConnection") != NULL &&
        read_banked(driver->gb, driver->producer_pending, 0)) {
        driver->producer_snapshot_class =
            read_banked(driver->gb, driver->producer_class, 0);
        driver->producer_snapshot_width =
            read_banked(driver->gb, driver->producer_width, 0);
        driver->producer_snapshot_height =
            read_banked(driver->gb, driver->producer_height, 0);
        driver->producer_snapshot_destination =
            read_banked(driver->gb, driver->producer_destination, 0) |
            ((uint16_t)read_banked(driver->gb, driver->producer_destination, 1) << 8);
        driver->producer_snapshot_extent =
            (uint16_t)driver->producer_snapshot_width * driver->producer_snapshot_height;
        driver->producer_snapshot_valid =
            driver->producer_snapshot_extent <= MAX_PAIRED_PAYLOAD_BYTES / 2;
        sample->producer_snapshot_found = driver->producer_snapshot_valid;
        sample->producer_class = driver->producer_snapshot_class;
        sample->producer_width = driver->producer_snapshot_width;
        sample->producer_height = driver->producer_snapshot_height;
        sample->producer_destination = driver->producer_snapshot_destination;
        sample->producer_extent = driver->producer_snapshot_extent;
        sample->producer_payload_bytes = 2 * driver->producer_snapshot_extent;
        if (driver->producer_snapshot_valid) {
            for (unsigned byte = 0; byte < driver->producer_snapshot_extent; byte++) {
                sample->producer_payload[byte] =
                    read_banked(driver->gb, driver->producer_tiles, byte);
                sample->producer_payload[driver->producer_snapshot_extent + byte] =
                    read_banked(driver->gb, driver->producer_attributes, byte);
            }
        }
    }

    /* Bind single-unit evidence to the linked descriptor class and geometry.
     * A producer may leave several resident requests, so select the descriptor
     * whose class matches the armed scenario's scheduler class in Python.  All
     * eight snapshots remain deterministic; the first non-terminal candidate
     * is preferred here and Python rejects an unexpected class or geometry. */
    if (!vertical_path(driver)) driver->captured_descriptor_slot = -1;
    for (unsigned slot = 0;
         !vertical_path(driver) && slot < DESCRIPTOR_CAPACITY; slot++) {
        unsigned base = slot * DESCRIPTOR_BYTES;
        uint8_t state_class = read_banked(driver->gb, driver->request_descriptors, base);
        uint8_t state = state_class & 0xF0;
        if (state == 0xF0 ||
            state == driver->options.descriptor_complete_value << 4) continue;
        if (driver->options.descriptor_class_value <= 0x0F &&
            (state_class & 0x0F) != driver->options.descriptor_class_value) continue;
        sample->descriptor_found = true;
        driver->captured_descriptor_slot = (int)slot;
        sample->descriptor_class = state_class & 0x0F;
        sample->descriptor_width = read_banked(driver->gb, driver->request_descriptors, base + 10);
        sample->descriptor_height = read_banked(driver->gb, driver->request_descriptors, base + 11);
        sample->descriptor_extent =
            read_banked(driver->gb, driver->request_descriptors, base + 14) |
            ((uint16_t)read_banked(driver->gb, driver->request_descriptors, base + 15) << 8);
        sample->descriptor_reservation =
            read_banked(driver->gb, driver->request_descriptors, base + 16) |
            ((uint16_t)read_banked(driver->gb, driver->request_descriptors, base + 17) << 8);
        if (strstr(driver->options.origin_label, "NorthConnection") != NULL) {
            fprintf(stderr, "phase5-north-descriptor slot=%u bytes=", slot);
            for (unsigned byte = 0; byte < DESCRIPTOR_BYTES; byte++) {
                fprintf(stderr, "%02x", read_banked(
                    driver->gb, driver->request_descriptors, base + byte));
            }
            fprintf(stderr,
                    " cache=%02x cache_desc=%02x%02x cache_required=%u producer_pending=%u request_count=%u cursor=%u\n",
                    read_banked(driver->gb, driver->fast_cache_valid, 0),
                    read_banked(driver->gb, driver->fast_cache_descriptor, 1),
                    read_banked(driver->gb, driver->fast_cache_descriptor, 0),
                    read_banked(driver->gb, driver->fast_cache_required_cycles, 0) |
                        ((uint16_t)read_banked(driver->gb, driver->fast_cache_required_cycles, 1) << 8),
                    read_banked(driver->gb, driver->producer_pending, 0),
                    read_banked(driver->gb, driver->request_count, 0),
                    read_banked(driver->gb, driver->request_cursor, 0));
        }
        break;
    }
}

static bool bind_retried_producer_descriptor(driver_t *driver)
{
    if (driver->captured_descriptor_slot >= 0) return true;
    if (!driver->producer_snapshot_valid) return false;
    sample_t *sample = &driver->records[driver->completed];
    for (unsigned slot = 0; slot < DESCRIPTOR_CAPACITY; slot++) {
        unsigned base = slot * DESCRIPTOR_BYTES;
        uint8_t state_class = read_banked(
            driver->gb, driver->request_descriptors, base);
        if ((state_class & 0xf0) == 0xf0 ||
            (state_class & 0x0f) != driver->producer_snapshot_class) continue;
        uint16_t destination =
            read_banked(driver->gb, driver->request_descriptors, base + 6) |
            ((uint16_t)read_banked(driver->gb, driver->request_descriptors, base + 7) << 8);
        uint8_t width = read_banked(
            driver->gb, driver->request_descriptors, base + 10);
        uint8_t height = read_banked(
            driver->gb, driver->request_descriptors, base + 11);
        uint16_t extent =
            read_banked(driver->gb, driver->request_descriptors, base + 14) |
            ((uint16_t)read_banked(driver->gb, driver->request_descriptors, base + 15) << 8);
        if (destination != driver->producer_snapshot_destination ||
            width != driver->producer_snapshot_width ||
            height != driver->producer_snapshot_height ||
            extent != driver->producer_snapshot_extent) continue;
        driver->captured_descriptor_slot = (int)slot;
        sample->descriptor_found = true;
        sample->descriptor_class = state_class & 0x0f;
        sample->descriptor_width = width;
        sample->descriptor_height = height;
        sample->descriptor_extent = extent;
        sample->descriptor_reservation =
            read_banked(driver->gb, driver->request_descriptors, base + 16) |
            ((uint16_t)read_banked(driver->gb, driver->request_descriptors, base + 17) << 8);
        return true;
    }
    return false;
}

static bool captured_descriptor_is_complete(driver_t *driver)
{
    if (!bind_retried_producer_descriptor(driver)) return false;
    unsigned base = (unsigned)driver->captured_descriptor_slot * DESCRIPTOR_BYTES;
    uint8_t state_class = read_banked(
        driver->gb, driver->request_descriptors, base
    );
    if ((state_class & 0x0F) != driver->options.descriptor_class_value) return false;
    return (state_class & 0xF0) ==
        driver->options.descriptor_complete_value << 4;
}

static void capture_postcondition(driver_t *driver, unsigned index)
{
    sample_t *sample = &driver->records[index];
    for (unsigned i = 0; i < SCENARIO_BYTES; i++) {
        sample->post_scenario[i] = read_banked(driver->gb, driver->scenario_state, i);
    }
    sample->post_owner = read_banked(driver->gb, driver->renderer_owner, 0);
    sample->post_phase = read_banked(driver->gb, driver->renderer_phase, 0);
}

static void log_callback(GB_gameboy_t *gb, const char *message, GB_log_attributes_t attributes)
{
    (void)attributes;
    driver_t *driver = GB_get_user_data(gb);
    uint64_t ticks = 0;
    if (sscanf(message, "T-cycles: %" SCNu64, &ticks) == 1) {
        driver->last_logged_ticks = ticks;
    }
}

static bool write_memory_callback(GB_gameboy_t *gb, uint16_t address, uint8_t value)
{
    (void)value;
    driver_t *driver = GB_get_user_data(gb);
    if (!driver || (driver->expected != EXPECT_END && driver->expected != EXPECT_DEADLINE)) return true;
    bool shadow = address >= driver->shadow_oam.address &&
                  address < driver->shadow_oam.address + 160;
    uint8_t svbk = GB_safe_read_memory(gb, SVBK_ADDRESS) & 7;
    if (svbk == 0) svbk = 1;
    bool preparation = svbk == driver->preparation_start.bank &&
                       address >= driver->preparation_start.address &&
                       address < driver->preparation_end.address;
    if (preparation && driver->expected == EXPECT_END) driver->preparation_buffer_writes++;
    uint32_t public_writes = 0;
    if (address == 0xFF46) public_writes = 160;
    else if ((address >= 0x8000 && address <= 0x9FFF) ||
             (address >= 0xFE00 && address <= 0xFE9F) ||
             address == 0xFF69 || address == 0xFF6B || shadow) public_writes = 1;
    if (driver->expected == EXPECT_END) driver->public_target_writes += public_writes;
    else driver->post_end_public_target_writes += public_writes;
    if (driver->expected == EXPECT_DEADLINE &&
        strstr(driver->options.origin_label, "NorthConnection") != NULL &&
        driver->producer_snapshot_valid &&
        driver->captured_descriptor_slot >= 0 &&
        address >= 0x9800 && address <= 0x9BFF) {
        unsigned base =
            (unsigned)driver->captured_descriptor_slot * DESCRIPTOR_BYTES;
        uint8_t state_class = read_banked(
            driver->gb, driver->request_descriptors, base
        );
        if ((state_class >> 4) != driver->options.descriptor_committing_value) {
            return true;
        }
        uint16_t target = (uint16_t)(address - 0x9800) & 0x03FF;
        uint16_t origin =
            (uint16_t)(driver->producer_snapshot_destination - 0x9800) & 0x03FF;
        for (unsigned row = 0; row < driver->producer_snapshot_height; row++) {
            uint16_t row_origin = (origin + row * 32) & 0x03FF;
            uint16_t column = (target - row_origin) & 0x03FF;
            if (column < driver->producer_snapshot_width) {
                driver->semantic_unit_public_target_writes++;
                break;
            }
        }
    }
    return true;
}

static uint16_t active_descriptor_address(driver_t *driver)
{
    return read_banked(driver->gb, driver->active_descriptor, 0) |
        ((uint16_t)read_banked(driver->gb, driver->active_descriptor, 1) << 8);
}

static uint8_t active_descriptor_state(driver_t *driver)
{
    uint16_t address = active_descriptor_address(driver);
    if (address < 0xD000 || address > 0xDFFF) return 0xFF;
    symbol_t descriptor = {
        .bank = driver->request_descriptors.bank,
        .address = address,
        .found = true,
    };
    return read_banked(driver->gb, descriptor, 0);
}

static uint16_t active_descriptor_destination(driver_t *driver)
{
    uint16_t address = active_descriptor_address(driver);
    if (address < 0xD000 || address > 0xDFFF) return 0;
    symbol_t descriptor = {
        .bank = driver->request_descriptors.bank,
        .address = address,
        .found = true,
    };
    return read_banked(driver->gb, descriptor, 6) |
        ((uint16_t)read_banked(driver->gb, descriptor, 7) << 8);
}

static bool at_linked_symbol(driver_t *driver, symbol_t symbol)
{
    uint16_t pc = GB_get_registers(driver->gb)->pc;
    if (pc != symbol.address) return false;
    if (pc < 0x4000) return symbol.bank == 0;
    return read_banked(driver->gb, driver->loaded_rom_bank, 0) == symbol.bank;
}

static void complete_sample_at_deadline(driver_t *driver, GB_gameboy_t *gb)
{
    sample_t *sample = &driver->records[driver->completed];
    if (vertical_path(driver) && (
        !vertical_descriptor_identity_is_stable(driver) ||
        !sample->descriptor_home_seen || !sample->descriptor_deferred_seen
    )) {
        fail(driver, "canonical column descriptor identity or finalizer seams drifted");
        return;
    }
    sample->deadline_offset = driver->last_logged_ticks;
    sample->deadline_ly = GB_safe_read_memory(driver->gb, LY_ADDRESS);
    sample->deadline_stat = GB_safe_read_memory(driver->gb, STAT_ADDRESS);
    sample->active_descriptor_state_at_deadline = active_descriptor_state(driver);
    sample->fast_cache_valid_at_deadline = read_banked(driver->gb, driver->fast_cache_valid, 0);
    sample->request_count_at_deadline = read_banked(driver->gb, driver->request_count, 0);
    sample->active_descriptor_address_at_deadline = active_descriptor_address(driver);
    sample->active_descriptor_destination_at_deadline = active_descriptor_destination(driver);
    sample->post_end_public_target_writes = driver->post_end_public_target_writes;
    sample->semantic_unit_public_target_writes =
        driver->semantic_unit_public_target_writes;
    for (unsigned i = 0; i < TRACE_BYTES; i++) {
        sample->presentation_trace[i] = read_banked(driver->gb, driver->trace, i);
    }
    sample->enqueued_mask_at_deadline = read_banked(driver->gb, driver->pressure_enqueued_mask, 0);
    sample->drained_mask_at_deadline = read_banked(driver->gb, driver->pressure_drained_mask, 0);
    sample->available_cycles_at_deadline =
        read_banked(driver->gb, driver->frame_available_cycles, 0) |
        ((uint16_t)read_banked(driver->gb, driver->frame_available_cycles, 1) << 8);
    sample->required_cycles_at_deadline =
        read_banked(driver->gb, driver->frame_required_cycles, 0) |
        ((uint16_t)read_banked(driver->gb, driver->frame_required_cycles, 1) << 8);
    if (sample->producer_snapshot_found && driver->captured_descriptor_slot >= 0) {
        unsigned base =
            (unsigned)driver->captured_descriptor_slot * DESCRIPTOR_BYTES;
        sample->producer_bound_descriptor_address =
            driver->request_descriptors.address + base;
        sample->producer_bound_descriptor_state = read_banked(
            driver->gb, driver->request_descriptors, base
        );
        sample->producer_bound_descriptor_destination =
            read_banked(driver->gb, driver->request_descriptors, base + 6) |
            ((uint16_t)read_banked(
                driver->gb, driver->request_descriptors, base + 7
            ) << 8);
    }
    driver->completed++;
    if (driver->completed >= driver->options.samples) {
        GB_debugger_set_disabled(gb, true);
    }
    driver->expected = EXPECT_ORIGIN;
}

static char *debugger_input(GB_gameboy_t *gb)
{
    driver_t *driver = GB_get_user_data(gb);
    const char *name = GB_debugger_name_for_address(gb, GB_get_registers(gb)->pc);
    if (!name) {
        fail(driver, "debugger stopped at an unnamed address");
        return strdup("continue");
    }
    if (driver->diagnostic_pending >= 0) {
        unsigned index = (unsigned)driver->diagnostic_pending;
        driver->diagnostic_pending = -1;
        driver->diagnostic_hits[index]++;
        fprintf(stderr,
                "phase5-hotspot label=%s hit=%u offset=%" PRIu64
                " ly=%u stat=%u bank=%02x pc=%04x\n",
                driver->options.diagnostic_labels[index],
                driver->diagnostic_hits[index], driver->last_logged_ticks,
                GB_safe_read_memory(gb, LY_ADDRESS),
                GB_safe_read_memory(gb, STAT_ADDRESS),
                read_banked(driver->gb, driver->loaded_rom_bank, 0),
                GB_get_registers(gb)->pc);
        return strdup("continue");
    }
    for (unsigned index = 0; index < driver->options.diagnostic_count; index++) {
        if (at_linked_symbol(driver, driver->diagnostic_symbols[index])) {
            driver->diagnostic_pending = (int)index;
            return strdup("ticks keep");
        }
    }
    if (strstr(driver->options.origin_label, "NorthConnection") != NULL) {
        sample_t *sample = &driver->records[driver->completed];
        if (at_linked_symbol(driver, driver->retry_admit)) {
            sample->retry_admit_hits++;
            return strdup("continue");
        }
        if (at_linked_symbol(driver, driver->retry_finish)) {
            sample->retry_finish_hits++;
            return strdup("continue");
        }
        if (at_linked_symbol(driver, driver->retry_publish)) {
            sample->retry_publish_hits++;
            sample->retry_publish_result = (uint8_t)(GB_get_registers(gb)->af >> 8);
            (void)bind_retried_producer_descriptor(driver);
            return strdup("continue");
        }
    }
    if (vertical_path(driver) && at_linked_symbol(driver, driver->owner_end)) {
        sample_t *sample = &driver->records[driver->completed];
        if (driver->expected == EXPECT_DEADLINE) {
            sample->descriptor_home_seen = true;
            sample->descriptor_home_address = active_descriptor_address(driver);
            sample->descriptor_home_state = active_descriptor_state(driver);
            sample->descriptor_home_cache = read_banked(
                driver->gb, driver->fast_cache_valid, 0
            );
            sample->descriptor_home_post_end_public_writes =
                driver->post_end_public_target_writes;
        }
        return strdup("continue");
    }
    if (vertical_path(driver) &&
        at_linked_symbol(driver, driver->deferred_accounting_start)) {
        sample_t *sample = &driver->records[driver->completed];
        if (driver->expected == EXPECT_DEADLINE) {
            sample->descriptor_deferred_seen = true;
            sample->descriptor_deferred_address = active_descriptor_address(driver);
            sample->descriptor_deferred_state = active_descriptor_state(driver);
            sample->descriptor_deferred_cache = read_banked(
                driver->gb, driver->fast_cache_valid, 0
            );
        }
        return strdup("continue");
    }
    symbol_t expected_symbol =
        driver->expected == EXPECT_ORIGIN ? driver->origin :
        driver->expected == EXPECT_START ? driver->operation_start :
        driver->expected == EXPECT_END ? driver->operation_end : driver->deadline;
    uint16_t pc = GB_get_registers(gb)->pc;
    if (!at_linked_symbol(driver, expected_symbol)) {
        if (driver->expected == EXPECT_ORIGIN &&
            strcmp(driver->options.deadline_kind, "LINKED_PRESENTATION") == 0 &&
            (at_linked_symbol(driver, driver->operation_start) ||
             at_linked_symbol(driver, driver->operation_end) ||
             at_linked_symbol(driver, driver->deadline))) {
            /* Shared enqueue and presentation seams may execute for unrelated
             * natural work while navigation approaches the case-specific
             * linked origin. Capture begins only at that origin; once it is
             * observed, start/end/deadline ordering remains strict. */
            return strdup("continue");
        }
        if (driver->expected == EXPECT_DEADLINE &&
            strcmp(driver->options.deadline_kind, "LINKED_PRESENTATION") == 0 &&
            (at_linked_symbol(driver, driver->origin) ||
             at_linked_symbol(driver, driver->operation_start) ||
             at_linked_symbol(driver, driver->operation_end))) {
            /* A mainline producer may coalesce or repeat before the first owned
             * presentation. The first origin/start/end remains paired with the
             * first linked presentation deadline. */
            return strdup("continue");
        }
        /* An operation may not be scheduled in every natural VBlank. */
        if (driver->expected == EXPECT_START &&
            at_linked_symbol(driver, driver->deadline)) {
            driver->expected = EXPECT_ORIGIN;
            driver->command_stage = 0;
            return strdup("continue");
        }
        if (driver->expected == EXPECT_START &&
            strstr(driver->options.origin_label, "NorthConnection") != NULL &&
            at_linked_symbol(driver, driver->operation_end)) {
            /* The natural north-row audit route also observes ordinary
             * approach rows. Discard an origin whose exact linked connection
             * Start never occurred; the actual case still has to hit the one
             * bank-qualified Start breakpoint before End can be accepted. */
            driver->expected = EXPECT_ORIGIN;
            driver->command_stage = 0;
            return strdup("continue");
        }
        char message[256];
        snprintf(message, sizeof(message),
                 "debugger breakpoint order violates origin <= start < end < deadline (expected=%u pc=%04x bank=%02x expected=%02x:%04x starts=%u completed=%u)",
                 driver->expected, pc,
                 read_banked(driver->gb, driver->loaded_rom_bank, 0),
                 expected_symbol.bank, expected_symbol.address,
                 driver->start_count, driver->completed);
        fail(driver, message);
        return strdup("continue");
    }
    if (driver->expected == EXPECT_DEADLINE &&
        strcmp(driver->options.deadline_kind, "LINKED_PRESENTATION") == 0 &&
        driver->options.descriptor_class_value <= 0x0F &&
        !captured_descriptor_is_complete(driver)) {
        /* The shared owner-return seam can occur on an earlier serialized
         * OAM frame.  Close only after the exact descriptor captured at End
         * has completed as one whole immutable publication. */
        return strdup("continue");
    }
    if (driver->expected == EXPECT_ORIGIN) {
        if (driver->command_stage == 0) {
            if (strstr(driver->options.origin_label, "NorthConnection") != NULL) {
                GB_set_key_state(driver->gb, GB_KEY_UP, false);
                driver->north_input_released = true;
            }
            driver->command_stage = 1;
            return strdup("ticks");
        }
        driver->command_stage = 0;
        driver->public_target_writes = 0;
        driver->preparation_buffer_writes = 0;
        driver->post_end_public_target_writes = 0;
        driver->semantic_unit_public_target_writes = 0;
        driver->captured_descriptor_slot = -1;
        if (driver->origin_is_start) {
            driver->start_count++;
            driver->start_offset = 0;
            driver->expected = EXPECT_END;
        }
        else driver->expected = EXPECT_START;
        return strdup("continue");
    }
    if (driver->command_stage == 0) {
        driver->command_stage = 1;
        return strdup("ticks keep");
    }
    if (driver->expected == EXPECT_START) {
        if (!bind_vertical_descriptor_at_start(driver)) {
            fail(driver, "canonical column descriptor was not bound at VerticalStart");
            driver->command_stage = 0;
            return strdup("continue");
        }
        driver->start_count++;
        driver->start_offset = driver->last_logged_ticks;
        driver->expected = EXPECT_END;
    }
    else if (driver->expected == EXPECT_END) {
        driver->end_offset = driver->last_logged_ticks;
        if (driver->end_offset <= driver->start_offset) {
            fail(driver, "SameBoy observed a non-positive linked operation duration");
        }
        capture_state(driver);
        if (driver->end_is_deadline) complete_sample_at_deadline(driver, gb);
        else driver->expected = EXPECT_DEADLINE;
    }
    else {
        if (driver->last_logged_ticks <= driver->end_offset) {
            fail(driver, "SameBoy observed operation end at or after its deadline seam");
        }
        complete_sample_at_deadline(driver, gb);
    }
    driver->command_stage = 0;
    return strdup("continue");
}

static uint32_t encode_rgb(GB_gameboy_t *gb, uint8_t red, uint8_t green, uint8_t blue)
{
    (void)gb;
    return 0xFF000000u | ((uint32_t)red << 16) | ((uint32_t)green << 8) | blue;
}

static void load_boot_rom(GB_gameboy_t *gb, GB_boot_rom_t type)
{
    (void)type;
    if (GB_load_boot_rom(gb, boot_rom_path) != 0) {
        driver_t *driver = GB_get_user_data(gb);
        if (driver) fail(driver, "SameBoy could not load the pinned CGB boot ROM");
    }
}

static bool write_frame(const char *directory, unsigned index)
{
    char path[4096];
    if (snprintf(path, sizeof(path), "%s/frame-%04u.ppm", directory, index) >= (int)sizeof(path)) return false;
    FILE *file = fopen(path, "wb");
    if (!file) return false;
    if (fprintf(file, "P6\n%d %d\n255\n", SCREEN_WIDTH, SCREEN_HEIGHT) < 0) {
        fclose(file);
        return false;
    }
    for (unsigned i = 0; i < SCREEN_WIDTH * SCREEN_HEIGHT; i++) {
        uint8_t rgb[3] = {
            (uint8_t)(pixels[i] >> 16),
            (uint8_t)(pixels[i] >> 8),
            (uint8_t)pixels[i],
        };
        if (fwrite(rgb, sizeof(rgb), 1, file) != 1) {
            fclose(file);
            return false;
        }
    }
    return fclose(file) == 0;
}

static void print_hex(FILE *file, const uint8_t *bytes, size_t size)
{
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < size; i++) {
        fputc(digits[bytes[i] >> 4], file);
        fputc(digits[bytes[i] & 0xF], file);
    }
}

static bool write_json(driver_t *driver)
{
    FILE *file = fopen(driver->options.json, "w");
    if (!file) return false;
    fprintf(file, "{\"calibration\":{\"frame_ticks\":%" PRIu64 ",\"known_nop_count\":%u,\"known_nop_ticks\":%" PRIu64 ",\"ly144_to_ly0_register_ticks\":%" PRIu64 ",\"ly144_to_ly145_register_ticks\":%" PRIu64 ",\"natural_vblank_ticks\":%" PRIu64 ",\"scanline_ticks\":%" PRIu64 "},\"model\":\"CGB-C\",\"samples\":[",
            driver->calibration.frame_ticks, CALIBRATION_NOPS,
            driver->calibration.nop_ticks, driver->calibration.vblank_ticks,
            driver->calibration.scanline_register_ticks,
            driver->calibration.scanline_ticks * 10,
            driver->calibration.scanline_ticks);
    for (unsigned i = 0; i < driver->completed; i++) {
        sample_t *sample = &driver->records[i];
        if (i) fputc(',', file);
        fprintf(file, "{\"active_descriptor_address_at_deadline\":%u,\"active_descriptor_address_at_end\":%u,\"active_descriptor_destination_at_deadline\":%u,\"active_descriptor_destination_at_end\":%u,\"active_descriptor_state_at_deadline\":%u,\"active_descriptor_state_at_end\":%u,\"available_cycles_at_deadline\":%u,\"available_cycles_at_end\":%u,\"deadline_ly\":%u,\"deadline_offset\":%" PRIu64 ",\"deadline_stat\":%u,\"descriptor_class\":%u,\"descriptor_extent\":%u,\"descriptor_found\":%s,\"descriptor_height\":%u,\"descriptor_reservation\":%u,\"descriptor_width\":%u,\"drained_mask_at_deadline\":%u,\"drained_mask_at_end\":%u,\"end_ly\":%u,\"end_offset\":%" PRIu64 ",\"end_stat\":%u,\"enqueued_mask_at_deadline\":%u,\"enqueued_mask_at_end\":%u,\"fast_cache_valid_at_deadline\":%u,\"fast_cache_valid_at_end\":%u,\"frame\":\"frame-%04u.ppm\",\"index\":%u,\"key1\":%u,\"post_end_public_target_writes\":%u,\"post_owner\":%u,\"post_phase\":%u,\"post_scenario\":\"", sample->active_descriptor_address_at_deadline, sample->active_descriptor_address_at_end, sample->active_descriptor_destination_at_deadline, sample->active_descriptor_destination_at_end, sample->active_descriptor_state_at_deadline, sample->active_descriptor_state_at_end, sample->available_cycles_at_deadline, sample->available_cycles_at_end, sample->deadline_ly, sample->deadline_offset, sample->deadline_stat, sample->descriptor_class, sample->descriptor_extent, sample->descriptor_found ? "true" : "false", sample->descriptor_height, sample->descriptor_reservation, sample->descriptor_width, sample->drained_mask_at_deadline, sample->drained_mask_at_end, sample->end_ly, sample->end_offset, sample->end_stat, sample->enqueued_mask_at_deadline, sample->enqueued_mask_at_end, sample->fast_cache_valid_at_deadline, sample->fast_cache_valid_at_end, i, i, sample->key1, sample->post_end_public_target_writes, sample->post_owner, sample->post_phase);
        print_hex(file, sample->post_scenario, SCENARIO_BYTES);
        fputs("\",\"scenario\":\"", file);
        print_hex(file, sample->scenario, SCENARIO_BYTES);
        fputs("\",\"stress\":\"", file);
        print_hex(file, sample->stress, STRESS_BYTES);
        if (sample->producer_snapshot_found || sample->retry_publish_hits) {
            fprintf(file,
                    "\",\"producer_class\":%u,\"producer_destination\":%u,\"producer_extent\":%u,\"producer_height\":%u,\"producer_payload\":\"",
                    sample->producer_class, sample->producer_destination,
                    sample->producer_extent, sample->producer_height);
            print_hex(file, sample->producer_payload, sample->producer_payload_bytes);
            fprintf(file,
                    "\",\"producer_snapshot_found\":%s,\"producer_width\":%u,\"producer_bound_descriptor_address\":%u,\"producer_bound_descriptor_destination\":%u,\"producer_bound_descriptor_state\":%u,\"retry_admit_hits\":%u,\"retry_finish_hits\":%u,\"retry_publish_hits\":%u,\"retry_publish_result\":%u,\"presentation_trace\":\"",
                    sample->producer_snapshot_found ? "true" : "false",
                    sample->producer_width,
                    sample->producer_bound_descriptor_address,
                    sample->producer_bound_descriptor_destination,
                    sample->producer_bound_descriptor_state,
                    sample->retry_admit_hits,
                    sample->retry_finish_hits, sample->retry_publish_hits,
                    sample->retry_publish_result);
        }
        else fputs("\",\"presentation_trace\":\"", file);
        print_hex(file, sample->presentation_trace, TRACE_BYTES);
        if (sample->descriptor_snapshot_found) {
            fprintf(file,
                    "\",\"descriptor_deferred_address\":%u,\"descriptor_deferred_cache\":%u,\"descriptor_deferred_seen\":%s,\"descriptor_deferred_state\":%u,\"descriptor_home_address\":%u,\"descriptor_home_cache\":%u,\"descriptor_home_post_end_public_writes\":%u,\"descriptor_home_seen\":%s,\"descriptor_home_state\":%u,\"descriptor_snapshot\":\"",
                    sample->descriptor_deferred_address,
                    sample->descriptor_deferred_cache,
                    sample->descriptor_deferred_seen ? "true" : "false",
                    sample->descriptor_deferred_state,
                    sample->descriptor_home_address,
                    sample->descriptor_home_cache,
                    sample->descriptor_home_post_end_public_writes,
                    sample->descriptor_home_seen ? "true" : "false",
                    sample->descriptor_home_state);
            print_hex(file, sample->descriptor_snapshot, DESCRIPTOR_BYTES);
            fputs("\",\"preparation_buffer_writes\":", file);
            fprintf(file, "%u", sample->preparation_buffer_writes);
        }
        else {
            fprintf(file, "\",\"preparation_buffer_writes\":%u", sample->preparation_buffer_writes);
        }
        fprintf(file, ",\"public_target_writes\":%u,\"request_count_at_deadline\":%u,\"request_count_at_end\":%u,\"required_cycles_at_deadline\":%u,\"required_cycles_at_end\":%u,\"semantic_unit_public_target_writes\":%u,\"start_offset\":%" PRIu64 ",\"ticks\":%" PRIu64 ",\"trace\":\"", sample->public_target_writes, sample->request_count_at_deadline, sample->request_count_at_end, sample->required_cycles_at_deadline, sample->required_cycles_at_end, sample->semantic_unit_public_target_writes, sample->start_offset, sample->ticks);
        print_hex(file, sample->trace, TRACE_BYTES);
        fputs("\"}", file);
    }
    fprintf(file, "],\"schema\":\"sameboy-phase5-driver-v1\",\"start_count\":%u}\n", driver->start_count);
    return fclose(file) == 0;
}

static bool require_symbol(driver_t *driver, const char *name, symbol_t *result)
{
    *result = find_symbol(driver->options.sym, name);
    if (!result->found) {
        char message[256];
        snprintf(message, sizeof(message), "audit symbol file lacks %s", name);
        fail(driver, message);
        return false;
    }
    return true;
}

int main(int argc, char **argv)
{
    driver_t driver = {
        .options = parse_options(argc, argv),
        .expected = EXPECT_ORIGIN,
        .diagnostic_pending = -1,
        .captured_descriptor_slot = -1,
    };
    driver.origin = find_symbol(driver.options.sym, driver.options.origin_label);
    driver.operation_start = find_symbol(driver.options.sym, driver.options.start_label);
    driver.operation_end = find_symbol(driver.options.sym, driver.options.end_label);
    driver.deadline = find_symbol(driver.options.sym, driver.options.deadline_label);
    driver.owner_end = find_symbol(
        driver.options.sym, "FullColorPhase5CombinedVBlankEnd"
    );
    driver.deferred_accounting_start = find_symbol(
        driver.options.sym, "FullColorPhase5DeferredAccountingStart"
    );
    for (unsigned index = 0; index < driver.options.diagnostic_count; index++) {
        driver.diagnostic_symbols[index] =
            find_symbol(driver.options.sym, driver.options.diagnostic_labels[index]);
        if (!driver.diagnostic_symbols[index].found) {
            fail(&driver, "audit symbol file lacks a requested diagnostic breakpoint");
        }
    }
    require_symbol(&driver, driver.options.control_symbol, &driver.control);
    require_symbol(&driver, driver.options.scenario_symbol, &driver.scenario);
    require_symbol(&driver, driver.options.stress_symbol, &driver.stress);
    require_symbol(&driver, driver.options.scenario_state_symbol, &driver.scenario_state);
    require_symbol(&driver, driver.options.trace_symbol, &driver.trace);
    require_symbol(&driver, "wTopMenuItemY", &driver.top_menu_y);
    require_symbol(&driver, "wTopMenuItemX", &driver.top_menu_x);
    require_symbol(&driver, "wMaxMenuItem", &driver.max_menu_item);
    require_symbol(&driver, "wMenuWatchedKeys", &driver.watched_keys);
    require_symbol(&driver, "wCurrentMenuItem", &driver.current_menu_item);
    require_symbol(&driver, "wCurMap", &driver.current_map);
    require_symbol(&driver, "wXCoord", &driver.x_coord);
    require_symbol(&driver, "wYCoord", &driver.y_coord);
    require_symbol(&driver, "wStatusFlags6", &driver.status_flags6);
    require_symbol(&driver, "wOaksLabCurScript", &driver.oaks_lab_script);
    require_symbol(&driver, "wPartyCount", &driver.party_count);
    require_symbol(&driver, "wShadowOAM", &driver.shadow_oam);
    require_symbol(&driver, "wFullColorBGPaletteBase", &driver.preparation_start);
    require_symbol(&driver, "wFullColorReconstructionLedger", &driver.preparation_end);
    require_symbol(&driver, "wFullColorRequestDescriptors", &driver.request_descriptors);
    require_symbol(&driver, "wFullColorActiveDescriptor", &driver.active_descriptor);
    require_symbol(&driver, "wFullColorRequestCursor", &driver.request_cursor);
    require_symbol(&driver, "wFullColorProducerPending", &driver.producer_pending);
    require_symbol(&driver, "wFullColorProducerTiles", &driver.producer_tiles);
    require_symbol(&driver, "wFullColorProducerAttributes", &driver.producer_attributes);
    require_symbol(&driver, "wFullColorProducerDestination", &driver.producer_destination);
    require_symbol(&driver, "wFullColorProducerWidth", &driver.producer_width);
    require_symbol(&driver, "wFullColorProducerHeight", &driver.producer_height);
    require_symbol(&driver, "wFullColorProducerClass", &driver.producer_class);
    require_symbol(&driver, "wFullColorPhase5FastCacheValid", &driver.fast_cache_valid);
    require_symbol(&driver, "wFullColorPhase5FastCacheDescriptor", &driver.fast_cache_descriptor);
    require_symbol(&driver, "wFullColorPhase5FastCacheSnapshot", &driver.fast_cache_snapshot);
    require_symbol(&driver, "wFullColorPhase5FastCacheRequiredCycles", &driver.fast_cache_required_cycles);
    require_symbol(&driver, "wFullColorRequestCount", &driver.request_count);
    require_symbol(&driver, "wFullColorPhase5FrameAvailableCycles", &driver.frame_available_cycles);
    require_symbol(&driver, "wFullColorPhase5FrameRequiredCycles", &driver.frame_required_cycles);
    require_symbol(&driver, "wFullColorPhase5PressureEnqueuedMask", &driver.pressure_enqueued_mask);
    require_symbol(&driver, "wFullColorPhase5PressureDrainedMask", &driver.pressure_drained_mask);
    require_symbol(&driver, "hLoadedROMBank", &driver.loaded_rom_bank);
    require_symbol(&driver, "wRendererOwner", &driver.renderer_owner);
    require_symbol(&driver, "wRendererPhase", &driver.renderer_phase);
    require_symbol(&driver, "wRendererGeneration", &driver.renderer_generation);
    require_symbol(&driver, "wCurMapTileset", &driver.current_tileset);
    require_symbol(&driver, "wCurMapWidth", &driver.map_width);
    require_symbol(&driver, "wCurMapHeight", &driver.map_height);
    require_symbol(&driver, "hJoyHeld", &driver.joy_held);
    require_symbol(&driver, "AdmitPreparedFullColorSemanticSelected", &driver.retry_admit);
    require_symbol(&driver, "FinishFullColorSemanticSelected", &driver.retry_finish);
    require_symbol(&driver, "RetryFullColorProducer.publish", &driver.retry_publish);
    if (!driver.origin.found || !driver.operation_start.found ||
        !driver.operation_end.found || !driver.deadline.found) {
        fail(&driver, "audit symbol file lacks a linked timing breakpoint");
    }
    if (vertical_path(&driver) &&
        (!driver.owner_end.found || !driver.deferred_accounting_start.found)) {
        fail(&driver, "audit symbol file lacks canonical column finalizer seams");
    }
    driver.origin_is_start =
        driver.origin.bank == driver.operation_start.bank &&
        driver.origin.address == driver.operation_start.address;
    driver.end_is_deadline =
        driver.operation_end.bank == driver.deadline.bank &&
        driver.operation_end.address == driver.deadline.address;
    if (driver.failed) {
        fprintf(stderr, "%s\n", driver.failure);
        return 65;
    }

    GB_random_seed(UINT64_C(0x504841534535));
    driver.gb = GB_init(GB_alloc(), GB_MODEL_CGB_C);
    if (!driver.gb) {
        fprintf(stderr, "SameBoy allocation failed\n");
        return 70;
    }
    GB_set_user_data(driver.gb, &driver);
    GB_set_log_callback(driver.gb, log_callback);
    GB_set_write_memory_callback(driver.gb, write_memory_callback);
    GB_set_input_callback(driver.gb, debugger_input);
    GB_set_pixels_output(driver.gb, pixels);
    GB_set_rgb_encode_callback(driver.gb, encode_rgb);
    GB_set_emulate_joypad_bouncing(driver.gb, false);
    GB_set_turbo_mode(driver.gb, true, true);
    boot_rom_path = driver.options.boot_rom;
    GB_set_boot_rom_load_callback(driver.gb, load_boot_rom);
    if (GB_load_rom(driver.gb, driver.options.rom) != 0) fail(&driver, "SameBoy could not load the audit ROM");
    GB_debugger_load_symbol_file(driver.gb, driver.options.sym);
    GB_reset(driver.gb);
    size_t ram_size = 0;
    uint8_t *ram = GB_get_direct_access(
        driver.gb, GB_DIRECT_ACCESS_RAM, &ram_size, NULL
    );
    if (ram) memset(ram, 0, ram_size);
    if (driver.failed) goto done;

    bool party_path = strstr(driver.options.start_label, "Party") != NULL;
    bool north_path = strstr(driver.options.origin_label, "NorthConnection") != NULL;
    if (north_path) {
        symbol_t linked_north_start =
            find_symbol(driver.options.sym, "FullColorPhase5NorthConnectionStart");
        symbol_t linked_north_producer =
            find_symbol(driver.options.sym, "EnqueueFullColorMapConnection");
        if (!linked_north_start.found || !linked_north_producer.found ||
            linked_north_start.bank != linked_north_producer.bank ||
            linked_north_start.address != linked_north_producer.address ||
            driver.operation_start.bank != linked_north_start.bank ||
            driver.operation_start.address != linked_north_start.address) {
            fail(&driver, "North Start and producer linked symbols are not exact aliases");
            goto done;
        }
    }
    if (!prepare_natural_pallet(&driver, party_path || north_path)) {
        char message[256];
        snprintf(message, sizeof(message),
                 "SameBoy controller journey failed at %s (initial=%u,%u,%u; map=%u x=%u y=%u script=%u party=%u)",
                 journey_stage,
                 journey_initial_map, journey_initial_x, journey_initial_y,
                 read_banked(driver.gb, driver.current_map, 0),
                 read_banked(driver.gb, driver.x_coord, 0),
                 read_banked(driver.gb, driver.y_coord, 0),
                 read_banked(driver.gb, driver.oaks_lab_script, 0),
                 read_banked(driver.gb, driver.party_count, 0));
        fail(&driver, message);
        (void)write_frame(driver.options.frame_dir, 9999);
        goto done;
    }

    if (!party_path && !north_path) {
        bool positioned = advance_value(
            &driver, driver.x_coord, 8,
            read_banked(driver.gb, driver.x_coord, 0) < 8 ? GB_KEY_RIGHT : GB_KEY_LEFT,
            24
        );
        if (positioned && strcmp(driver.options.movement_axis, "column") == 0) {
            positioned = advance_value(
                &driver, driver.y_coord, 12,
                read_banked(driver.gb, driver.y_coord, 0) < 12 ? GB_KEY_DOWN : GB_KEY_UP,
                24
            );
            /* x=8 is the open Pallet approach.  One further natural step
             * positions the player at the camera-column seam, so the first
             * measured 2-on/121-off Right pulse enqueues the canonical 2x18
             * unit instead of spending the entire 32-VBlank window merely
             * approaching that seam. */
            if (positioned) {
                uint8_t initial_map = read_banked(
                    driver.gb, driver.current_map, 0
                );
                uint8_t initial_generation[4];
                for (unsigned byte = 0; byte < 4; byte++) {
                    initial_generation[byte] = read_banked(
                        driver.gb, driver.renderer_generation, byte
                    );
                }
                positioned = advance_value(
                    &driver, driver.x_coord, 9, GB_KEY_RIGHT, 2
                );
                positioned = positioned && clean_column_measurement_seam(
                    &driver, initial_map, initial_generation
                );
            }
        }
        if (!positioned) {
            fail(&driver, "natural pressure path did not reach Pallet's open scrolling axis");
            goto done;
        }
    }
    else if (north_path) {
        /* Position before installing timing breakpoints. ScheduleNorthRowRedraw
         * is shared by ordinary approach rows, so the first observed origin
         * after this point must be the final natural Pallet north row. */
        bool positioned = advance_value(
            &driver, driver.x_coord, 8,
            read_banked(driver.gb, driver.x_coord, 0) < 8 ? GB_KEY_RIGHT : GB_KEY_LEFT,
            24
        ) && advance_value(&driver, driver.y_coord, 2, GB_KEY_UP, 24)
          && advance_value(&driver, driver.x_coord, 10, GB_KEY_RIGHT, 24);
        if (!positioned) {
            fail(&driver, "natural north path did not reach its pre-breakpoint approach");
            goto done;
        }
    }

    if (!calibrate_tick_units(&driver)) goto done;

    for (unsigned frame = 0; frame < driver.options.warmup_frames && !driver.failed; frame++) {
        GB_run_frame(driver.gb);
    }

    char command[1024];
    snprintf(command, sizeof(command), "breakpoint %s", driver.options.origin_label);
    GB_debugger_execute_command(driver.gb, command);
    if (!driver.origin_is_start) {
        if (north_path) {
            /* The two linked North names are exact aliases. SameBoy's reversed
             * symbol map does not retain either duplicate spelling, so install
             * one explicit bank:PC breakpoint derived from the verified pair.
             * This is bank-qualified and adds zero emulated CPU work. */
            snprintf(command, sizeof(command), "breakpoint $%02x:$%04x",
                     driver.operation_start.bank, driver.operation_start.address);
        }
        else {
            snprintf(command, sizeof(command), "breakpoint %s",
                     driver.options.start_label);
        }
        GB_debugger_execute_command(driver.gb, command);
    }
    snprintf(command, sizeof(command), "breakpoint %s", driver.options.end_label);
    GB_debugger_execute_command(driver.gb, command);
    if (!driver.end_is_deadline) {
        snprintf(command, sizeof(command), "breakpoint %s", driver.options.deadline_label);
        GB_debugger_execute_command(driver.gb, command);
    }
    if (vertical_path(&driver)) {
        /* These are observation-only lifecycle seams, not the row's expected
         * breakpoint sequence.  Install their already-verified linked bank
         * and address directly: SameBoy v1.0.3's textual reverse-symbol
         * lookup can retain a stale duplicate spelling for these aliases. */
        snprintf(command, sizeof(command), "breakpoint $%02x:$%04x",
                 driver.owner_end.bank, driver.owner_end.address);
        GB_debugger_execute_command(driver.gb, command);
        snprintf(command, sizeof(command), "breakpoint $%02x:$%04x",
                 driver.deferred_accounting_start.bank,
                 driver.deferred_accounting_start.address);
        GB_debugger_execute_command(driver.gb, command);
    }
    if (north_path) {
        const char *retry_labels[] = {
            "AdmitPreparedFullColorSemanticSelected",
            "FinishFullColorSemanticSelected",
            "RetryFullColorProducer.publish",
        };
        for (unsigned index = 0;
             index < sizeof(retry_labels) / sizeof(retry_labels[0]); index++) {
            snprintf(command, sizeof(command), "breakpoint %s", retry_labels[index]);
            GB_debugger_execute_command(driver.gb, command);
        }
    }
    for (unsigned index = 0; index < driver.options.diagnostic_count; index++) {
        snprintf(command, sizeof(command), "breakpoint %s",
                 driver.options.diagnostic_labels[index]);
        GB_debugger_execute_command(driver.gb, command);
    }
    /* Direct debugger commands do not refresh SameBoy's cached active flag.
     * Re-enable through the public API after installing every breakpoint. */
    GB_debugger_set_disabled(driver.gb, false);

    unsigned prior_completed = 0;
    bool column_movement = strcmp(driver.options.movement_axis, "column") == 0;
    /* Begin on the exact open Pallet routes used by the PyBoy proof. Starting
     * left/up can immediately oscillate against post-lab collision objects
     * without ever crossing a camera strip boundary. */
    GB_key_t sustained_movement_key = north_path ? GB_KEY_UP :
        (column_movement ? GB_KEY_RIGHT : GB_KEY_DOWN);
    if (!party_path) arm_scenario(&driver);
    for (unsigned frame = 0; frame < driver.options.max_frames * driver.options.samples && driver.completed < driver.options.samples && !driver.failed; frame++) {
        if (party_path) {
            press_key(&driver, GB_KEY_START);
            bool menu_ready = false;
            for (unsigned wait = 0; wait < 240; wait++) {
                if (value_is(&driver, driver.max_menu_item, 6) &&
                    value_is(&driver, driver.watched_keys, 0xCB)) {
                    menu_ready = true;
                    break;
                }
                run_frames(&driver, 1);
            }
            if (!menu_ready) {
                fail(&driver, "natural Party path did not open the Start menu");
                break;
            }
            /* wMaxMenuItem is a count: six means this pre-Pokédex route.
             * Select raw item zero; the stock dispatcher increments it before
             * comparing the effective Pokémon item ID (one). */
            uint8_t pokemon_index = value_is(&driver, driver.max_menu_item, 6) ? 0 : 1;
            if (!advance_value(&driver, driver.current_menu_item, pokemon_index, GB_KEY_DOWN, 12)) {
                fail(&driver, "natural Party path did not select Pokemon");
                break;
            }
            arm_scenario(&driver);
            press_key(&driver, GB_KEY_A);
            bool yellow_stable = false;
            for (unsigned wait = 0; wait < 900; wait++) {
                if (read_banked(driver.gb, driver.scenario_state, 4) == driver.options.state_stable_value &&
                    read_banked(driver.gb, driver.scenario_state, 6) == driver.options.ledger_all_value &&
                    read_banked(driver.gb, driver.scenario_state, 8) == driver.options.barrier_stable_value &&
                    read_banked(driver.gb, driver.scenario_state, 9) == 5 &&
                    read_banked(driver.gb, driver.renderer_owner, 0) == driver.options.yellow_owner_value &&
                    read_banked(driver.gb, driver.renderer_phase, 0) == driver.options.yellow_phase_value) {
                    yellow_stable = true;
                    break;
                }
                run_frames(&driver, 1);
            }
            if (!yellow_stable) {
                fail(&driver, "natural Party path did not become stably Yellow-owned");
                break;
            }
            press_key(&driver, GB_KEY_B);
            bool color_complete = false;
            for (unsigned wait = 0; wait < 900; wait++) {
                if (read_banked(driver.gb, driver.scenario_state, 3) == driver.options.result_passed_value &&
                    read_banked(driver.gb, driver.scenario_state, 4) == driver.options.state_complete_value &&
                    read_banked(driver.gb, driver.scenario_state, 7) == driver.options.ledger_all_value &&
                    read_banked(driver.gb, driver.scenario_state, 8) == driver.options.barrier_stable_value &&
                    read_banked(driver.gb, driver.scenario_state, 9) == 5 &&
                    read_banked(driver.gb, driver.renderer_owner, 0) == driver.options.color_owner_value &&
                    read_banked(driver.gb, driver.renderer_phase, 0) == driver.options.color_phase_value) {
                    color_complete = true;
                    break;
                }
                run_frames(&driver, 1);
            }
            if (!color_complete) {
                fail(&driver, "natural Party path did not complete Color reconstruction");
                break;
            }
            run_frames(&driver, 5);
        }
        else if (north_path) {
            bool reached_connection = true;
            if (!value_is(&driver, driver.current_map, 0)) {
                reached_connection = advance_value(
                    &driver, driver.current_map, 0, GB_KEY_DOWN, 48
                );
            }
            if (reached_connection && read_banked(driver.gb, driver.x_coord, 0) != 10) {
                reached_connection = advance_value(
                    &driver, driver.x_coord, 10,
                    read_banked(driver.gb, driver.x_coord, 0) < 10 ? GB_KEY_RIGHT : GB_KEY_LEFT,
                    24
                );
            }
            if (!reached_connection) {
                char message[192];
                snprintf(message, sizeof(message),
                         "natural north path did not reach its Pallet approach (map=%u x=%u y=%u pc=%04x)",
                         read_banked(driver.gb, driver.current_map, 0),
                         read_banked(driver.gb, driver.x_coord, 0),
                         read_banked(driver.gb, driver.y_coord, 0),
                         GB_get_registers(driver.gb)->pc);
                fail(&driver, message);
                break;
            }
            /* Run the final natural Up input at SameBoy's smallest public CPU
             * quantum. The Origin callback releases it immediately, before a
             * frame-sized host pulse can sail past Pallet authority. Ordinary
             * approach-row origins are discarded above; the accepted window
             * still requires the exact bank-qualified connection Start. */
            unsigned starts_before = driver.start_count;
            uint8_t y_before = read_banked(driver.gb, driver.y_coord, 0);
            driver.north_input_released = false;
            GB_set_key_state(driver.gb, GB_KEY_UP, true);
            bool input_window_closed = false;
            bool approach_release = false;
            for (unsigned quantum = 0; quantum < 2000000 && !driver.failed; quantum++) {
                GB_run(driver.gb);
                if (!driver.north_input_released && !approach_release &&
                    read_banked(driver.gb, driver.y_coord, 0) != y_before) {
                    /* A preliminary y=2->1 step has no redraw origin. Turn it
                     * into a complete natural key pulse, then wait until the
                     * game has observed release before issuing another Up. */
                    GB_set_key_state(driver.gb, GB_KEY_UP, false);
                    approach_release = true;
                }
                if (!value_is(&driver, driver.current_map, 0) &&
                    driver.start_count == starts_before) {
                    fail(&driver, "natural North input changed map before exact connection Start");
                    break;
                }
                if (approach_release &&
                    (read_banked(driver.gb, driver.joy_held, 0) & 0x40) == 0) {
                    input_window_closed = true;
                    break;
                }
                if (driver.north_input_released &&
                    driver.expected == EXPECT_DEADLINE) {
                    /* Input is already released at the linked origin. After
                     * exact Start and End, let natural frames advance to the
                     * first owned presentation without issuing more input. */
                    for (unsigned wait = 0;
                         wait < 900 && driver.completed == prior_completed &&
                         !driver.failed; wait++) {
                        run_frames(&driver, 1);
                    }
                    input_window_closed = driver.completed > prior_completed;
                    break;
                }
                if (driver.north_input_released &&
                    (driver.completed > prior_completed || driver.expected == EXPECT_ORIGIN)) {
                    input_window_closed = true;
                    break;
                }
            }
            GB_set_key_state(driver.gb, GB_KEY_UP, false);
            if (!driver.failed && !input_window_closed) {
                uint8_t captured_state = driver.captured_descriptor_slot < 0 ? 0xff :
                    read_banked(driver.gb, driver.request_descriptors,
                                (unsigned)driver.captured_descriptor_slot * DESCRIPTOR_BYTES);
                fprintf(stderr,
                        "phase5-north-deadline final_state=%02x cache=%02x cache_required=%u producer_pending=%u producer_class=%u producer_dest=%04x producer_width=%u producer_height=%u producer_extent=%u request_count=%u cursor=%u retry_admit=%u retry_finish=%u retry_publish=%u retry_result=%u\n",
                        captured_state,
                        read_banked(driver.gb, driver.fast_cache_valid, 0),
                        read_banked(driver.gb, driver.fast_cache_required_cycles, 0) |
                            ((uint16_t)read_banked(driver.gb, driver.fast_cache_required_cycles, 1) << 8),
                        read_banked(driver.gb, driver.producer_pending, 0),
                        driver.producer_snapshot_class,
                        driver.producer_snapshot_destination,
                        driver.producer_snapshot_width,
                        driver.producer_snapshot_height,
                        driver.producer_snapshot_extent,
                        read_banked(driver.gb, driver.request_count, 0),
                        read_banked(driver.gb, driver.request_cursor, 0),
                        driver.records[driver.completed].retry_admit_hits,
                        driver.records[driver.completed].retry_finish_hits,
                        driver.records[driver.completed].retry_publish_hits,
                        driver.records[driver.completed].retry_publish_result);
                for (unsigned slot = 0; slot < DESCRIPTOR_CAPACITY; slot++) {
                    fprintf(stderr, "phase5-north-final-slot%u=", slot);
                    for (unsigned byte = 0; byte < DESCRIPTOR_BYTES; byte++) {
                        fprintf(stderr, "%02x", read_banked(
                            driver.gb, driver.request_descriptors,
                            slot * DESCRIPTOR_BYTES + byte));
                    }
                    fputc('\n', stderr);
                }
                char message[192];
                snprintf(message, sizeof(message),
                         "natural North input did not close at an exact linked seam (map=%u x=%u y=%u expected=%u released=%u)",
                         read_banked(driver.gb, driver.current_map, 0),
                         read_banked(driver.gb, driver.x_coord, 0),
                         read_banked(driver.gb, driver.y_coord, 0),
                         driver.expected, driver.north_input_released);
                fail(&driver, message);
                break;
            }
        }
        else {
            /* Keep natural overworld scrolling active throughout the measured
             * window. Mirror the proven PyBoy right/down route with ordinary
             * press/release pulses; reverse only well inside Pallet's bounds. */
            uint8_t coordinate = read_banked(
                driver.gb, column_movement ? driver.x_coord : driver.y_coord, 0
            );
            GB_key_t wanted = sustained_movement_key;
            if (coordinate <= 3) wanted = column_movement ? GB_KEY_RIGHT : GB_KEY_DOWN;
            else if (coordinate >= (column_movement ? 16 : 14)) {
                wanted = column_movement ? GB_KEY_LEFT : GB_KEY_UP;
            }
            sustained_movement_key = wanted;
            pulse_movement_key(&driver, sustained_movement_key);
        }
        while (prior_completed < driver.completed) {
            capture_postcondition(&driver, prior_completed);
            if (!write_frame(driver.options.frame_dir, prior_completed)) {
                fail(&driver, "could not write SameBoy frame evidence");
                break;
            }
            prior_completed++;
            if (!party_path && driver.completed < driver.options.samples) arm_scenario(&driver);
        }
    }
    if (!driver.failed && driver.completed != driver.options.samples) {
        char message[256];
        snprintf(message, sizeof(message),
                 "SameBoy timed out before all natural executions (expected=%u starts=%u completed=%u pc=%04x map=%u x=%u y=%u owner=%u phase=%u control=%u scenario=%u)",
                 driver.expected, driver.start_count, driver.completed,
                 GB_get_registers(driver.gb)->pc,
                 read_banked(driver.gb, driver.current_map, 0),
                 read_banked(driver.gb, driver.x_coord, 0),
                 read_banked(driver.gb, driver.y_coord, 0),
                 read_banked(driver.gb, driver.renderer_owner, 0),
                 read_banked(driver.gb, driver.renderer_phase, 0),
                 read_banked(driver.gb, driver.control, 0),
                 read_banked(driver.gb, driver.scenario, 0));
        fail(&driver, message);
    }
    if (!driver.failed && driver.start_count != driver.completed) fail(&driver, "SameBoy observed unpaired timing breakpoints");
    if (!driver.failed && !write_json(&driver)) fail(&driver, "could not write SameBoy JSON evidence");

done:
    if (driver.gb) {
        GB_free(driver.gb);
        GB_dealloc(driver.gb);
    }
    if (driver.failed) {
        fprintf(stderr, "%s\n", driver.failure);
        return 1;
    }
    return 0;
}

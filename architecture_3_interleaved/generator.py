"""
=============================================================================
INTELLIGENT MEMORY ARCHITECT (IMA) Generator
=============================================================================
Reads user parameters from config.json, performs hardware math calculations,
selects the appropriate Verilog modules, and auto-generates a parameterized
top-level Verilog wrapper (ima_generated_subsystem.v).

Supported arbiter_type values: "round_robin", "priority", "age_based"
=============================================================================
"""

import json
import math
import os


def load_config(filepath="config.json"):
    """Reads the user parameters from the JSON config file."""
    with open(filepath, "r") as f:
        config = json.load(f)
    return config


def calculate_hardware_parameters(config):
    """
    Converts high-level user requirements into RTL bit-widths and module choices.

    Steps:
      1. Convert memory_size (KB) → total addressable words → ADDR_WIDTH bits
      2. Clamp num_banks to the nearest lower power of 2 (required for LSB interleaving)
      3. Select arbiter module based on arbiter_type
      4. Confirm pipeline_depth from config
    """
    print("=" * 60)
    print("  INTELLIGENT MEMORY ARCHITECT (IMA) - Decision Engine")
    print("=" * 60)

    # --- 1. Address Width Calculation ---
    mem_bytes      = config["memory_size"] * 1024          # KB → bytes
    bytes_per_word = config["data_width"] // 8              # bits → bytes
    total_words    = mem_bytes // bytes_per_word            # total addressable words
    addr_width     = math.ceil(math.log2(total_words))     # bits needed

    print(f"\n[Memory]")
    print(f"  Size          : {config['memory_size']} KB")
    print(f"  Data Width    : {config['data_width']} bits")
    print(f"  Total Words   : {total_words}")
    print(f"  → ADDR_WIDTH  : {addr_width} bits")

    # --- 2. Bank Selection (must be power of 2 for zero-gate LSB interleaving) ---
    num_banks = config["max_banks"]
    if num_banks > 1 and not (num_banks & (num_banks - 1) == 0):
        num_banks = 2 ** int(math.log2(num_banks))
        print(f"  ⚠ max_banks not a power of 2 — clamped to {num_banks}")

    bank_bits = int(math.log2(num_banks))
    row_addr_width = addr_width - bank_bits

    print(f"\n[Banking]")
    print(f"  Architecture  : INTERLEAVED (priority: {config['priority']})")
    print(f"  NUM_BANKS     : {num_banks}  (bank_bits = {bank_bits})")
    print(f"  Row ADDR_WIDTH: {row_addr_width} bits per bank")

    # --- 3. Arbiter Selection ---
    arbiter_map = {
        "round_robin": "arbiter_round_robin",
        "priority":    "arbiter_priority",
        "age_based":   "arbiter_age_based",
    }
    selected_arbiter = arbiter_map.get(config["arbiter_type"], "arbiter_round_robin")

    print(f"\n[Arbitration]")
    print(f"  Requested     : {config['arbiter_type']}")
    print(f"  Module Mapped : {selected_arbiter}")

    # --- 4. Pipeline ---
    pipeline_depth = config["pipeline_depth"]
    print(f"\n[Pipeline]")
    print(f"  Clock Target  : {config['clock_frequency']} MHz")
    print(f"  PIPELINE_DEPTH: {pipeline_depth} {'(output registered)' if pipeline_depth > 0 else '(combinational bypass)'}")

    return {
        "data_width":     config["data_width"],
        "addr_width":     addr_width,
        "num_banks":      num_banks,
        "num_ports":      config["num_ports"],
        "pipeline_depth": pipeline_depth,
        "arbiter_module": selected_arbiter,
    }


def generate_top_wrapper(params, output_dir="output_rtl"):
    """
    Generates ima_generated_subsystem.v — a thin Verilog wrapper that
    instantiates memory_top_interleaved with the computed hardware parameters.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "ima_generated_subsystem.v")

    verilog_code = f"""\
// =============================================================================
// INTELLIGENT MEMORY ARCHITECT (IMA) GENERATOR — AUTO-GENERATED OUTPUT
// =============================================================================
// DO NOT EDIT MANUALLY. Re-run generator.py to regenerate.
//
// Architecture   : INTERLEAVED BANK MEMORY (Architecture 3)
// Total Ports    : {params['num_ports']}
// Memory Banks   : {params['num_banks']}
// Data Width     : {params['data_width']} bits
// Address Width  : {params['addr_width']} bits
// Arbiter Module : {params['arbiter_module']}
// Pipeline Depth : {params['pipeline_depth']}
// =============================================================================

module ima_generated_subsystem (
    input  wire                                                  clk,
    input  wire                                                  reset,

    input  wire [{params['num_ports']}-1:0]                      port_req,
    input  wire [{params['num_ports']}-1:0]                      port_we,
    input  wire [({params['num_ports']}*{params['addr_width']})-1:0]  port_addr,
    input  wire [({params['num_ports']}*{params['data_width']})-1:0]  port_wdata,
    output wire [({params['num_ports']}*{params['data_width']})-1:0]  port_rdata,
    output wire [{params['num_ports']}-1:0]                      port_rvalid
);

    // Auto-generated instantiation of the master Architecture 3 template.
    // All parameters injected from IMA Decision Engine calculations.
    memory_top_interleaved #(
        .DATA_WIDTH    ({params['data_width']}),
        .ADDR_WIDTH    ({params['addr_width']}),
        .NUM_BANKS     ({params['num_banks']}),
        .NUM_PORTS     ({params['num_ports']}),
        .PIPELINE_DEPTH({params['pipeline_depth']})
    ) optimized_memory_core (
        .clk        (clk),
        .reset      (reset),
        .port_req   (port_req),
        .port_we    (port_we),
        .port_addr  (port_addr),
        .port_wdata (port_wdata),
        .port_rdata (port_rdata),
        .port_rvalid(port_rvalid)
    );

endmodule
"""

    with open(filepath, "w") as f:
        f.write(verilog_code)

    print(f"\n[Output]")
    print(f"  ✅ Generated  : {filepath}")


def main():
    print()
    config    = load_config("config.json")
    hw_params = calculate_hardware_parameters(config)

    print("\n" + "=" * 60)
    print("  Generating RTL Wrapper...")
    print("=" * 60)
    generate_top_wrapper(hw_params)

    print("\n🚀 IMA Generator complete. File ready for synthesis.\n")


if __name__ == "__main__":
    main()

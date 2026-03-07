import yaml
import os
import math
from jinja2 import Environment, FileSystemLoader

# -------------------------------------
# Paths
# -------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "templates")
RESULT_DIR = os.path.join(SCRIPT_DIR, "results")

# -------------------------------------
# Load input.yaml
# -------------------------------------

def load_input():

    input_file = os.path.join(SCRIPT_DIR, "input.yaml")

    with open(input_file) as f:
        return yaml.safe_load(f)


# -------------------------------------
# Architecture Selection
# -------------------------------------

def select_architecture(cfg):

    num_ports = cfg["num_ports"]
    read_ports = cfg["read_ports"]
    write_ports = cfg["write_ports"]
    clock_frequency = cfg["clock_frequency"]
    priority = cfg["priority"]
    access_pattern = cfg["access_pattern"]
    num_banks = cfg["num_banks"]
    pipeline_depth = cfg.get("pipeline_depth", 1)

    if clock_frequency >= 800 and pipeline_depth >= 2 and priority == "bandwidth":
        return "pipelined", "High clock frequency and bandwidth priority require pipeline stages."

    elif read_ports >= 3 and write_ports <= 1 and 300 <= clock_frequency <= 1500 and priority == "latency":
        return "replicated", "Multiple read ports require replication to avoid read conflicts."

    elif num_ports >= 4 and priority in ["latency", "bandwidth"] and clock_frequency >= 500:
        return "multiport", "High port count requires true multi-port memory."

    elif access_pattern == "sequential" and num_banks >= 4 and clock_frequency >= 300 and priority == "bandwidth":
        return "interleaved", "Sequential access benefits from bank interleaving."

    elif num_ports >= 2 and access_pattern == "random" and num_banks >= 2 and priority in ["bandwidth", "power"]:
        return "banked", "Random accesses with multiple ports benefit from banked architecture."

    elif num_ports <= 1 and clock_frequency <= 200:
        return "monolithic", "Low port count and low frequency allow simple monolithic memory."

    else:
        return "banked", "Default fallback architecture."

# -------------------------------------
# Compute Parameters
# -------------------------------------

def compute_parameters(cfg):

    params = {}

    params["DATA_WIDTH"] = cfg["data_width"]
    params["MEMORY_SIZE"] = cfg["memory_size"]

    memory_depth = cfg["memory_size"] // cfg["data_width"]
    params["MEMORY_DEPTH"] = memory_depth

    addr_width = math.ceil(math.log2(memory_depth))
    params["ADDR_WIDTH"] = addr_width

    params["NUM_PORTS"] = cfg["num_ports"]

    params["NUM_READ_PORTS"] = cfg["read_ports"]
    params["NUM_WRITE_PORTS"] = cfg["write_ports"]

    # required by some RTL templates
    params["READ_PORTS"] = cfg["read_ports"]
    params["WRITE_PORTS"] = cfg["write_ports"]

    params["N"] = cfg["N"]

    params["NUM_BANKS"] = cfg["num_banks"]
    params["MAX_BANKS"] = cfg["num_banks"]

    bank_index_width = math.ceil(math.log2(cfg["num_banks"]))
    params["BANK_INDEX_WIDTH"] = bank_index_width

    params["BANK_ADDR_WIDTH"] = addr_width - bank_index_width

    if cfg["clock_frequency"] > 700:
        params["PIPELINE_DEPTH"] = 3
    else:
        params["PIPELINE_DEPTH"] = 1

    params["CLOCK_FREQUENCY"] = cfg["clock_frequency"]
    params["ACCESS_PATTERN"] = cfg["access_pattern"]
    params["PRIORITY"] = cfg["priority"]

    params["NUM_REPLICAS"] = cfg["read_ports"]   

    # arbiter + address mapping
    arb_map = {
        "round_robin": 0,
        "priority": 1,
        "age_based": 2
    }

    addr_map = {
        "block": 0,
        "interleaved": 1,
        "xor": 2
    }

    priority_map = {
    "latency": 0,
    "bandwidth": 1
}

    access_map = {
    "random": 0,
    "sequential": 1
}

    params["PRIORITY"] = priority_map.get(cfg["priority"], 0)
    params["ACCESS_PATTERN"] = access_map.get(cfg["access_pattern"], 0)

    params["ARBITER_TYPE"] = arb_map.get(cfg.get("arbiter_type", "round_robin"), 0)
    params["ADDR_MAP_TYPE"] = addr_map.get(cfg.get("addr_map_type", "block"), 0)

    return params


# -------------------------------------
# Create Output Directories
# -------------------------------------

def create_result_dirs(arch):

    base = os.path.join(RESULT_DIR, arch)

    rtl_dir = os.path.join(base, "rtl")
    tb_dir = os.path.join(base, "tb")
    report_dir = os.path.join(base, "reports")

    os.makedirs(rtl_dir, exist_ok=True)
    os.makedirs(tb_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)

    return rtl_dir, tb_dir, report_dir


# -------------------------------------
# Generate Architecture RTL
# -------------------------------------

def generate_architecture_rtl(arch, params):

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    rtl_dir, _, _ = create_result_dirs(arch)

    arch_folder = os.path.join(TEMPLATE_DIR, "architectures", arch)

    if not os.path.exists(arch_folder):
        print("ERROR: Architecture template not found:", arch_folder)
        return

    for root, dirs, files in os.walk(arch_folder):

        for file in files:

            if file.endswith(".j2"):

                full_path = os.path.join(root, file)

                rel_path = os.path.relpath(full_path, TEMPLATE_DIR)
                rel_path = rel_path.replace("\\", "/")

                template = env.get_template(rel_path)

                rendered = template.render(params)

                output_name = file.replace(".j2", "")

                output_path = os.path.join(rtl_dir, output_name)

                with open(output_path, "w") as f:
                    f.write(rendered)

                print("Generated RTL:", output_path)


# -------------------------------------
# Generate Shared Modules
# -------------------------------------

def generate_shared_modules(arch, cfg, params):

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    rtl_dir, _, _ = create_result_dirs(arch)

    # -----------------------------
    # Address Mapping
    # -----------------------------

    if arch in ["pipelined", "interleaved", "banked"]:
        addr_type = "interleaved"
    else:
        addr_type = cfg.get("addr_map_type", "block")

    addr_template = f"shared_modules/address_mapping/address_map_{addr_type}.v.j2"

    template = env.get_template(addr_template)

    rendered = template.render(params)

    output = os.path.join(rtl_dir, f"address_map_{addr_type}.v")

    with open(output, "w") as f:
        f.write(rendered)

    print("Generated:", output)

    # -----------------------------
    # Arbiter
    # -----------------------------

    arbiter_type = cfg.get("arbiter_type", "round_robin")

    arb_template = f"shared_modules/arbiters/arbiter_{arbiter_type}.v.j2"

    template = env.get_template(arb_template)

    rendered = template.render(params)

    output = os.path.join(rtl_dir, f"arbiter_{arbiter_type}.v")

    with open(output, "w") as f:
        f.write(rendered)

    print("Generated:", output)

    # -----------------------------
    # Memory Modules
    # -----------------------------

    mem_folder = os.path.join(TEMPLATE_DIR, "shared_modules", "memory")

    for file in os.listdir(mem_folder):

        if not file.endswith(".j2"):
            continue

        if file == "write_broadcast.v.j2" and arch not in ["replicated", "multiport"]:

            continue

        if file == "read_mux.v.j2" and cfg["read_ports"] <= 1:
            continue

        template_path = f"shared_modules/memory/{file}"

        template = env.get_template(template_path)

        rendered = template.render(params)

        output_name = file.replace(".j2", "")

        output = os.path.join(rtl_dir, output_name)

        with open(output, "w") as f:
            f.write(rendered)

        print("Generated:", output)

    # -----------------------------
    # Pipeline Modules
    # -----------------------------

    if arch in ["pipelined", "multiport"]:

        pipe_folder = os.path.join(TEMPLATE_DIR, "shared_modules", "pipeline")

        for file in os.listdir(pipe_folder):

            if file.endswith(".j2"):

                template_path = f"shared_modules/pipeline/{file}"

                template = env.get_template(template_path)

                rendered = template.render(params)

                output_name = file.replace(".j2", "")

                output = os.path.join(rtl_dir, output_name)

                with open(output, "w") as f:
                    f.write(rendered)

                print("Generated:", output)


# -------------------------------------
# Generate Testbench
# -------------------------------------

def generate_testbench(arch, params):

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    _, tb_dir, _ = create_result_dirs(arch)

    template = env.get_template("testbench/memory_tb.v.j2")

    rendered = template.render(params)

    tb_file = os.path.join(tb_dir, f"{arch}_memory_tb.v")

    with open(tb_file, "w") as f:
        f.write(rendered)

    print("Generated Testbench:", tb_file)



# -------------------------------------
# Generate Detailed Report
# -------------------------------------

def generate_report(arch, reason, cfg, params):

    _, _, report_dir = create_result_dirs(arch)

    report_file = os.path.join(report_dir, "architecture_report.txt")

    memory_kb = cfg["memory_size"] / 1024
    total_bandwidth = cfg["data_width"] * cfg["num_ports"]

    with open(report_file, "w") as f:

        f.write("INTELLIGENT MEMORY ARCHITECTURE GENERATION REPORT\n")
        f.write("=================================================\n\n")

        # ----------------------------------------------------
        # 1. SYSTEM INPUT SPECIFICATION
        # ----------------------------------------------------

        f.write("1. SYSTEM INPUT SPECIFICATION\n")
        f.write("-----------------------------\n\n")

        f.write(f"Total Memory Size : {cfg['memory_size']} bits ({memory_kb:.2f} KB)\n")
        f.write(f"Data Width        : {cfg['data_width']} bits\n")
        f.write(f"Total Ports       : {cfg['num_ports']}\n")
        f.write(f"Read Ports        : {cfg['read_ports']}\n")
        f.write(f"Write Ports       : {cfg['write_ports']}\n")
        f.write(f"Clock Frequency   : {cfg['clock_frequency']} MHz\n")
        f.write(f"Access Pattern    : {cfg['access_pattern']}\n")
        f.write(f"Priority Goal     : {cfg['priority']}\n")
        f.write(f"Maximum Banks     : {cfg['num_banks']}\n\n")

        f.write("""
These parameters define the operational constraints and performance targets
for the generated memory subsystem. The architecture generator analyzes these
inputs to determine the most suitable memory organization capable of meeting
performance, bandwidth, and complexity requirements.
""")

        # ----------------------------------------------------
        # 2. DERIVED MEMORY PARAMETERS
        # ----------------------------------------------------

        f.write("\n2. DERIVED MEMORY PARAMETERS\n")
        f.write("----------------------------\n\n")

        for k, v in params.items():
            f.write(f"{k:20s}: {v}\n")

        f.write("\n")

        f.write(f"""
Memory Depth Calculation
------------------------
Memory depth represents the number of addressable memory words.

Formula:
    MEMORY_DEPTH = MEMORY_SIZE / DATA_WIDTH

Computation:
    MEMORY_DEPTH = {cfg['memory_size']} / {cfg['data_width']} = {params['MEMORY_DEPTH']} words


Address Width Calculation
-------------------------
The address width determines the number of bits required to uniquely
address every word in memory.

Formula:
    ADDR_WIDTH = ceil(log2(MEMORY_DEPTH))

Computed Address Width:
    ADDR_WIDTH = {params['ADDR_WIDTH']} bits
""")

        # ----------------------------------------------------
        # 3. ARCHITECTURE SELECTION
        # ----------------------------------------------------

        f.write("\n3. ARCHITECTURE SELECTION\n")
        f.write("-------------------------\n\n")

        f.write(f"Selected Architecture : {arch.upper()}\n\n")

        f.write("Selection Reason\n")
        f.write("----------------\n")

        f.write(reason + "\n\n")

        f.write("""
The architecture selection algorithm evaluates system constraints including
port count, access patterns, performance priorities, and operating frequency.
Based on these conditions, it chooses the architecture that best balances
performance, complexity, and scalability.
""")

        # ----------------------------------------------------
        # 4. MEMORY ACCESS CHARACTERISTICS
        # ----------------------------------------------------

        f.write("\n4. MEMORY ACCESS CHARACTERISTICS\n")
        f.write("--------------------------------\n\n")

        f.write(f"Total Parallel Ports : {cfg['num_ports']}\n")
        f.write(f"Estimated Peak Bandwidth : {total_bandwidth} bits per cycle\n\n")

        f.write("""
Bandwidth Analysis
------------------
Peak memory bandwidth is estimated as:

    BANDWIDTH = DATA_WIDTH × NUM_PORTS

This represents the theoretical maximum number of bits that can be
transferred per clock cycle assuming no bank conflicts or arbitration delays.
""")

        # ----------------------------------------------------
        # 5. ALTERNATIVE ARCHITECTURES
        # ----------------------------------------------------

        f.write("\n5. ALTERNATIVE ARCHITECTURES CONSIDERED\n")
        f.write("---------------------------------------\n\n")

        alternatives = ["monolithic", "banked", "interleaved", "replicated", "multiport", "pipelined"]

        alternatives.remove(arch)

        for alt in alternatives:
            f.write(f"- {alt}\n")

        f.write("\n")

        f.write("""
The generator evaluates several alternative architectures. While these
architectures may satisfy certain system requirements, they were not selected
because they provide inferior tradeoffs under the given constraints.
""")

        # ----------------------------------------------------
        # 6. ARCHITECTURE TRADEOFF ANALYSIS
        # ----------------------------------------------------

        f.write("\n6. ARCHITECTURE TRADEOFF ANALYSIS\n")
        f.write("---------------------------------\n\n")

        if arch == "replicated":

            f.write("""
Replicated Memory Architecture
------------------------------
Multiple identical memory copies are instantiated so that each read port
can access the memory independently.

Advantages
- Eliminates read contention
- Enables simultaneous reads
- Low read latency

Disadvantages
- Increased silicon area due to replication
- Write operations must update all replicas
""")

        elif arch == "banked":

            f.write("""
Multi-Bank Memory Architecture
------------------------------
Memory is divided into independent banks that can operate concurrently.

Advantages
- Improves memory bandwidth
- Enables parallel access
- Reduces access contention

Disadvantages
- Bank conflicts may stall operations
- Requires arbitration logic
""")

        elif arch == "interleaved":

            f.write("""
Interleaved Memory Architecture
-------------------------------
Sequential memory addresses are distributed across different banks.

Advantages
- Excellent performance for streaming workloads
- Improved parallelism
- Reduced bank conflicts for sequential access

Disadvantages
- Random accesses may still cause conflicts
""")

        elif arch == "multiport":

            f.write("""
Multi-Port Memory Architecture
------------------------------
Multiple read/write ports directly access the memory array.

Advantages
- True simultaneous access
- High flexibility

Disadvantages
- High area cost
- Complex routing and timing
""")

        elif arch == "pipelined":

            f.write("""
Pipelined Memory Architecture
-----------------------------
Memory access is divided into pipeline stages to increase clock frequency.

Advantages
- Supports high clock speeds
- Improved throughput

Disadvantages
- Increased access latency
- More complex control logic
""")

        elif arch == "monolithic":

            f.write("""
Monolithic Memory Architecture
------------------------------
A single unified memory array.

Advantages
- Minimal area
- Simple control logic
- Low power consumption

Disadvantages
- Limited scalability
- Low parallelism
""")

        # ----------------------------------------------------
        # 7. IMPLEMENTATION DETAILS
        # ----------------------------------------------------

        f.write("\n7. IMPLEMENTATION DETAILS\n")
        f.write("-------------------------\n\n")

        f.write("""
The RTL generated for this architecture includes:

- Parameterized memory bank modules
- Address mapping logic
- Arbitration modules
- Pipeline stages (if required)
- Testbench for functional verification

All modules are generated from parameterized templates using Jinja2.
This allows flexible scaling of memory size, port count, and banking
configuration without modifying the RTL source code manually.
""")

        # ----------------------------------------------------
        # 8. SUMMARY
        # ----------------------------------------------------

        f.write("\n8. SUMMARY\n")
        f.write("----------\n\n")

        f.write(f"""
Based on the provided system constraints, the generator selected the
{arch.upper()} architecture as the most appropriate implementation.

The decision was primarily influenced by:

- Port configuration
- Access pattern
- Target clock frequency
- Performance priority

The generated RTL implements the derived memory depth, address width,
bank configuration, and pipeline structure necessary to satisfy these
requirements.
""")

    print("Generated Detailed Report:", report_file)

# -------------------------------------
# Main
# -------------------------------------

def main():

    cfg = load_input()

    arch, reason = select_architecture(cfg)

    print("\nSelected Architecture:", arch)

    params = compute_parameters(cfg)

    params["ARCHITECTURE"] = arch

    generate_architecture_rtl(arch, params)

    generate_shared_modules(arch, cfg, params)

    generate_testbench(arch, params)

    generate_report(arch, reason, cfg, params)

    print("\nGeneration Completed")

    print("\nResults located at:")

    print(f"{RESULT_DIR}/{arch}/")

if __name__ == "__main__":
    main()
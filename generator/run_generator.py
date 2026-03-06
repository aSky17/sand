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
# Load user input
# -------------------------------------

def load_input():

    input_path = os.path.join(SCRIPT_DIR, "input.yaml")

    with open(input_path) as f:
        return yaml.safe_load(f)


# -------------------------------------
# Architecture decision logic
# -------------------------------------

def select_architecture(cfg):

    if cfg["read_ports"] > 2:
        return "replicated"

    if cfg["priority"] == "bandwidth":
        return "banked"

    if cfg["clock_frequency"] > 700:
        return "pipelined"

    if cfg["access_pattern"] == "sequential":
        return "interleaved"

    return "monolithic"


# -------------------------------------
# Compute RTL parameters
# -------------------------------------

def compute_parameters(cfg):

    params = {}

    # Basic parameters
    params["DATA_WIDTH"] = cfg["data_width"]
    params["MEMORY_SIZE"] = cfg["memory_size"]

    # Memory depth (word based)
    memory_depth = cfg["memory_size"] // cfg["data_width"]
    params["MEMORY_DEPTH"] = memory_depth

    # Address width
    addr_width = math.ceil(math.log2(memory_depth))
    params["ADDR_WIDTH"] = addr_width

    # Port parameters
    params["NUM_PORTS"] = cfg["num_ports"]
    params["NUM_READ_PORTS"] = cfg["read_ports"]
    params["NUM_WRITE_PORTS"] = cfg["write_ports"]

    # Banking parameters
    params["NUM_BANKS"] = cfg["num_banks"]

    bank_index_width = math.ceil(math.log2(cfg["num_banks"]))
    params["BANK_INDEX_WIDTH"] = bank_index_width

    params["BANK_ADDR_WIDTH"] = addr_width - bank_index_width

    # Pipeline decision
    if cfg["clock_frequency"] > 700:
        params["PIPELINE_DEPTH"] = 3
    else:
        params["PIPELINE_DEPTH"] = 1

    # Control parameters
    params["CLOCK_FREQUENCY"] = cfg["clock_frequency"]
    params["ACCESS_PATTERN"] = cfg["access_pattern"]
    params["PRIORITY"] = cfg["priority"]

    return params


# -------------------------------------
# Create result folders
# -------------------------------------

def create_result_dirs(arch):

    base = os.path.join(RESULT_DIR, arch)

    rtl_dir = os.path.join(base, "rtl")
    report_dir = os.path.join(base, "reports")

    os.makedirs(rtl_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)

    return rtl_dir


# -------------------------------------
# Generate RTL files
# -------------------------------------

def generate_rtl(arch, params):

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    rtl_dir = create_result_dirs(arch)

    template_path = os.path.join(TEMPLATE_DIR, "architectures", arch)

    if not os.path.exists(template_path):
        print(f"ERROR: Architecture template folder not found: {template_path}")
        return

    for root, dirs, files in os.walk(template_path):

        for file in files:

            if file.endswith(".j2"):

                full_path = os.path.join(root, file)

                rel_path = os.path.relpath(full_path, TEMPLATE_DIR)

                # Fix Windows path for Jinja
                rel_path = rel_path.replace("\\", "/")

                template = env.get_template(rel_path)

                output_text = template.render(params)

                # Remove .j2 extension
                output_filename = os.path.basename(file).replace(".j2", "")

                output_file = os.path.join(rtl_dir, output_filename)

                with open(output_file, "w") as f:
                    f.write(output_text)

                print("Generated:", output_file)


# -------------------------------------
# Main generator
# -------------------------------------

def main():

    cfg = load_input()

    arch = select_architecture(cfg)

    print("Selected Architecture:", arch)

    params = compute_parameters(cfg)

    params["ARCHITECTURE"] = arch

    generate_rtl(arch, params)

    print("\nResults stored in:")
    print(f"results/{arch}/")


if __name__ == "__main__":
    main()
# Complete In-Depth Theory of Architecture 3 — Interleaved Multi-Port Memory Subsystem

Below is a **complete in-depth theory of Architecture 3 — Interleaved Multi-Port Memory Subsystem**, written in a way that will help you both **understand the concept deeply and justify it in your hackathon presentation/report.**

---

## 1. Motivation

Modern SoC (System-on-Chip) designs contain multiple processor cores, DMA engines, and accelerators that all share a common memory space. Each of these agents constantly competes to read and write data. A naïve single-port memory can only serve **one request per clock cycle**, which creates a catastrophic serialization bottleneck.

The deeper problem is **spatial locality**. CPUs and GPUs naturally access memory in sequential patterns — if core A reads address `0x00`, there is a very high probability (>80%) the next access is `0x01`, then `0x02`. In a standard **block-mapped** memory, all these addresses live in the same physical bank. When two cores simultaneously need `0x00` and `0x01`, they collide at the same bank — one core must stall and wait.

**Architecture 3 exists to solve this exact problem** by distributing sequential addresses across physically separate memory banks, transforming what would be a collision into a perfectly parallel, zero-wait memory access.

---

## 2. Core Idea

The central innovation is **address interleaving**: instead of mapping a block of consecutive addresses to one bank, we cyclically distribute them across all banks.

| Address | Block-Mapped Bank | Interleaved Bank |
|---------|-------------------|------------------|
| 0x0000  | Bank 0            | Bank 0           |
| 0x0001  | Bank 0            | Bank 1           |
| 0x0002  | Bank 0            | Bank 2           |
| 0x0003  | Bank 0            | Bank 3           |
| 0x0004  | Bank 0            | Bank 0           |
| 0x0005  | Bank 0            | Bank 1           |

With interleaving, when Core 0 asks for `0x0000` and Core 1 asks for `0x0001` simultaneously, they are routed to **Bank 0 and Bank 1** — completely independent physical SRAMs that fire in parallel. **Bandwidth scales linearly with the number of active banks.**

The crossbar routing matrix connects every port to every bank, making this a **fully non-blocking interconnect** as long as no two ports target the same bank in the same cycle.

---

## 3. Pipeline Stages

Architecture 3 operates as a **2-stage memory pipeline** when `PIPELINE_DEPTH = 1`:

```
Stage 1 (Combinational):
  Port Address → Address Mapper → Bank Selector → Arbiter → SRAM Write/Read

Stage 2 (Registered):
  SRAM Read Output → Read Mux → Pipeline D-FF → Port Read Data + Valid Signal
```

**Stage 1** is entirely combinational — address decoding, bank selection, arbitration, and SRAM access all happen within a single clock cycle.

**Stage 2** registers the output. The D-flip-flop at the read output breaks the combinational critical path, enabling the design to run at a higher clock frequency (lower cycle time).

When `PIPELINE_DEPTH = 0`, Stage 2 is bypassed and the read data is purely combinational — lower latency but lower maximum Fmax.

---

## 4. Dataflow

A complete read transaction flows through the system as follows:

```
[Port p sends: addr, req=1, we=0]
         │
         ▼
[address_map_interleaved]
  bank_id = addr[BANK_BITS-1:0]   ← zero gate, zero cycle
         │
         ▼
[bank_selector]
  bank_enable[bank_id] = 1        ← one-hot decode
         │
         ▼
[bank_req_matrix[b][p] = 1]       ← crossbar injection
         │
         ▼
[arbiter_round_robin (per bank)]
  grant[p] = 1 if port wins       ← conflict resolved
         │
         ▼
[memory_bank (SRAM)]
  read_data = mem[row_addr]       ← synchronous read on posedge clk
         │
         ▼
[read_mux]
  selects correct bank's rdata    ← per-port output selection
         │
         ▼
[pipeline_stage (if enabled)]
  data_out <= data_in             ← registered on posedge clk
         │
         ▼
[port_rdata, port_rvalid]         ← output to processor
```

A write transaction follows the same path through Stage 1, but bypasses the read mux and pipeline stage entirely.

---

## 5. Address Mapping and Banking

The mathematical basis of interleaving is modular arithmetic:

> **Bank_ID = Address MOD NUM_BANKS**

In general hardware, `MOD` requires a divider — a large, slow, and power-hungry circuit. Architecture 3 eliminates this by **restricting `NUM_BANKS` to a power of 2** (2, 4, 8, 16 …).

For any power of 2 value $2^k$:

$$\text{Address} \mod 2^k = \text{Address}[k-1:0]$$

This means taking the bank ID is just **reading the bottom `k` bits** of the address — no arithmetic, no gates, just wires.

```verilog
localparam BANK_BITS = $clog2(NUM_BANKS);  // e.g. 2 for 4 banks
assign bank = addr[BANK_BITS-1:0];         // Pure wire assignment
```

The **upper bits** (`addr[ADDR_WIDTH-1:BANK_BITS]`) form the **row address** — the actual index within each bank's internal SRAM array.

| Parameter | Value (default config) |
|-----------|----------------------|
| ADDR_WIDTH | 16 bits (64KB space) |
| NUM_BANKS  | 4 banks              |
| BANK_BITS  | 2 bits (addr[1:0])   |
| ROW_ADDR   | 14 bits per bank     |
| Bank depth | 2^14 = 16,384 words  |

---

## 6. Arbitration

The crossbar matrix creates a potential conflict scenario: two or more ports can simultaneously request the same memory bank. Without arbitration, both ports would drive the SRAM's address/data lines simultaneously, causing data corruption.

**Per-bank Round-Robin Arbitration** resolves this:

- Each of the `NUM_BANKS` banks has its own dedicated `arbiter_round_robin` instance.
- The arbiter maintains a rotating `pointer` register.
- On each cycle, it scans starting from `pointer + 1` around the ring and grants access to the **first requesting port it encounters**.
- After granting, the pointer advances to the winning port, ensuring the **next conflict will favor a different port**.

**Why round-robin over fixed priority?**

- **Fixed priority** always grants Port 0 first → Port 1 can starve indefinitely under heavy load.
- **Round-robin** guarantees every port gets access within `N` conflict cycles → no starvation, fair bandwidth distribution.
- **Age-based** (available as an alternative) prioritizes the port that has waited longest, ideal for latency-sensitive mixed workloads.

---

## 7. Hazard Handling

In pipelined memory systems, **hazards** are conditions where incorrect data could be read if not managed carefully.

**Read-After-Write (RAW) Hazard:**
With `PIPELINE_DEPTH = 1`, a write in cycle `T` is committed to the SRAM. A read of the same address in cycle `T+1` will correctly receive the written data because the SRAM is synchronous and the write completes at the end of cycle `T`. ✅

**Write-After-Write (WAW) Hazard:**
If two ports write to the same bank in the same cycle, the arbiter allows only one through at a time. The second port's grant is deferred to the next cycle. ✅

**Write-After-Read (WAR) / Structural Hazard:**
The `bank_active` signal (`|bank_gnt_matrix[b]`) gates the SRAM write-enable. If no port wins the arbiter (impossible in a valid request scenario), the SRAM is not written. ✅

> [!NOTE]
> Architecture 3 does **not** implement forwarding or write buffers. For applications requiring guaranteed single-cycle read-after-write, `PIPELINE_DEPTH` should be set to `0` (fully combinational mode) at the cost of reduced Fmax.

---

## 8. Throughput vs. Latency

These two metrics trade off directly in Architecture 3:

| Mode | PIPELINE_DEPTH | Read Latency | Max Throughput | Fmax |
|------|---------------|--------------|----------------|------|
| Bypass | 0 | 1 cycle | 1 read/cycle/port | Lower |
| Pipelined | 1 | 2 cycles | 1 read/cycle/port (sustained) | Higher |

**Throughput** is the sustained data rate. In both modes, once the pipeline is full, the system delivers **1 word per cycle per active port** — it does not decrease with depth.

**Latency** is the time from request to valid data appearing. Adding the pipeline stage costs exactly 1 extra clock cycle.

**Fmax** (maximum clock frequency) improves with pipelining because the combinational path is cut in half. For a 500 MHz target (as in `config.json`), the pipeline stage is **mandatory** — the combinational path through arbiter + SRAM + mux is too long for a 2ns cycle time without it.

**Peak theoretical bandwidth:**
$$\text{BW} = \text{NUM\_BANKS} \times \text{DATA\_WIDTH} \times F_{clk}$$
$$= 4 \times 32 \text{ bits} \times 500 \text{ MHz} = 64 \text{ GB/s}$$

---

## 9. Timing Model

The **critical path** (longest combinational delay chain) in Architecture 3 without pipelining:

```
Port Address Register
  → address_map_interleaved  (wire slice: ~0 ns)
  → bank_selector            (~0.1 ns, simple for-loop mux)
  → arbiter_round_robin      (~0.3 ns, combinational priority scan)
  → memory_bank              (~0.8 ns, SRAM access time)
  → read_mux                 (~0.1 ns, output select)
  → Port Read Data Register
```

Estimated total: **~1.3 ns** → supports up to ~770 MHz without pipelining (technology dependent).

**With pipeline stage inserted after `read_mux`:**

- Stage 1 path: Port → SRAM output (~1.2 ns)
- Stage 2 path: SRAM output → D-FF input (~0.1 ns)

Both stages are well within a 2ns (500 MHz) clock budget, with margin for routing and hold-time closure.

---

## 10. Hardware Blocks

| Module | Type | Function | Gates (approx.) |
|--------|------|----------|-----------------|
| `address_map_interleaved` | Combinational | LSB extraction for bank routing | 0 (pure wire) |
| `bank_selector` | Combinational | Binary to one-hot decoder | ~N gates |
| `arbiter_round_robin` | Sequential | Fair multi-port conflict resolution | ~N×log2(N) FFs |
| `memory_bank` | Sequential | Synchronous SRAM (Dual-purpose R/W) | SRAM macro |
| `read_mux` | Combinational | Route bank output to port | ~N×DATA_WIDTH gates |
| `pipeline_stage` | Sequential | Output D-FF register chain | DATA_WIDTH FFs |
| `memory_top_interleaved` | Structural | P×N crossbar integration top | (instantiates all above) |

**Total instance count** at default parameters (4 banks, 2 ports):
- 2× `address_map_interleaved`
- 2× `bank_selector`
- 4× `arbiter_round_robin`
- 4× `memory_bank`
- 2× `read_mux`
- 2× `pipeline_stage`

---

## 11. Design Parameters

All parameters are injected at synthesis time — no RTL modification required.

| Parameter | Type | Default | Valid Range | Effect |
|-----------|------|---------|-------------|--------|
| `DATA_WIDTH` | int | 32 | 8–128 | Word size in bits |
| `ADDR_WIDTH` | int | 16 | 8–32 | Total address space |
| `NUM_BANKS` | int | 4 | 2, 4, 8, 16 | **Must be power of 2.** Multiplies bandwidth linearly. |
| `NUM_PORTS` | int | 2 | 1–8 | Number of independent R/W ports |
| `PIPELINE_DEPTH` | int | 1 | 0 or 1 | 0 = combinational, 1 = registered output |

**Scaling example:** Setting `NUM_BANKS = 16, NUM_PORTS = 4` auto-generates:
- 64 crossbar routing paths
- 16 independent arbiters
- 16 SRAM banks
- 4 read muxes and 4 pipeline stages
— all without modifying a single line of RTL.

---

## 12. Integration with the IMA Generator

`generator.py` is the **Decision Engine** that bridges user intent (in `config.json`) and synthesizable hardware (Verilog wrappers).

**Flow:**

```
config.json
    │
    ▼
generator.py
  ├─ memory_size × 1024 / (data_width/8) → total_words → log2 → ADDR_WIDTH
  ├─ max_banks (clamped to power of 2)   → NUM_BANKS
  ├─ arbiter_type → arbiter_round_robin / arbiter_priority / arbiter_age_based
  └─ pipeline_depth → PIPELINE_DEPTH
    │
    ▼
output_rtl/ima_generated_subsystem.v
  └─ Instantiates memory_top_interleaved with computed parameters
```

**Example output for default config (64KB, 32-bit, 4 banks, 2 ports, 500MHz):**

```verilog
memory_top_interleaved #(
    .DATA_WIDTH(32),
    .ADDR_WIDTH(14),   // log2(64K / 4 bytes) = 14
    .NUM_BANKS(4),
    .NUM_PORTS(2),
    .PIPELINE_DEPTH(1)
) optimized_memory_core ( ... );
```

The Python script validates that `NUM_BANKS` is a power of 2 and automatically corrects if the user provides an invalid value, ensuring synthesizability is never broken.

---

## 13. Real-World Usage

Architecture 3 directly mirrors memory subsystems found in production silicon:

| Domain | Usage |
|--------|-------|
| **GPU Shared Memory** | NVIDIA's shared memory in each SM is interleaved across 32 banks. Sequential thread accesses map to different banks, enabling 32× parallel memory bandwidth. |
| **CPU L1/L2 Cache** | Multi-way set-associative caches use interleaved SRAM arrays to avoid same-bank conflicts during load/store pairs from out-of-order execution. |
| **DDR/LPDDR DRAM** | Multiple DRAM banks are interleaved at the rank level. Memory controllers pre-activate different banks to hide row access latency (tRAS). |
| **FPGA Block RAMs** | Xilinx and Intel FPGAs use multiple BRAM tiles with interleaved address mapping to achieve multi-port memory with built-in arbitration. |
| **Network Switch Buffers** | Packet buffers in high-speed switching ASICs use interleaved banks to simultaneously enqueue and dequeue packets at line rate. |

**In the context of your IMA Generator**, a designer can describe a 256KB shared memory for 8 DSP cores in `config.json`, and the generator will emit synthesizable RTL with 8 banks, 8 ports, 64 crossbar paths, and all arbitration — turning days of manual RTL work into a single script run.

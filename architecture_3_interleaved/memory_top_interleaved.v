// =============================================================================
// MEMORY TOP - INTERLEAVED BANK ARCHITECTURE (Architecture 3)
// =============================================================================
// Implements a fully parameterized, multi-port interleaved memory subsystem.
// Key features:
//   - P x N Crossbar routing matrix (P ports, N banks)
//   - Zero-latency address interleaving via LSB extraction
//   - Per-bank round-robin arbitration (starvation-free)
//   - Optional output pipeline stage for high-Fmax designs
//   - Fully scalable: all logic auto-generated via generate loops
// =============================================================================

module memory_top_interleaved #(
    parameter DATA_WIDTH    = 32,
    parameter ADDR_WIDTH    = 16,
    parameter NUM_BANKS     = 4,
    parameter NUM_PORTS     = 2,
    parameter PIPELINE_DEPTH = 1 // 1 = enable output pipeline stage, 0 = bypass
)(
    input  wire                                      clk,
    input  wire                                      reset,

    // Per-port request interface (flattened arrays)
    input  wire [NUM_PORTS-1:0]                      port_req,
    input  wire [NUM_PORTS-1:0]                      port_we,
    input  wire [(NUM_PORTS*ADDR_WIDTH)-1:0]         port_addr,
    input  wire [(NUM_PORTS*DATA_WIDTH)-1:0]         port_wdata,

    // Per-port read response
    output wire [(NUM_PORTS*DATA_WIDTH)-1:0]         port_rdata,
    output wire [NUM_PORTS-1:0]                      port_rvalid
);

    localparam BANK_BITS     = $clog2(NUM_BANKS);
    localparam ROW_ADDR_WIDTH = ADDR_WIDTH - BANK_BITS;

    // -------------------------------------------------------------------------
    // Internal wire arrays for the crossbar matrix
    // -------------------------------------------------------------------------
    wire [BANK_BITS-1:0]              mapped_bank_id  [0:NUM_PORTS-1];
    wire [NUM_BANKS-1:0]              port_bank_en    [0:NUM_PORTS-1];
    wire [NUM_PORTS-1:0]              bank_req_matrix [0:NUM_BANKS-1];
    wire [NUM_PORTS-1:0]              bank_gnt_matrix [0:NUM_BANKS-1];
    wire [(NUM_BANKS*DATA_WIDTH)-1:0] all_banks_rdata;

    genvar p, b;

    // =========================================================================
    // 1. ADDRESS MAPPING & BANK DECODING (Per Port)
    //    Each port independently maps its address to a target bank and
    //    generates a one-hot bank enable vector.
    // =========================================================================
    generate
        for (p = 0; p < NUM_PORTS; p = p + 1) begin : gen_decoders
            wire [ADDR_WIDTH-1:0] p_addr = port_addr[p*ADDR_WIDTH +: ADDR_WIDTH];

            address_map_interleaved #(
                .ADDR_WIDTH(ADDR_WIDTH),
                .NUM_BANKS(NUM_BANKS)
            ) addr_map (
                .addr(p_addr),
                .bank(mapped_bank_id[p])
            );

            bank_selector #(
                .NUM_BANKS(NUM_BANKS)
            ) b_sel (
                .bank_id   (mapped_bank_id[p]),
                .enable    (port_req[p]),
                .bank_enable(port_bank_en[p])
            );
        end
    endgenerate

    // =========================================================================
    // 2. ARBITRATION & CROSSBAR MATRIX (Per Bank)
    //    Each bank has its own dedicated arbiter. Conflicting port requests
    //    are resolved by round-robin arbitration. The winning port's address
    //    and data are muxed into the SRAM.
    // =========================================================================
    generate
        for (b = 0; b < NUM_BANKS; b = b + 1) begin : gen_banks

            // Build the request column for this bank across all ports
            for (p = 0; p < NUM_PORTS; p = p + 1) begin : gen_req_route
                assign bank_req_matrix[b][p] = port_bank_en[p][b];
            end

            // Per-bank round-robin arbiter
            arbiter_round_robin #(
                .N(NUM_PORTS)
            ) arbiter (
                .clk   (clk),
                .reset (reset),
                .req   (bank_req_matrix[b]),
                .grant (bank_gnt_matrix[b])
            );

            // Mux: Select winning port's row address, write data, and write enable
            reg [ROW_ADDR_WIDTH-1:0] final_row_addr;
            reg [DATA_WIDTH-1:0]     final_wdata;
            reg                      final_we;
            wire                     bank_active = |bank_gnt_matrix[b];

            integer k;
            always @(*) begin
                final_row_addr = 0;
                final_wdata    = 0;
                final_we       = 0;
                for (k = 0; k < NUM_PORTS; k = k + 1) begin
                    if (bank_gnt_matrix[b][k]) begin
                        // Strip the interleave bits; use the upper bits as the row address
                        final_row_addr = port_addr[k*ADDR_WIDTH + BANK_BITS +: ROW_ADDR_WIDTH];
                        final_wdata    = port_wdata[k*DATA_WIDTH +: DATA_WIDTH];
                        final_we       = port_we[k];
                    end
                end
            end

            // SRAM instance for this bank
            wire [DATA_WIDTH-1:0] b_rdata;
            memory_bank #(
                .DATA_WIDTH(DATA_WIDTH),
                .ADDR_WIDTH(ROW_ADDR_WIDTH)
            ) sram (
                .clk        (clk),
                .we         (final_we & bank_active),
                .addr       (final_row_addr),
                .write_data (final_wdata),
                .read_data  (b_rdata)
            );

            // Concatenate all bank read outputs into flattened bus
            assign all_banks_rdata[b*DATA_WIDTH +: DATA_WIDTH] = b_rdata;

        end
    endgenerate

    // =========================================================================
    // 3. READ ROUTING & OPTIONAL PIPELINING (Per Port)
    //    Each port's read_mux selects the correct bank's data.
    //    If PIPELINE_DEPTH > 0, data passes through a D-FF stage to
    //    break the critical path and support higher clock frequencies.
    // =========================================================================
    generate
        for (p = 0; p < NUM_PORTS; p = p + 1) begin : gen_outputs
            wire [DATA_WIDTH-1:0] muxed_data;

            read_mux #(
                .NUM_BANKS(NUM_BANKS),
                .DATA_WIDTH(DATA_WIDTH)
            ) r_mux (
                .bank_select(mapped_bank_id[p]),
                .bank_data  (all_banks_rdata),
                .read_data  (muxed_data)
            );

            if (PIPELINE_DEPTH > 0) begin : pipelined
                pipeline_stage #(.WIDTH(DATA_WIDTH)) pipe (
                    .clk      (clk),
                    .reset    (reset),
                    .data_in  (muxed_data),
                    .valid_in (port_req[p] & ~port_we[p]),
                    .data_out (port_rdata[p*DATA_WIDTH +: DATA_WIDTH]),
                    .valid_out(port_rvalid[p])
                );
            end else begin : bypass
                assign port_rdata[p*DATA_WIDTH +: DATA_WIDTH] = muxed_data;
                assign port_rvalid[p] = port_req[p] & ~port_we[p];
            end
        end
    endgenerate

endmodule

module address_map_interleaved #(
    parameter ADDR_WIDTH = 16,
    parameter NUM_BANKS = 4
)(
    input  wire [ADDR_WIDTH-1:0]        addr,
    output wire [$clog2(NUM_BANKS)-1:0] bank
);
    // Zero-latency, zero-gate bank routing.
    // Sequential addresses map to different banks via their LSBs.
    // Bank_ID = Address % NUM_BANKS => just the bottom $clog2(NUM_BANKS) bits.
    localparam BANK_BITS = $clog2(NUM_BANKS);
    assign bank = addr[BANK_BITS-1:0];
endmodule

module write_broadcast
#(
    parameter NUM_REPLICAS = {{NUM_REPLICAS}},
parameter ADDR_WIDTH   = {{ADDR_WIDTH}},
parameter DATA_WIDTH   = {{DATA_WIDTH}}
)
(
    input wire write_enable,
    input wire [ADDR_WIDTH-1:0] write_addr,
    input wire [DATA_WIDTH-1:0] write_data,

    output wire [NUM_REPLICAS-1:0] we_out,
    output wire [NUM_REPLICAS*ADDR_WIDTH-1:0] addr_out,
    output wire [NUM_REPLICAS*DATA_WIDTH-1:0] data_out
);

genvar i;

generate
    for(i = 0; i < NUM_REPLICAS; i = i + 1) begin : broadcast

        assign we_out[i] = write_enable;

        assign addr_out[i*ADDR_WIDTH +: ADDR_WIDTH] = write_addr;

        assign data_out[i*DATA_WIDTH +: DATA_WIDTH] = write_data;

    end
endgenerate

endmodule
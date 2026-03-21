module arbiter_round_robin #(
    parameter N = 4
)(
    input  wire         clk,
    input  wire         reset,
    input  wire [N-1:0] req,
    output reg  [N-1:0] grant
);
    // Prevents starvation by rotating the grant pointer after each cycle.
    // If Port 0 wins this cycle, Port 1 is guaranteed to win the next conflict.
    reg [$clog2(N)-1:0] pointer;
    integer i, index;
    reg found;

    // Combinational grant logic: searches from pointer+1 around the ring
    always @(*) begin
        grant = 0; found = 0;
        for(i = 1; i <= N; i = i + 1) begin
            index = (pointer + i) % N;
            if(req[index] && !found) begin
                grant[index] = 1'b1;
                found = 1'b1;
            end
        end
    end

    // Sequential pointer update
    always @(posedge clk or posedge reset) begin
        if(reset) pointer <= 0;
        else begin
            for(i = 0; i < N; i = i + 1)
                if(grant[i]) pointer <= i;
        end
    end
endmodule

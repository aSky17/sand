module arbiter_age_based
#(
    parameter N         = {{N}},
parameter AGE_WIDTH = {{AGE_WIDTH}}
)
(
    input wire clk,
    input wire reset,

    input wire [N-1:0] req,
    output reg [N-1:0] grant
);

reg [AGE_WIDTH-1:0] age [0:N-1];

integer i;
integer max_index;
reg [AGE_WIDTH-1:0] max_age;

always @(posedge clk or posedge reset) begin
    if(reset) begin
        for(i=0;i<N;i=i+1)
            age[i] <= 0;
    end
    else begin
        for(i=0;i<N;i=i+1) begin
            if(req[i])
                age[i] <= age[i] + 1;
            else
                age[i] <= 0;
        end
    end
end

always @(*) begin
    grant = 0;
    max_age = 0;
    max_index = 0;

    for(i=0;i<N;i=i+1) begin
        if(req[i] && age[i] >= max_age) begin
            max_age = age[i];
            max_index = i;
        end
    end

    if(req[max_index])
        grant[max_index] = 1'b1;
end

endmodule
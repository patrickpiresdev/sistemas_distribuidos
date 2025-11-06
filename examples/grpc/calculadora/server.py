import grpc
from concurrent import futures

import calc_pb2 as pb
import calc_pb2_grpc as pb_grpc
import numpy as np

class CalculatorServicer(pb_grpc.CalculatorServicer):
    def Add(self, request, context):
        return pb.Result(value=request.a + request.b)

    def Mul(self, request, context):
        return pb.Result(value=request.a * request.b)

    def Div(self, request, context):
        if request.b == 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Division by zero")
        return pb.Result(value=request.a / request.b)
def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb_grpc.add_CalculatorServicer_to_server(CalculatorServicer(), server)
    server.add_insecure_port("[::]:50051")
    print("Servidor gRPC ouvindo em 0.0.0.0:50051")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()

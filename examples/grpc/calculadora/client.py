import grpc

import calc_pb2 as pb
import calc_pb2_grpc as pb_grpc

def main():
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = pb_grpc.CalculatorStub(channel)

        r1 = stub.Add(pb.BinaryOp(a=10, b=5))
        print("Add(10,5) =", r1.value)

        r2 = stub.Mul(pb.BinaryOp(a=7, b=6))
        print("Mul(7,6) =", r2.value)

        try:
            r3 = stub.Div(pb.BinaryOp(a=10, b=0))
            print("Div(10,0) =", r3.value)
        except grpc.RpcError as e:
            print("Erro em Div(10,0):", e.code().name, e.details())

        r4 = stub.Div(pb.BinaryOp(a=10, b=4))
        print("Div(10,4) =", r4.value)

if __name__ == "__main__":
    main()

import sys
import grpc

import logan_pb2 as pb
import logan_pb2_grpc as pb_grpc

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "example.log"
    with grpc.insecure_channel("localhost:50051") as channel:
        stub = pb_grpc.LogServiceStub(channel)
        request = pb.LogRequest(path=path)
        try:
            for event in stub.StreamLogs(request):
                print(f"[{event.lineno:02d}] {event.level:7} | {event.line}")
        except grpc.RpcError as e:
            print("Erro gRPC:", e.code().name, e.details())

if __name__ == "__main__":
    main()

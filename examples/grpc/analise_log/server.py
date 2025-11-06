import grpc
from concurrent import futures

import logan_pb2 as pb
import logan_pb2_grpc as pb_grpc

def infer_level(line: str) -> str:
    line_up = line.upper()
    if "ERROR" in line_up:
        return "ERROR"
    if "WARN" in line_up:
        return "WARN"
    if "INFO" in line_up:
        return "INFO"
    return "UNKNOWN"

class LogServiceServicer(pb_grpc.LogServiceServicer):
    def StreamLogs(self, request, context):
        path = request.path
        try:
            with open(path, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f, start=1):
                    line = line.strip()
                    yield pb.LogEvent(
                        lineno=idx,
                        level=infer_level(line),
                        line=line
                    )
        except FileNotFoundError:
            context.abort(grpc.StatusCode.NOT_FOUND, f"Arquivo não encontrado: {path}")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
    pb_grpc.add_LogServiceServicer_to_server(LogServiceServicer(), server)
    server.add_insecure_port("[::]:50051")
    print("Servidor ouvindo em 0.0.0.0:50051")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()

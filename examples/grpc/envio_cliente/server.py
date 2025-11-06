import os
import grpc
from concurrent import futures

import file_pb2 as pb
import file_pb2_grpc as pb_grpc


class FileServiceServicer(pb_grpc.FileServiceServicer):
    def Upload(self, request_iterator, context):
        """
        Handler de client-streaming:
        - request_iterator: itera sobre UploadChunk enviados pelo cliente
        - retorna um único UploadStatus no final
        """
        out_dir = "uploads"
        os.makedirs(out_dir, exist_ok=True)

        file_handle = None
        saved_path = None
        total = 0
        filename_seen = None

        try:
            for chunk in request_iterator:
                # na 1ª iteração, abrimos o arquivo
                if file_handle is None:
                    filename_seen = chunk.filename.strip()
                    # sanitiza nome simples (sem diretórios do cliente)
                    filename_seen = os.path.basename(filename_seen)
                    saved_path = os.path.join(out_dir, filename_seen)
                    file_handle = open(saved_path, "wb")

                # valida nome consistente (opcional)
                if chunk.filename and os.path.basename(chunk.filename) != filename_seen:
                    # Abortamos se o cliente mudar o nome no meio do stream
                    context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                                  "filename mudou durante o upload")

                if chunk.data:
                    file_handle.write(chunk.data)
                    total += len(chunk.data)

            # fim do stream
            if file_handle:
                file_handle.close()

            return pb.UploadStatus(
                ok=True,
                message="Upload concluído",
                bytes_received=total,
                saved_path=saved_path,
            )

        except Exception as e:
            if file_handle:
                try:
                    file_handle.close()
                except:
                    pass
            # Em caso de erro interno
            context.abort(grpc.StatusCode.INTERNAL, f"Falha no upload: {e}")


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    pb_grpc.add_FileServiceServicer_to_server(FileServiceServicer(), server)
    server.add_insecure_port("[::]:50051")
    print("Servidor gRPC (Upload) ouvindo em 0.0.0.0:50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()

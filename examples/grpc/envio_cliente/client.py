import os
import sys
import grpc

import file_pb2 as pb
import file_pb2_grpc as pb_grpc


def chunked_file_reader(path, send_name=None, chunk_size=1024):
    """Gera UploadChunk em blocos para o stub.Upload."""
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            yield pb.UploadChunk(filename=send_name, data=data)


def main():
    # Uso:
    #   python client.py <arquivo_local> [nome_no_servidor]
    #
    # Ex:
    #   python client.py exemplo.txt exemplo_remoto.txt
    if len(sys.argv) < 2:
        print("Uso: python client.py <arquivo_local> [nome_no_servidor]")
        sys.exit(1)

    local_path = sys.argv[1]
    remote_name = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.isfile(local_path):
        print(f"Arquivo local não encontrado: {local_path}")
        sys.exit(1)

    with grpc.insecure_channel("localhost:50051") as channel:
        stub = pb_grpc.FileServiceStub(channel)
        try:
            status = stub.Upload(chunked_file_reader(local_path, remote_name))
            print("OK?" , status.ok)
            print("Msg:", status.message)
            print("Bytes recebidos:", status.bytes_received)
            print("Salvo em:", status.saved_path)
        except grpc.RpcError as e:
            print("Erro gRPC:", e.code().name, e.details())


if __name__ == "__main__":
    main()


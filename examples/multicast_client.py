#!/usr/bin/env python3
"""
examples/multicast_client.py

Cliente multicast simples: envia mensagens JSON para um grupo multicast IPv4.
Pode enviar mensagens interativamente ou apenas uma vez com --once/--message.
Também pode aguardar respostas unicast (timeout configurável).

Exemplos:
  python examples/multicast_client.py --group 224.0.0.1 --port 5007 --name Cliente1
  python examples/multicast_client.py --once --message "Olá" --timeout 3
  python examples/multicast_client.py --iface 192.168.1.11 --name PC --timeout 5
"""

import argparse
import json
import socket
import struct
import time
import uuid
import sys


def get_default_interface():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def parse_args():
    p = argparse.ArgumentParser(description='Cliente multicast UDP simples')
    p.add_argument('--group', default='224.0.0.1', help='Endereço do grupo multicast (padrão: 224.0.0.1)')
    p.add_argument('--port', type=int, default=5007, help='Porta UDP (padrão: 5007)')
    p.add_argument('--iface', default=None, help='IP da interface local a usar (opcional)')
    p.add_argument('--name', default=None, help='Nome exibido nas mensagens (padrão: hostname)')
    p.add_argument('--ttl', type=int, default=1, help='TTL do multicast (padrão: 1)')
    p.add_argument('--timeout', type=float, default=2.0, help='Tempo (s) para aguardar resposta unicast (padrão: 2s)')
    p.add_argument('--once', action='store_true', help='Enviar apenas uma mensagem e sair')
    p.add_argument('--message', default=None, help='Mensagem a enviar com --once')
    return p.parse_args()


def main():
    args = parse_args()
    group = args.group
    port = args.port
    iface = args.iface or get_default_interface()
    name = args.name or socket.gethostname()
    ttl = args.ttl
    timeout = args.timeout

    local_id = uuid.uuid4().hex

    dest = (group, port)

    # Cria socket UDP e vincula a uma porta efêmera para poder receber respostas
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass

    # Opcional: bind a ('', 0) para receber respostas
    try:
        sock.bind(('', 0))
    except Exception:
        pass

    # TTL
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('b', ttl))
    except Exception:
        pass

    # Forçar interface de saída multicast
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
    except Exception:
        # ignora, não crítico
        pass

    print(f"Enviando para {group}:{port} via iface {iface} (TTL={ttl}) — pressione Ctrl-C para sair")

    def send_text(text):
        msg = {'id': local_id, 'name': name, 'text': text, 'ts': time.time()}
        b = json.dumps(msg).encode('utf-8')
        try:
            sock.sendto(b, dest)
        except Exception as e:
            print(f"Erro ao enviar: {e}")

    try:
        if args.once:
            text = args.message if args.message is not None else input('Mensagem: ')
            send_text(text)
            # aguardar resposta opcional
            sock.settimeout(timeout)
            try:
                data, addr = sock.recvfrom(65536)
                try:
                    print('Resposta de', addr, data.decode('utf-8'))
                except Exception:
                    print('Resposta bruta de', addr, data)
            except socket.timeout:
                pass
            return

        # modo interativo
        while True:
            try:
                text = input()
            except (EOFError, KeyboardInterrupt):
                print('\nSaindo...')
                break
            if not text:
                continue
            send_text(text)
            # aguardar resposta curta
            sock.settimeout(timeout)
            try:
                data, addr = sock.recvfrom(65536)
                try:
                    print('Resposta de', addr, data.decode('utf-8'))
                except Exception:
                    print('Resposta bruta de', addr, data)
            except socket.timeout:
                # sem resposta — continue
                pass

    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()

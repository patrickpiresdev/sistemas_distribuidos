#!/usr/bin/env python3
"""
examples/multicast_server.py

Servidor UDP que ingressa em um grupo multicast IPv4 e exibe mensagens recebidas.
Opcionalmente responde (unicast) ao remetente com um echo.

Exemplos:
  python examples/multicast_server.py --group 224.0.0.1 --port 5007
  python examples/multicast_server.py --group 239.255.0.1 --port 5007 --iface 192.168.1.10 --reply

Observações:
 - Em sistemas com múltiplas interfaces, informe --iface para garantir que o join use a interface correta.
 - Verifique firewall/antivírus para permitir UDP na porta escolhida.
"""

import argparse
import socket
import struct
import time
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
    p = argparse.ArgumentParser(description='Servidor multicast UDP simples')
    p.add_argument('--group', default='224.0.0.1', help='Endereço do grupo multicast (padrão: 224.0.0.1)')
    p.add_argument('--port', type=int, default=5007, help='Porta UDP (padrão: 5007)')
    p.add_argument('--iface', default=None, help='IP da interface local a usar (opcional)')
    p.add_argument('--reply', action='store_true', help='Enviar resposta unicast de eco ao remetente')
    p.add_argument('--bufsize', type=int, default=65536, help='Tamanho do buffer para recvfrom')
    return p.parse_args()


def main():
    args = parse_args()
    group = args.group
    port = args.port
    iface = args.iface or get_default_interface()
    reply = args.reply

    print(f'Grupo: {group}, porta: {port}, iface: {iface}, reply: {reply}')

    # Cria socket UDP para multicast
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass

    # Em muitos sistemas bind em '' (INADDR_ANY) permite receber datagramas multicast na porta
    try:
        sock.bind(('', port))
    except Exception as e:
        print(f'Falha ao bind na porta {port}: {e}')
        sys.exit(1)

    # Preparar IP_ADD_MEMBERSHIP com o IP da interface
    group_bin = socket.inet_aton(group)
    try:
        iface_bin = socket.inet_aton(iface)
    except Exception:
        iface_bin = socket.inet_aton('0.0.0.0')

    mreq = struct.pack('4s4s', group_bin, iface_bin)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except Exception as e:
        # tentar com 0.0.0.0 como fallback
        try:
            fallback = struct.pack('4s4s', group_bin, socket.inet_aton('0.0.0.0'))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, fallback)
            print('Usando fallback INADDR_ANY para IP_ADD_MEMBERSHIP')
        except Exception as e2:
            print(f'Erro ao ingressar no grupo multicast: {e} / {e2}')
            sock.close()
            sys.exit(1)

    print('Servidor multicast pronto. Aguardando mensagens...')

    try:
        while True:
            try:
                data, addr = sock.recvfrom(args.bufsize)
            except InterruptedError:
                continue
            if not data:
                continue
            ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            try:
                text = data.decode('utf-8')
            except Exception:
                text = repr(data)
            print(f'[{ts}] {addr[0]}:{addr[1]} -> {text}')

            if reply:
                resp = f'Echo from multicast-server: {text}'
                try:
                    # responder diretamente ao remetente (unicast)
                    sock.sendto(resp.encode('utf-8'), addr)
                except Exception as e:
                    print(f'Falha ao enviar resposta para {addr}: {e}')

    except KeyboardInterrupt:
        print('\nInterrompido pelo usuário, saindo...')
    finally:
        # Tenta sair do grupo
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except Exception:
            pass
        sock.close()


if __name__ == '__main__':
    main()

"""
multicast_chat.py
Um chat simples via multicast UDP.

Como usar (ex.):
    python multicast_chat.py --name PC1

Funciona em duas ou mais máquinas na mesma rede. Envia mensagens para o grupo multicast e exibe mensagens recebidas.
"""

import argparse
import json
import socket
import struct
import threading
import time
import uuid
import sys


def get_default_interface():
    """Tenta descobrir o IP da interface padrão (não faz conexões externas duradouras).
    Usa um socket UDP para um endereço público (não envia dados) para inferir o IP local.
    Retorna uma string com o IP, ou '0.0.0.0' se não for possível.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Não precisa que o destino seja alcançável, apenas para revelar a interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"

def make_socket(bind_ip, port, mcast_group, ttl=1, iface=None, loop=True, debug=False):
    """Cria socket UDP para enviar/receber multicast.

    - bind_ip: IP para bind ('' ou '0.0.0.0' para todas)
    - iface: endereço IP da interface de rede a usar ao ingressar no grupo
    - loop: habilita loopback de multicast (receber as próprias mensagens)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # Permitir reuso de endereço/porta
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass

    # Bind para receber datagramas do grupo
    sock.bind((bind_ip, port))

    # TTL (alcance do multicast)
    try:
        ttl_bin = struct.pack('b', ttl)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl_bin)
    except Exception:
        if debug:
            print('Aviso: não foi possível ajustar IP_MULTICAST_TTL')

    # Controla loopback (receber nossas próprias mensagens) - habilitado por padrão
    try:
        loop_val = 1 if loop else 0
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, loop_val)
    except Exception:
        if debug:
            print('Aviso: não foi possível ajustar IP_MULTICAST_LOOP')

    # Juntar ao grupo multicast
    group = socket.inet_aton(mcast_group)
    # Interface para juntar no grupo (use 0.0.0.0 para "qualquer" — em alguns SOs funciona melhor usar o IP real da interface)
    iface_ip = iface or get_default_interface() or '0.0.0.0'
    try:
        mreq = struct.pack('4s4s', group, socket.inet_aton(iface_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        if debug:
            print(f'Ingressou no grupo multicast {mcast_group} na interface {iface_ip}')
    except Exception:
        # Em alguns sistemas (Windows) pode ser necessário empacotar diferente; tentar usar INADDR_ANY
        try:
            mreq = struct.pack('4s4s', group, socket.inet_aton('0.0.0.0'))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except Exception as e:
            if debug:
                print(f'Erro ao ingressar no grupo multicast: {e}')
            raise

    # Especifica a interface de saída para mensagens multicast (ajuda em sistemas com múltiplas NICs)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface_ip))
        if debug:
            print(f'Interface de saída multicast ajustada para {iface_ip}')
    except Exception:
        if debug:
            print('Aviso: não foi possível ajustar IP_MULTICAST_IF')

    return sock


def listener(sock, local_id, encoding='utf-8'):
    while True:
        try:
            data, addr = sock.recvfrom(65536)
        except OSError:
            print('oserror')
            break
        if not data:
            continue
        try:
            obj = json.loads(data.decode(encoding, errors='replace'))
        except Exception:
            # mensagem não JSON -> pular
            continue
        # Ignorar mensagens do mesmo id (evitar eco)
        if obj.get('id') == local_id:
            continue
        name = obj.get('name', 'unknown')
        text = obj.get('text', '')
        ts = obj.get('ts')
        stamp = ''
        if ts:
            try:
                stamp = time.strftime('%H:%M:%S', time.localtime(float(ts)))
            except Exception:
                stamp = str(ts)
        print(f"[{stamp}] {name}@{addr[0]}:{addr[1]}: {text}")


def sender_loop(sock, mcast_group, port, local_id, name, encoding='utf-8'):
    dest = (mcast_group, port)
    print("Digite mensagens e pressione Enter para enviar. Ctrl-C para sair.")
    while True:
        try:
            text = input()
        except (EOFError, KeyboardInterrupt):
            print("\nSaindo e limpando...")
            break
        if not text:
            continue
        msg = {
            'id': local_id,
            'name': name,
            'text': text,
            'ts': time.time()
        }
        b = json.dumps(msg).encode(encoding)
        try:
            sock.sendto(b, dest)
        except Exception as e:
            print(f"Erro ao enviar: {e}")


def parse_args():
    p = argparse.ArgumentParser(description='Chat multicast simples (UDP)')
    p.add_argument('--group', default='224.0.0.1', help='Endereço do grupo multicast (padrão: 224.0.0.1)')
    p.add_argument('--port', type=int, default=5007, help='Porta UDP (padrão: 5007)')
    p.add_argument('--name', default=None, help='Nome exibido no chat (padrão: hostname)')
    p.add_argument('--ttl', type=int, default=1, help='TTL do multicast (padrão: 1)')
    p.add_argument('--iface', default=None, help='IP da interface de rede a usar (opcional). Se não informado, será detectado automaticamente.')
    p.add_argument('--loop', action='store_true', default=False, help='Permitir receber as próprias mensagens (útil para testes locais).')
    return p.parse_args()


def main():
    args = parse_args()
    name = args.name or socket.gethostname()
    mcast_group = args.group
    port = args.port
    ttl = args.ttl

    local_id = uuid.uuid4().hex

    # Escolhe interface
    iface_ip = args.iface or get_default_interface()

    # Cria socket para envio/recepção
    try:
        # Em muitos sistemas bind em '' funciona bem para receber
        sock = make_socket('', port, mcast_group, ttl=ttl, iface=iface_ip, loop=args.loop, debug=True)
    except Exception as e:
        print(f"Falha ao criar socket multicast: {e}")
        sys.exit(1)

    # Thread de escuta
    t = threading.Thread(target=listener, args=(sock, local_id), daemon=True)
    t.start()

    try:
        sender_loop(sock, mcast_group, port, local_id, name)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            # remover do grupo (opcional)
            drop_iface = iface_ip or '0.0.0.0'
            mreq = struct.pack('4s4s', socket.inet_aton(mcast_group), socket.inet_aton(drop_iface))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()

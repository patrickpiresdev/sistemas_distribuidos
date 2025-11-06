#!/usr/bin/env python3
"""
examples/multicast_peer.py

Peer P2P multicast: cada processo ingressa em um grupo multicast, escuta mensagens
e permite enviar mensagens JSON ao grupo. Inclui opções para forçar interface,
controle de TTL, receber próprias mensagens (loop) e responder aos remetentes.

Uso:
  python examples/multicast_peer.py --name PC1
  python examples/multicast_peer.py --group 239.255.0.1 --port 5007 --iface 192.168.1.10 --reply

O peer imprime mensagens recebidas em tempo real e evita eco usando um identificador único.
"""

import argparse
import json
import socket
import struct
import threading
import time
import uuid
import sys
import logging


logger = logging.getLogger(__name__)


def get_default_interface():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def make_mcast_socket(bind_port, mcast_group, iface=None, ttl=1, loop=True, debug=False):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass

    # Bind para receber datagramas multicast
    try:
        sock.bind(("", bind_port))
    except Exception as e:
        raise

    # TTL
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('b', ttl))
    except Exception:
        if debug:
            logger.warning('Aviso: não foi possível ajustar IP_MULTICAST_TTL')

    # Loopback control
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1 if loop else 0)
    except Exception:
        if debug:
            logger.warning('Aviso: não foi possível ajustar IP_MULTICAST_LOOP')

    # Join group usando IP da interface, se fornecido
    group_bin = socket.inet_aton(mcast_group)
    iface_ip = iface or get_default_interface() or '0.0.0.0'
    try:
        mreq = struct.pack('4s4s', group_bin, socket.inet_aton(iface_ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        logger.info(f'Ingressou no grupo {mcast_group} na interface {iface_ip}')
    except Exception:
        # fallback
        try:
            mreq = struct.pack('4s4s', group_bin, socket.inet_aton('0.0.0.0'))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            logger.info('Ingressou no grupo usando INADDR_ANY (fallback)')
        except Exception as e:
            logger.exception('Erro ao ingressar no grupo multicast: %s', e)
            raise

    # Define interface de saída multicast
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface_ip))
    except Exception:
        if debug:
            logger.warning('Aviso: não foi possível ajustar IP_MULTICAST_IF')

    return sock


def listener_thread(sock, local_id, reply=False, debug=False):
    logger.debug('Listener thread started')
    while True:
        try:
            logger.debug('Waiting to receive data...')
            data, addr = sock.recvfrom(65536)
            logger.debug('Data received')
        except OSError:
            logger.info('OSError in listener thread, exiting')
            break
        if not data:
            logger.info('No data received, continuing')
            continue
        # tentar decodificar JSON
        try:
            obj = json.loads(data.decode('utf-8', errors='replace'))
        except Exception:
            # não JSON -> exibir como texto bruto
            try:
                text = data.decode('utf-8')
            except Exception:
                text = repr(data)
            ts = time.strftime('%H:%M:%S')
            logger.info(f'[{ts}] {addr[0]}:{addr[1]} -> {text}')
            continue

        # Ignorar mensagens locais (eco)
        if obj.get('id') == local_id:
            if debug:
                logger.debug('Ignorando mensagem local (eco)')
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
        logger.info(f'[{stamp}] {name}@{addr[0]}:{addr[1]}: {text}')

        if reply:
            resp = json.dumps({'id': uuid.uuid4().hex, 'name': 'peer-reply', 'text': f'Echo: {text}', 'ts': time.time()}).encode('utf-8')
            try:
                sock.sendto(resp, addr)
                if debug:
                    logger.debug(f'Resposta enviada para {addr}')
            except Exception as e:
                if debug:
                    logger.exception('Falha ao enviar resposta: %s', e)


def parse_args():
    p = argparse.ArgumentParser(description='Peer multicast P2P (envia e recebe mensagens via multicast)')
    p.add_argument('--group', default='239.0.0.1', help='Endereço do grupo multicast')
    p.add_argument('--port', type=int, default=5007, help='Porta UDP')
    p.add_argument('--iface', default=None, help='IP da interface local a usar (opcional)')
    p.add_argument('--name', default=None, help='Nome exibido nas mensagens (padrão: hostname)')
    p.add_argument('--ttl', type=int, default=1, help='TTL do multicast')
    p.add_argument('--reply', action='store_true', help='Responder (unicast) às mensagens recebidas')
    p.add_argument('--loop', action='store_true', help='Permitir receber as próprias mensagens (útil para testes locais)')
    p.add_argument('--once', action='store_true', help='Enviar uma mensagem e sair (use com --message)')
    p.add_argument('--message', default=None, help='Mensagem a enviar quando usar --once')
    p.add_argument('--debug', action='store_true', help='Modo debug (logs adicionais)')
    p.add_argument('--logfile', default='multicast_peer.log', help='Arquivo para gravar logs (padrão: multicast_peer.log)')
    return p.parse_args()


def main():
    args = parse_args()
    group = args.group
    port = args.port
    iface = args.iface or get_default_interface()
    name = args.name or socket.gethostname()
    ttl = args.ttl
    reply = args.reply
    loop = args.loop
    debug = args.debug

    local_id = uuid.uuid4().hex

    # Configure logging: file + console (console INFO, file DEBUG/INFO)
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    fh = logging.FileHandler(args.logfile)
    fh.setLevel(level)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    try:
        sock = make_mcast_socket(port, group, iface=iface, ttl=ttl, loop=loop, debug=debug)
    except Exception as e:
        logger.exception('Falha ao criar socket multicast: %s', e)
        sys.exit(1)

    # Start listener thread
    t = threading.Thread(target=listener_thread, args=(sock, local_id, reply, debug), daemon=True)
    t.start()

    dest = (group, port)

    def send_text(text):
        logger.debug('sending text: %s', text)
        msg = {'id': local_id, 'name': name, 'text': text, 'ts': time.time()}
        b = json.dumps(msg).encode('utf-8')
        try:
            sock.sendto(b, dest)
            logger.debug('message sent')
        except Exception as e:
            logger.exception('Erro ao enviar mensagem: %s', e)

    try:
        if args.once:
            text = args.message if args.message is not None else input('Mensagem: ')
            send_text(text)
            time.sleep(0.5)
            return

        logger.info('Digite mensagens e pressione Enter para enviar. Ctrl-C para sair.')
        while True:
            try:
                text = input()
                logger.debug('going to send: %s', text)
            except (EOFError, KeyboardInterrupt):
                logger.info('\nSaindo...')
                break
            logger.debug('going to send: %s', text)
            if not text:
                logger.debug('not text')
                continue
            send_text(text)

    finally:
        try:
            # tentar dropar membership
            group_bin = socket.inet_aton(group)
            iface_bin = socket.inet_aton(iface or '0.0.0.0')
            mreq = struct.pack('4s4s', group_bin, iface_bin)
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
            except Exception:
                pass
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()

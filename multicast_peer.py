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


def get_default_interface_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def make_mcast_socket(bind_port, mcast_group, iface_ip=None, ttl=1, loop=True, debug=False):
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


def listener_thread(sock, state, debug=False):
    """Listener que também implementa comportamento do coordenador quando state['is_coordinator']==True.

    state: dict compartilhado com chaves: is_coordinator (bool), members (dict), next_id (int).
    """
    logger.debug('Listener thread started')
    group, port = state.get('group'), state.get('port')
    while True:
        try:
            logger.debug('Waiting to receive data...')
            data, addr = sock.recvfrom(65536)
            logger.debug('Data received from %s', addr)
        except OSError:
            logger.info('OSError in listener thread, exiting')
            break
        if not data:
            logger.info('No data received, continuing')
            continue
        # tentar decodificar JSON
        try:
            obj = json.loads(data.decode('utf-8', errors='replace'))
            logger.debug('Data decoded as JSON: %s', obj)
        except Exception:
            # não JSON -> exibir como texto bruto
            try:
                text = data.decode('utf-8')
            except Exception:
                text = repr(data)
            ts = time.strftime('%H:%M:%S')
            # logger.info(f'[{ts}] {addr[0]}:{addr[1]} -> {text}')
            continue

        if obj.get('to') not in ('all', state.get('id')):
            if debug:
                logger.debug('Mensagem não destinada a este peer (to=%s), ignorando', obj.get('to'))
            continue

        # protocolo: tratar mensagens administrativas quando houver 'type'
        mtype = obj.get('type')

        # Ignorar mensagens locais (eco) — campo id das mensagens de chat
        if obj.get('id') == state.get('id'):
            if debug:
                logger.debug('Ignorando mensagem local (eco)')
                logger.debug('Id local: %s', state.get('id'))
                logger.debug('Mensagem ignorada: %s', obj)
            continue

        # Se for mensagem administrativa e somos coordenador, tratar
        if mtype == 'whois' and is_coordinator(state):
            resp = message(sender_id=state['id'], mtype='iam', to=obj.get('id'))
            try:
                # responder por multicast para que o solicitante descubra o endereço do coordenador
                sock.sendto(json.dumps(resp).encode('utf-8'), (group, port))
                logger.debug('Respondido whois via multicast')
            except Exception:
                logger.exception('Falha ao responder whois')

            # whois não são exibidos como chat
            continue

        if mtype == 'iam': # todo: verificar necessidade pos inclusao do campo 'to' nas mensagens
            # recepção de anúncio de coordenador — ignorar aqui (main já usou discovery)
            continue

        if mtype == 'join_request' and is_coordinator(state):
            logger.debug('Recebido join_request de %s', addr)
            if is_coordinator(state):
                # atribuir id único e responder unicast
                name = obj.get('name', 'unknown')
                logger.debug('Atribuindo id para novo membro: %s', name)
                ip = addr[0]
                assigned_id = f'{name}@{ip}' # apenas o 'ip' ja bastava, pois ja eh um identificador unico que a rede resolve para mim, so estou adicionando o nome pelo requisito de atribuição de id para o trabalho
                if assigned_id in state['members']:
                    logger.debug('Membro %s já existe, gerando id complementar', assigned_id)
                    complement = uuid.uuid4().hex[:6]
                    assigned_id = f'{name}_{complement}@{ip}'
                state['members'].append(assigned_id)
                content = {'assigned_id': assigned_id, 'members': state['members']}
                ack = message(sender_id=state['id'], mtype='join_ack', to=obj.get('id'), content=content)

                try:
                    logger.debug('Enviando join_ack %s para %s', ack, addr)
                    sock.sendto(json.dumps(ack).encode('utf-8'), (group, port))
                    logger.info('Atribuído id %s para %s (%s)', assigned_id, obj.get('name'), addr)
                except Exception:
                    logger.exception('Falha ao enviar join_ack')
            continue

        if mtype == 'join_ack': # todo: verificar necessidade pos inclusao do campo 'to' nas mensagens
            # join_ack recebido — main thread trata de join, aqui apenas ignorar
            continue

        if mtype == 'chat':
            try:
                peer_id = obj.get('id')
                text = obj.get('content', {}).get('text', '')
                ts = obj.get('ts')
                stamp = ''
                if ts:
                    try:
                        stamp = time.strftime('%H:%M:%S', time.localtime(float(ts)))
                    except Exception:
                        stamp = str(ts)
                logger.info(f'[{stamp}] {peer_id}: {text}')
            except Exception:
                logger.exception('Erro ao processar mensagem recebida: %s', obj)
                continue


def parse_args():
    p = argparse.ArgumentParser(description='Peer multicast P2P (envia e recebe mensagens via multicast)')
    p.add_argument('--group', default='239.0.0.1', help='Endereço do grupo multicast')
    p.add_argument('--port', type=int, default=5007, help='Porta UDP')
    p.add_argument('--name', default=None, help='Nome exibido nas mensagens (padrão: hostname)')
    p.add_argument('--ttl', type=int, default=1, help='TTL do multicast')
    p.add_argument('--loop', action='store_true', help='Permitir receber as próprias mensagens (útil para testes locais)')
    p.add_argument('--debug', action='store_true', help='Modo debug (logs adicionais)')
    p.add_argument('--logfile', default='multicast_peer.log', help='Arquivo para gravar logs (padrão: multicast_peer.log)')
    p.add_argument('--join-timeout', type=float, default=2.0, help='Tempo (s) para descobrir coordenador/aguardar join_ack (padrão: 2.0)')
    return p.parse_args()


def is_coordinator(state):
    return state.get('id') == state.get('coordinator_id')


def wait_reply(sock, reply_type='all', reply_from='all', reply_to='all', timeout=2.0):
    while True:
        sock.settimeout(timeout)
        try:
            data, addr = sock.recvfrom(65536)
            obj = json.loads(data.decode('utf-8', errors='replace'))
            logger.debug('Dados recebidos de %s: %s', addr, obj)
            if reply_type != 'all' and obj['type'] != reply_type:
                logger.debug('Tipo de mensagem %s não corresponde ao esperado %s, ignorando', obj['type'], reply_type)
                continue
            if reply_from != 'all' and obj.get('id') != reply_from:
                logger.debug('Mensagem de %s não corresponde ao esperado %s, ignorando', addr[0], reply_from)
                continue
            if reply_to != 'all' and obj.get('to') != reply_to:
                logger.debug('Mensagem para id %s não corresponde ao esperado %s, ignorando', obj.get('id'), reply_to)
                continue
            return obj, addr
        except socket.timeout:
            return None
        finally:
            sock.settimeout(None)


def message(sender_id, mtype, to='all', content=None):
    return {'id': sender_id, 'to': to, 'type': mtype, 'content': content, 'ts': time.time()}


def send_text(sock, state, text):
    group, port = state['group'], state['port']
    logger.debug('sending text: %s', text)
    msg = message(sender_id=state['id'], mtype='chat', content={'text': text})
    b = json.dumps(msg).encode('utf-8')
    try:
        sock.sendto(b, (group, port))
        logger.debug('message sent')
    except Exception as e:
        logger.exception('Erro ao enviar mensagem: %s', e)


def main():
    args = parse_args()
    group = args.group
    port = args.port
    name = args.name or socket.gethostname()
    ttl = args.ttl
    loop = args.loop
    debug = args.debug
    logfile = args.logfile
    join_timeout = args.join_timeout
    iface_ip = get_default_interface_ip() or '0.0.0.0'

    # Configure logging: file + console (console INFO, file DEBUG/INFO)
    setup_logger(logfile, debug)

    with make_mcast_socket(port, group, iface_ip=iface_ip, ttl=ttl, loop=loop, debug=debug) as sock:
        # State for coordinator logic
        state = build_state(group, port)

        # DISCOVERY: procurar coordenador enviando whois e aguardando iam
        state['coordinator_id'] = get_coordinator(sock, state)

        if state['coordinator_id'] is None: # nenhum coordenador detectado -> assumir coordenação
            assume_coordination(name, state)

        # Se não for coordenador, enviar join_request e aguardar join_ack
        if not is_coordinator(state):
            connect_to_chat(sock, state, join_timeout)

        # Start listener thread (após discovery/join)
        t = threading.Thread(target=listener_thread, args=(sock, state, debug), daemon=True)
        t.start()

        logger.info('Digite mensagens e pressione Enter para enviar. Ctrl-C para sair.')
        while True:
            try:
                text = input('>>> ')
                logger.debug('sending: %s', text)
                send_text(sock, state, text)
            except (EOFError, KeyboardInterrupt):
                logger.info('\nSaindo...')
                break

def build_state(group, port):
    temp_id = uuid.uuid4().hex
    return {'id': temp_id, 'members': [], 'group': group, 'port': port, 'coordinator_id': None}


def connect_to_chat(sock, state, join_timeout):
    logger.info('Iniciando entrada na chat...')
    group, port = state['group'], state['port']
    join_req = message(sender_id=state['id'], mtype='join_request', to=state['coordinator_id'])
    tries = 3

    old_id = state['id']
    for attempt in range(tries):
        try:
            sock.sendto(json.dumps(join_req).encode('utf-8'), (group, port))
            logger.debug('Enviado join_request para %s', state['coordinator_id'])
        except Exception:
            logger.exception('Falha ao enviar join_request')

        sock.settimeout(join_timeout)
        logger.debug('Aguardando join_ack...')
        reply = wait_reply(sock, reply_type='join_ack', reply_to=state['id'])
            
        if reply is None:
            logger.debug('Timeout aguardando join_ack (tentativa %d/%d)', attempt + 1, tries)
            continue

        obj, _addr = reply
        logger.debug('join_ack recebido: %s', obj)

        content = obj.get('content', {})
        state['id'] = content.get('assigned_id', old_id)
        state['members'] = content.get('members', [])
        break

    if state['id'] == old_id:
        logger.error('Não foi possível entrar no chat')
        sys.exit(1)

    logger.info('entrada na rede concluída com id %s', state['id'])

def assume_coordination(name, state):
    local_ip = socket.gethostbyname(socket.gethostname())
    state['id'] = f'{name}@{local_ip}'
    state['coordinator_id'] = state['id']
    state['members'].append(state['id'])
    logger.info('Nenhum coordenador encontrado — assumindo coordenação (id=%s)', state['coordinator_id'])

def get_coordinator(sock, state):
    group, port = state['group'], state['port']
    logger.info('Procurando coordenador no grupo %s:%d...', group, port)
    whois = message(sender_id=state['id'], mtype='whois')

    # enviar whois algumas vezes para aumentar chance de receber
    for _ in range(3):
        try:
            sock.sendto(json.dumps(whois).encode('utf-8'), (group, port))
            logger.debug('Enviado whois para %s:%d', group, port)
        except Exception:
            logger.exception('Falha ao enviar whois')

        logger.debug('Aguardando iam do coordenador...')
        reply = wait_reply(sock, reply_type='iam', reply_to=state['id'])

        if reply is None:
            logger.debug('Timeout aguardando iam')
            continue

        obj, _addr = reply
        coord_id = obj.get('id')
        logger.info('Coordenador %s detectado', coord_id)
        return coord_id
    
    return None

def setup_logger(logfile, debug):
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    fh = logging.FileHandler(logfile)
    fh.setLevel(level)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)


if __name__ == '__main__':
    main()

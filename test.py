import multicast_peer as mp

group = '239.0.0.1'
port = 5007
sock = mp.make_mcast_socket(port, group, mp.get_default_interface_ip(), debug=False)

state = mp.build_state(group, port, 'outsider')
mp.send_text(sock, state, 'ola de fora!')

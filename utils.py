import requests
import os


def http_get(url, token):
    response = requests.get(url,headers = {'x-auth-token':token,'content-type':'application/json'})
    return response.json()


def register_port_to_file(file_path, mode, data, mac_addr, ip_addr, sport, dport):
    f = open(file_path, mode)
    f.write(data)
    f.close()


def get_ports_and_routers(neutron_endpoint, admin_token):
    match_ports = []
    list_routers_url = '{}/routers'.format(neutron_endpoint)
    routers = http_get(list_routers_url, admin_token)['routers']
    list_ports_url = '{}/ports'.format(neutron_endpoint)
    ports = http_get(list_ports_url, admin_token)['ports']
    router_ids = list(map(lambda x: x['id'], routers))
    for port in ports:
        device_id = port['device_id']
        if any(device_id == router_id for router_id in router_ids):
            match_ports.append(port)
    return {'routers': routers,
            'router_ports': match_ports}


def load_haproxy(cfg_file, netns = None):
    haproxyLoadCmd = 'haproxy -f {}'.format(cfg_file)
    if netns:
        haproxyLoadCmd = 'ip netns exec {} '.format(netns) + haproxyLoadCmd
    os.system(haproxyLoadCmd)


def kill_haproxy(cfg_file, pid_file):
    f = open(pid_file, 'r')
    fl = f.readlines()
    f.close()
    kill_cmd = 'kill -9 {}'.format(fl[0])
    os.system(kill_cmd)
    remove_files_cmd = 'rm -f {} {}'.format(cfg_file, pid_file)
    os.system(remove_files_cmd)
    

def get_header(pid_file):
    data = """global
    log         127.0.0.1 local2
    chroot      /var/lib/haproxy
    pidfile     {pid_file}
    maxconn     4000
    user        haproxy
    group       haproxy
    daemon
    stats socket /var/lib/haproxy/stats
""".format(pid_file=pid_file)
    return data

def get_register_data(mac, ip, sport, dport):
    data = """
frontend ssh_fe_{mac}_{ip}_{dport}
    bind *:{sport}
    mode tcp
    log global
    option tcplog
    timeout client 1m
    maxconn 3000
    default_backend ssh_{mac}_{ip}_{dport}
backend ssh_{mac}_{ip}_{dport}
    mode tcp
    option tcplog
    balance roundrobin
    option log-health-checks
    option redispatch
    log global
    timeout connect 10s
    timeout server 1m
    server {mac}_{ip}_{dport} {ip}:{dport} check
""".format(mac=mac, ip=ip, sport=sport, dport=dport)
    return data


def get_admin_token_id(keystone_endpoint, openstack_info):
    url ='{}/auth/tokens'.format(keystone_endpoint)
    data = {
        "auth": {
            "identity": {
                "methods": [
                    "password"
                    ],
                "password": {
                    "user": {
                        "id": openstack_info['admin_id'],
                        "password": openstack_info['admin_password']
                    }
                }
            },
            "scope": {
                "project": {
                    "domain": {
                        "id": "default"
                    },
                    "name": "admin"
                }
            }
        }
    }
    response = requests.post(url, json = data)
    return response.headers['X-Subject-Token']

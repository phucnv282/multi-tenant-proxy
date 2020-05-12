import os
import socket
import requests
import json

import models
import utils
from flask import Flask, request, jsonify
from sqlalchemy.orm import sessionmaker


CONFIG_FILE_DIR = "/etc/haproxy/ctrl-config"
PID_CONFIG_FILE_DIR = "/etc/haproxy/pid-ctrl-config"


with open("./config.json") as f_config:
    config = json.load(f_config)
    mysql_cfg = config["mysql"]
    openstack_info = config["openstack"]
    service_endpoints = config["service_endpoints"]
    other_cfgs = config["others"]


app = Flask(__name__)


@app.route("/register-ports", methods=["POST"])
def register_ssh():
    admin_token = utils.get_admin_token_id(service_endpoints["keystone"], openstack_info)
    session = sessionmaker(bind=models.engine)()
    content = request.get_json()
    server_id = content["server_id"]
    tcp_ports = content["tcp_ports"]
    interfaceAttachments = []
    while not interfaceAttachments:
        url ="{}/servers/{}/os-interface".format(service_endpoints["nova"], server_id)
        response = requests.get(url,headers = {"x-auth-token":admin_token,
            "content-type":"application/json"})
        interfaceAttachments = response.json()["interfaceAttachments"]
    ip_addr = interfaceAttachments[0]["fixed_ips"][0]["ip_address"]
    mac_addr = interfaceAttachments[0]["mac_addr"]
    net_id = interfaceAttachments[0]["net_id"]
    routers_and_ports = utils.get_ports_and_routers(service_endpoints["neutron"],
            admin_token)
    router_ports = routers_and_ports["router_ports"]
    routers = routers_and_ports["routers"]
    router_id = next(router_port["device_id"] for router_port in router_ports
            if net_id == router_port["network_id"])
    if router_id:
        used_ports = session.query(models.Ports)
        if not used_ports:
            used_ports = []
        else :
            used_ports = list(map(lambda Port: Port.port, used_ports))
        os.makedirs(CONFIG_FILE_DIR, exist_ok=True)
        os.makedirs(PID_CONFIG_FILE_DIR, exist_ok=True)
        config_file = "{}/{}.cfg".format(CONFIG_FILE_DIR, server_id)
        pid_file = "{}/{}.pid".format(PID_CONFIG_FILE_DIR, server_id)
        cfg_file_router_dir = "/etc/haproxy/qrouter-{}".format(router_id)
        pid_cfg_file_router_dir = "/etc/haproxy/pid-qrouter-{}".format(router_id)
        os.makedirs(cfg_file_router_dir, exist_ok=True)
        os.makedirs(pid_cfg_file_router_dir, exist_ok=True)
        router_cfg_file = "{}/{}.cfg".format(cfg_file_router_dir, server_id)
        router_pid_file = "{}/{}.pid".format(pid_cfg_file_router_dir, server_id)
        netns = "qrouter-{}".format(router_id)
        router = next(router for router in routers if router["id"] == router_id)
        external_router_ip = router["external_gateway_info"]["external_fixed_ips"][0]["ip_address"] 
        hostname = "localhost"
        remote_server_ip = socket.gethostbyname(hostname)
        is_ssh = True
        port_count = 0
        conn = models.engine.connect()
        range_ports = range(49050, 49100)
        range_ports = list(set(range_ports) - set(used_ports))
        for port in range_ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((remote_server_ip, port))
            if result != 0 and port not in used_ports:
                free_port = port
                used_ports.append(free_port)
                if is_ssh:
                    header = utils.get_header(pid_file)
                    data = header + utils.get_register_data(mac_addr, external_router_ip, free_port, free_port)
                    utils.register_port_to_file(config_file, "w", data, mac_addr, external_router_ip, free_port, free_port)
                    header = utils.get_header(router_pid_file)
                    data = header + utils.get_register_data(mac_addr, ip_addr, free_port, 22)
                    utils.register_port_to_file(router_cfg_file, "w", data, mac_addr, ip_addr, free_port, 22)
                    ins_port = models.Ports.insert().values(port=free_port, server_id=server_id, net_id=net_id, router_id=router_id, is_ssh=True)
                    conn.execute(ins_port)
                    is_ssh = False
                elif port_count < tcp_ports:
                    data = utils.get_register_data(mac_addr, external_router_ip, free_port, free_port)
                    utils.register_port_to_file(config_file, "a", data, mac_addr, external_router_ip, free_port, free_port)
                    data = utils.get_register_data(mac_addr, ip_addr, free_port, free_port)
                    utils.register_port_to_file(router_cfg_file, "a", data, mac_addr, ip_addr, free_port, free_port)
                    ins_port = models.Ports.insert().values(port=free_port, server_id=server_id, net_id=net_id, router_id=router_id, is_ssh=False)
                    conn.execute(ins_port)
                    port_count = port_count + 1
                else:
                    utils.load_haproxy(config_file)
                    utils.load_haproxy(router_cfg_file, netns)
                    sock.close()
                    break
            sock.close()
    response = {"status": "Success"}
    return jsonify(response)


@app.route("/unregister-ports", methods=["POST"])
def unregister_ssh():
    session = sessionmaker(bind=models.engine)()
    content = request.get_json()
    server_id = content["server_id"]
    addresses = content["addresses"]
    if addresses:
        network_name = list(addresses.keys())[0]
        mac = addresses[network_name][0]["OS-EXT-IPS-MAC:mac_addr"]
        ip = addresses[network_name][0]["addr"]
        mac_ip = "{}-{}".format(mac, ip)
        PortsDb = session.query(models.Ports)
        router_id = None
        for port in PortsDb:
            if server_id == port.server_id:
                router_id = port.router_id
                break
        if router_id:
            config_file = "{}/{}.cfg".format(CONFIG_FILE_DIR, server_id)
            pid_file = "{}/{}.pid".format(PID_CONFIG_FILE_DIR, server_id)
            utils.kill_haproxy(config_file, pid_file)
            cfg_file_router_dir = "/etc/haproxy/qrouter-{}".format(router_id)
            pid_cfg_file_router_dir = "/etc/haproxy/pid-qrouter-{}".format(router_id)
            router_cfg_file = "{}/{}.cfg".format(cfg_file_router_dir, server_id)
            router_pid_file = "{}/{}.pid".format(pid_cfg_file_router_dir, server_id)
            utils.kill_haproxy(router_cfg_file, router_pid_file)
            session.query(models.Ports).filter(models.Ports.c.server_id == server_id).delete(synchronize_session=False)
            session.commit()
    response = {"status": "Success"}
    return jsonify(response)


@app.route("/instance-ports", methods=["POST"])
def get_ssh_address():
    session = sessionmaker(bind=models.engine)()
    content = request.get_json()
    server_id = content["server_id"]
    used_ports = session.query(models.Ports)
    ssh_address = "N/A"
    available_ports = []
    for port in used_ports:
        if server_id == port.server_id:
            if port.is_ssh:
                ssh_address = "{}:{}".format(other_cfgs["public_ip"], port.port)
            else:
                available_ports.append("{}:{}".format(other_cfgs["public_ip"], port.port))
    if not available_ports:
        available_ports.append("N/A")
    response = {"ssh_address": ssh_address,
                "available_ports": available_ports}
    return jsonify(response)


def run_app(port):
    models.metadata.create_all()
    app.run(debug=True, host="0.0.0.0", port=port)

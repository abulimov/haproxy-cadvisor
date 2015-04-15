#!/usr/bin/env python
#
# Utility to set backend servers weight on HAProxy
# based on data from cAdvisor API.
# ===
#
# Copyright 2015 Alexander Bulimov <lazywolf0@gmail.com>
#
# Released under the MIT license, see LICENSE for details.

from __future__ import unicode_literals
from __future__ import division
from __future__ import print_function
import re
import json
import requests
import socket
import select
import math
import sys


def haproxy_execute(socket_name, command, timeout=200):
    """Executes a HAProxy command by sending a message to a HAProxy's local
    UNIX socket and waiting up to 'timeout' milliseconds for the response."""

    buffer = ""

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(socket_name)

    client.send(command + "\n")

    running = True
    while(running):
        r, w, e = select.select([client, ], [], [], timeout)

        if not (r or w or e):
            raise RuntimeError("Socket timeout")

        for s in r:
            if (s is client):
                buffer = buffer + client.recv(16384)
                running = (len(buffer) == 0)

    client.close()

    return (buffer.decode('utf-8').split('\n'))


def get_containers_data(cadvisor_url):
    """Get cAdvisor url, hostname, and return host data in JSON"""
    data = dict()
    response = requests.get(cadvisor_url + "/api/v1.2/containers/docker",
                            timeout=10)
    payload = json.loads(response.text)
    for cont in payload["subcontainers"]:
        host_raw_data = requests.get(cadvisor_url +
                                     "/api/v1.2/containers/" +
                                     cont["name"],
                                     timeout=10)
        host_data = json.loads(host_raw_data.text)
        if "aliases" in host_data:
            data[host_data["aliases"][0]] = host_data

    return data


def get_machine_data(cadvisor_url):
    """Get cAdvisor url and return parent host data in JSON"""
    response = requests.get(cadvisor_url + "/api/v1.2/machine")
    payload = json.loads(response.text)
    return payload


def cpu_usage(containers, machine):
    """Calculate cpu usage percent for list of containers stats"""
    res = dict()
    for name in containers:
        first = containers[name]["stats"][0]["cpu"]["usage"]["total"]
        last = containers[name]["stats"][-1]["cpu"]["usage"]["total"]
        cpu_usage_per_min = last - first

        cpu_num_cores = machine["num_cores"]
        cpu_usage_percent = cpu_usage_per_min / 60 / 10000000 / cpu_num_cores
        res[name] = cpu_usage_percent
    return res


def get_cadvisor_data(urls, pattern):
    """Get containers stats from list of cAdvisor urls"""
    cadvisor = dict()
    for url in urls:
        try:
            containers = get_containers_data(url)
            machine = get_machine_data(url)
            data = cpu_usage(containers, machine)
            for k in data:
                if re.match(pattern, k):
                    cadvisor[k] = (data[k])
        except (requests.exceptions.RequestException, ValueError) as e:
            print(e)
            pass
    return cadvisor


def get_haproxy_names(haproxy_sock, backend, pattern):
    """Get list of available haproxy backend servers through haproxy socket"""
    haproxy_names = []
    stat_raw = haproxy_execute(haproxy_sock, "show stat")
    for line in stat_raw:
        if not re.match("^#", line):
            splitted = line.split(",")
            if splitted[0] == backend and re.match(pattern, splitted[1]):
                haproxy_names.append(splitted[1])
    return haproxy_names


def get_haproxy_current_weights(haproxy_sock, haproxy_names, backend):
    results = dict()
    for name in haproxy_names:
        try:
            result = haproxy_execute(haproxy_sock,
                                     "get weight %s/%s" % (backend, name))
            cur_weight = int(result[0].split(" ")[0])
            results[name] = cur_weight
        except (RuntimeError, IOError) as e:
                fail("Failed to get servers weight from haproxy: %s" % e)
    return results


def fail(message):
    print(message)
    sys.exit(1)


def main(config_file):
    try:
        with open(config_file) as json_data_file:
            config = json.load(json_data_file)
        urls = config["urls"]
        pattern = config["pattern"]
        backend = config["backend"]
        haproxy_sock = config["haproxy_socket"]
    except IOError as e:
        fail("Failed to load config! %s" % e)
    except ValueError as e:
        fail("Failed to parse config! %s" % e)
    except KeyError as e:
        fail("Failed to load config! Key not found: %s" % e)

    try:
        haproxy_names = get_haproxy_names(haproxy_sock, backend, pattern)
    except (RuntimeError, IOError) as e:
        fail("Failed to get server names from haproxy: %s" % e)
    cadvisor_data = get_cadvisor_data(urls, pattern)
    desired_load = sum(cadvisor_data.values())/len(cadvisor_data)
    cur_weights = get_haproxy_current_weights(haproxy_sock,
                                              haproxy_names,
                                              backend)

    new_weights = dict()
    for name in cur_weights:
        if name in cadvisor_data:
            cur_weight = cur_weights[name]
            scale_factor = (cur_weight / cadvisor_data[name])
            desired_weight = desired_load * scale_factor
            new_weight = cur_weight + (desired_weight - cur_weight) / 2
            new_weights[name] = new_weight
            print("%s - cur: %d, des: %d, new: %d" % (name, cur_weight,
                                                      desired_weight,
                                                      new_weight))

    haproxy_scale_factor = 100 / (sum(new_weights.values()) + 1)
    for name in new_weights:
        value = math.ceil(new_weights[name] * haproxy_scale_factor)
        if value < 1:
            value = 1
        print("after scale %s - %d" % (name, value))
        try:
            haproxy_execute(haproxy_sock, "set weight %s/%s %d" % (backend,
                                                                   name,
                                                                   value))
        except (RuntimeError, IOError) as e:
                fail("Failed to set servers weight in haproxy: %s" % e)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        fail("Usage: %s path/to/config.json" % sys.argv[0])
    main(sys.argv[1])

# haproxy-cadvisor

haproxy_cadvisor.py is a small utility, created
to set backend servers weight on [HAProxy](http://www.haproxy.org/) based on
CPU utilization data from [cAdvisor](https://github.com/google/cadvisor).

This utility will adjust servers balancing weight to
make the load on all servers in given backend equal.

You can read more about it in
[my blog (in Russian)](http://bulimov.ru/it/haproxy-cadvisor/).

## Install

First, you need to install Python *requests* lib:
```shell
pip install requests
# or apt-get install python-requests on Debian/Ubuntu
```

Then clone this repo and set up initial config

```shell
git clone https://github.com/abulimov/haproxy-cadvisor
cd haproxy-cadvisor
cp config.json.example config.json
```
Then you have to edit config.json, and change
some parameters as described in **Configuration** section.

Your HAProxy must have admin socket configured,
it is done with settings like this in **haproxy.cfg**:

```
global
    stats socket /var/run/haproxy.sock level admin
```

More info about configuring HAProxy socket is in
[official documentation](http://cbonte.github.io/haproxy-dconv/configuration-1.4.html#stats).

Last step is configuring cron task - type `crontab -e` as
user that can write to HAProxy socket and
add something like this:

```crontab
* * * * * /usr/bin/python /path/to/haproxy_cadvisor.py /path/to/config.json > /dev/null
```

Don't forget to change path to haproxy_cadvisor.py and config.json to real values.

## Configuration

All configuration is done in plain JSON.
You can find example configuration in **config.json.example**.

| parameter      | type       | description |
|----------------|------------|-------------|
| haproxy_socket | **string** | socket for communication with HAProxy
| backend        | **string** | name of HAProxy backend we will control
| pattern        | **string** | regexp to match container aliases we get from cAdvisor and HAProxy server names
| urls           | **list of strings** | list of URLs we'll use to access cAdvisor API

As you can see, you'll have to change at least **urls**,
**backend** and **pattern** to match your environment.

## Usage

Set up the cron task and watch backend servers weight
adjust as the load to servers change.

## License

Licensed under the [MIT License](http://opensource.org/licenses/MIT).

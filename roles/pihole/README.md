# pihole

Runs [Pi-hole](https://pi-hole.net/) (DNS sinkhole / ad blocker) as a
Docker Compose stack. Requires the [docker-compose](../docker-compose/README.md)
role to have installed Docker Engine and the Compose plugin first.

## What it does

- Creates the compose project under `{{ pihole_dir }}` (default `/containers/pihole`)
- Renders `.env` (admin password, `0600`) and `compose.yaml`
- Brings the stack up with `docker compose` (via `community.docker.docker_compose_v2`), pulling the latest image for the configured tag

The container uses **default (bridge) networking** and publishes only the
DNS and web-admin ports via the compose `ports:` directive:

- `53/tcp` + `53/udp` — DNS
- `80/tcp` + `443/tcp` — web admin (HTTP + HTTPS)

The embedded NTP server/sync and the DHCP server are disabled — this is a
DNS resolver with the web admin only. Persistent data (config, gravity and
query databases) lives in `{{ pihole_dir }}/etc-pihole`.

## Key variables

- `pihole_password` — web admin / API password (put it in vault)
- `dns1` / `dns2` — upstream DNS servers
- `timezone` — container timezone (default `UTC`)
- `pihole_image` — image repository (default `pihole/pihole`)
- `pihole_version_tag` — image tag (default `latest`)
- `pihole_dir` — compose project directory (default `/containers/pihole`)
- `pihole_dns_listen_ip` — host IP the DNS ports (53/tcp+udp) are published on
  (default `0.0.0.0`, i.e. all interfaces)
- `pihole_web_listen_ip` — host IP the web-admin ports (80/443) are published on
  (default `0.0.0.0`, i.e. all interfaces)

Set either to a specific IP to publish that protocol on a single interface only.
Either variable may also be a **list of IPs** to publish that protocol on
several interfaces at once — each IP gets its own set of port mappings in the
generated compose file:

```yaml
pihole_dns_listen_ip:
  - "10.0.0.1"
  - "192.168.1.1"
```

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/pihole.yml`

Targets `linux_routers`; also runs as part of the
[linux_router](../linux_router/README.md) playbook.

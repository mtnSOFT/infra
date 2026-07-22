# pihole

Runs [Pi-hole](https://pi-hole.net/) (DNS sinkhole / ad blocker) as a
Docker Compose stack. Requires the [docker-compose](../docker-compose/README.md)
role to have installed Docker Engine and the Compose plugin first.

## What it does

- Creates the compose project under `{{ pihole_dir }}` (default `/containers/pihole`)
- Renders `.env` (admin password, `0600`) and `compose.yaml`
- Brings the stack up with `docker compose` (via `community.docker.docker_compose_v2`), pulling the latest image for the configured tag

The container uses **host networking** (`network_mode: host`), so FTL binds the
host's interfaces directly — DNS arrives as INPUT traffic and is governed by the
host firewall (no DNAT / published ports for UFW-managed NAT to clobber).

By default it listens on all interfaces. Set `pihole_dns_interface` to bind a
single interface only (e.g. `wg0`) — this avoids the wildcard, so Pi-hole can
share `:53` with another resolver bound to a different interface (that resolver
must also not bind `0.0.0.0:53`). Set `pihole_web_ip` to bind the web admin
(80/443) to one IP too (FTL's web server binds by IP, not interface).

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
- `pihole_dns_interface` — interface FTL binds DNS on; empty (default) = all
  interfaces, or e.g. `wg0` to bind only that one
- `pihole_web_ip` — IP the web admin (80/443) binds to; empty (default) = all
  interfaces, or e.g. `10.10.0.1`

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/pihole.yml`

Targets `linux_routers`; also runs as part of the
[linux_router](../linux_router/README.md) playbook.

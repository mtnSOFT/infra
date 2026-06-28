# pihole

Installs and pre-configures Pi-hole (DNS sinkhole / ad blocker).

## What it does

- Creates the `pihole` user/group (uid/gid 953)
- Pre-seeds `/etc/pihole/pihole.toml` from a template (upstreams, local zone forwarding)
- Runs the official Pi-hole unattended installer
- Sets the admin password, updates gravity lists, and updates Pi-hole

## Key variables

- `pihole_password` — web admin password
- `dns1` / `dns2` — upstream DNS servers
- `local_zone_name` — local zone forwarded to `127.0.0.1#5300` (see [powerdns](../powerdns/README.md))
- `pihole_version_tag` — version tag (default `latest`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/pihole.yml`

Targets `linux_routers`; also runs as part of the [linux_router](../linux_router/README.md) playbook.

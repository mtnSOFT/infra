# pihole

[Pi-hole](https://pi-hole.net/) (DNS sinkhole / ad blocker) as a Docker Compose
stack. Needs the [docker-compose](../docker-compose/README.md) role first.

## What it does

- Renders the compose project into `{{ pihole_dir }}` (default
  `/containers/pihole`) and brings it up with `community.docker.docker_compose_v2`
- Uses **host networking**, so FTL binds the host's interfaces directly — DNS is
  INPUT traffic governed by the host firewall, with no DNAT for UFW's NAT rules to
  clobber
- Listens on all interfaces unless `pihole_dns_interface` names one or more; that
  drops the wildcard bind so Pi-hole can share `:53` with another resolver on a
  different interface. `pihole_web_ip` does the same for the web admin (80/443),
  which binds by IP rather than by interface
- Serves `pihole_dns_records` as local A records — internal overrides, e.g. so
  `vpn.example.com` answers with a WireGuard address instead of the router's public
  IP (FTL's `dns.hosts`, the web admin's *Local DNS Records* page)
- Delegates each `pihole_dns_forward_zones` entry to another DNS server as a
  `server=/<zone>/<server>[#<port>]` dnsmasq line, so an internal zone resolves
  without being published to the internet
- Disables the embedded NTP and DHCP servers; data (config, gravity and query
  databases) lives in `{{ pihole_dir }}/etc-pihole`

## Gotchas

- **Ansible owns the config — the web UI cannot edit it.** Pi-hole makes every
  setting passed as an environment variable
  [read-only in the UI and CLI](https://docs.pi-hole.net/docker/configuration/).
  `dns.hosts` and `misc.dnsmasq_lines` are always emitted, so the first run
  *replaces* anything added by hand: copy existing entries out of Settings → Local
  DNS Records into `pihole_dns_records` before converging.
- **A records only.** Aliases (`dns.cnameRecords`), wildcard domains
  (`address=/example.com/…`) and reverse delegation (`dns.revServers`) are not
  wired up.
- Local records beat delegation — dnsmasq answers from `dns.hosts` before
  forwarding, so a `pihole_dns_records` entry inside a delegated zone wins.
- Sharing `:53` via `pihole_dns_interface` only works if the other resolver also
  avoids binding `0.0.0.0:53`.
- Co-locating with [powerdns](../powerdns/README.md): Pi-hole keeps `:53` and
  delegates to the authoritative server on loopback — `server: 127.0.0.1` /
  `port: 5300` matches `powerdns_auth_address` / `powerdns_auth_port`. Needs
  `powerdns_recursor_enabled: false`, or the two fight over the port.

## Key variables

- `pihole_password` — web admin / API password (vault; no default)
- `pihole_dir` — compose project directory (default `/containers/pihole`)
- `pihole_deploy` — bring the stack up (default `true`; the molecule scenario sets
  it `false` to render config only)
- `pihole_dns_records` — local A records, a list of `{name, ip}` (default `[]`)
- `pihole_dns_forward_zones` — zones delegated to another DNS server, a list of
  `{zone, server}` with an optional `port` (default `[]`)
- `pihole_dns_interface` — interface(s) FTL binds DNS on, one (`wg0`) or a list
  (`["eth1", "wg0"]`); empty (default) = all interfaces
- `pihole_web_ip` — host IP the web admin binds to (default empty = all interfaces)
- `pihole_image` / `pihole_version_tag` — image and tag (default
  `pihole/pihole:latest`; pin these in inventory)
- `dns1` / `dns2` — upstream resolvers
- `timezone` — container timezone (default `UTC`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/pihole.yml`

Targets `linux_routers`; also runs as part of the
[linux_router](../linux_router/README.md) playbook. Configure it in
`group_vars/linux_routers/`:

```yaml
# vars.yml
pihole_password: "{{ vault_pihole_password }}"

pihole_dns_records:
  - name: vpn.example.com
    ip: 10.10.0.1

pihole_dns_forward_zones:
  - zone: example.internal
    server: 127.0.0.1
    port: 5300 # optional, defaults to 53

# vault.yml (ansible-vault)
vault_pihole_password: "..."
```

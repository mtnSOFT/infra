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

By default it listens on all interfaces. Set `pihole_dns_interface` to bind
specific interfaces only — a single one (e.g. `wg0`) or a list (e.g.
`["eth1", "wg0"]`). This avoids the wildcard, so Pi-hole can share `:53` with
another resolver bound to a different interface (that resolver must also not
bind `0.0.0.0:53`). Use a list to answer on a LAN interface *and* WireGuard
clients on `wg0` at the same time. Set `pihole_web_ip` to bind the web admin
(80/443) to one IP too (FTL's web server binds by IP, not interface).

The embedded NTP server/sync and the DHCP server are disabled — this is a
DNS resolver with the web admin only. Persistent data (config, gravity and
query databases) lives in `{{ pihole_dir }}/etc-pihole`.

## Local DNS records

`pihole_dns_records` defines internal overrides — names answered from this list
instead of from the upstreams. The usual case is a service whose public DNS points
at the router's WAN address: without an override, a client already inside the LAN or
the VPN resolves the public IP and hairpins out and back instead of going straight
to the internal address.

```yaml
pihole_dns_records:
  - name: vpn.example.com
    ip: 10.10.0.1
  - name: nas.example.com
    ip: 10.10.0.20
```

These land in FTL's `dns.hosts` — the same store the web admin's
**Settings → Local DNS Records** page uses — via `FTLCONF_dns_hosts`. Pi-hole makes
any setting supplied through the environment [read-only in the web UI and
CLI](https://docs.pi-hole.net/docker/configuration/), so the entries show up there
greyed out: this list is the single source of truth, and hand edits can't drift
from it. The same already applies to the upstreams and the listening mode.

Only A records (name → IP) are handled. Aliases (`dns.cnameRecords`) and wildcard
domain overrides (`address=/example.com/10.0.0.1`) are not wired up.

> ⚠️ **Before the first run on an existing Pi-hole:** `FTLCONF_dns_hosts` is always
> emitted, so an empty `pihole_dns_records` *clears* the Local DNS Records page.
> If records were ever added by hand there, copy them into `pihole_dns_records`
> first.

## Delegated zones

`pihole_dns_forward_zones` hands a whole zone to another DNS server: queries for
names in it are forwarded there rather than to `dns1`/`dns2`, so an internal zone
resolves without ever being published to the internet.

```yaml
pihole_dns_forward_zones:
  - zone: example.internal
    server: 127.0.0.1
    port: 5300        # optional, defaults to 53
  - zone: lab.example.com
    server: 10.10.0.3
```

Each entry renders one `server=/<zone>/<server>[#<port>]` dnsmasq directive into
`misc.dnsmasq_lines`. That setting is shared with the interface binding
`pihole_dns_interface` produces — both end up in the same list.

The `127.0.0.1:5300` above is not arbitrary: it matches `powerdns_auth_address` /
`powerdns_auth_port` in the [powerdns](../powerdns/README.md) role, whose
authoritative server sits on loopback. That is the co-location pattern — Pi-hole
owns `:53` and delegates its zone to PowerDNS behind it, instead of the two
fighting over the port (which is why `powerdns_recursor_enabled` must be `false`
on such a host).

Delegation and local records compose in the useful direction: dnsmasq consults
`dns.hosts` *before* forwarding, so a `pihole_dns_records` entry for a name inside
a delegated zone wins over whatever the delegated server would answer.

Reverse (`PTR`) delegation is not wired up — that is Pi-hole's separate
`dns.revServers` setting, which couples a domain to a client subnet.

> ⚠️ `misc.dnsmasq_lines` is now emitted on every run too (it previously appeared
> only when `pihole_dns_interface` was set), so it is subject to the same caveat as
> the records above: anything added to it by hand is replaced by what this role
> renders.

## Key variables

- `pihole_password` — web admin / API password (put it in vault)
- `dns1` / `dns2` — upstream DNS servers
- `timezone` — container timezone (default `UTC`)
- `pihole_image` — image repository (default `pihole/pihole`)
- `pihole_version_tag` — image tag (default `latest`)
- `pihole_dir` — compose project directory (default `/containers/pihole`)
- `pihole_dns_records` — local DNS overrides, a list of `{name, ip}` (default `[]`);
  see [Local DNS records](#local-dns-records)
- `pihole_dns_forward_zones` — zones delegated to another DNS server, a list of
  `{zone, server}` with an optional `port` (default `[]`); see
  [Delegated zones](#delegated-zones)
- `pihole_deploy` — bring the stack up with `docker compose` (default `true`); set
  `false` to render the config only
- `pihole_dns_interface` — interface(s) FTL binds DNS on; empty (default) = all
  interfaces, e.g. `wg0` to bind only that one, or a list like `["eth1", "wg0"]`
  to answer on several (e.g. a LAN interface *and* WireGuard clients)
- `pihole_web_ip` — IP the web admin (80/443) binds to; empty (default) = all
  interfaces, or e.g. `10.10.0.1`

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/pihole.yml`

Targets `linux_routers`; also runs as part of the
[linux_router](../linux_router/README.md) playbook.

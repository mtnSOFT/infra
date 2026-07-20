# powerdns

Installs a full DNS server: an authoritative PowerDNS server for a local zone
**plus** a PowerDNS Recursor that resolves everything else.

## What it does

- Includes the `PowerDNS.pdns` galaxy role to install the authoritative server,
  bound to loopback (`127.0.0.1:5300`) behind the recursor
- Auto-builds `A` records from inventory hosts (`ansible_host`) plus any manual records
- Creates/loads the zone with `pdnsutil` and bumps the serial on change
- Includes the `PowerDNS.pdns_recursor` galaxy role to install the Recursor as the
  client-facing resolver on port `53`:
  - the local zone (`pdns_zone_name`) is forwarded to the authoritative server
  - every other query is forwarded to the upstream resolvers (`dns1`/`dns2`)

Query flow: `client → recursor :53` → (`pdns_zone_name` → auth `127.0.0.1:5300`)
/ (`.` → upstreams).

## Key variables

Authoritative server / zone:

- `pdns_zone_name` — DNS zone to manage
- `pdns_records_manual` — extra records (A/AAAA/CNAME/MX/TXT)
- `pdns_auto_inventory_records` — auto-create A records from inventory (default `true`)
- `pdns_primary_ns` — primary nameserver (default `ns1.<zone>`)
- `pdns_config.local-address` / `local-port` — auth bind (keep on loopback, `5300`)

Recursor / resolver:

- `powerdns_recursor_enabled` — install the recursor (default `true`)
- `powerdns_listen_interfaces` — interface names the recursor listens on; each is
  resolved to its primary IPv4 address (e.g. `[eth0, eth1]`). Takes precedence
  over `powerdns_listen_addresses`
- `powerdns_listen_addresses` — explicit listen IPs, used verbatim
- `powerdns_listen_default` — fallback when neither is set (default `0.0.0.0`)
- `powerdns_recursor_port` — client-facing port (default `53`)
- `powerdns_recursor_upstreams` — upstream resolvers for external queries
  (default `dns1`/`dns2`)
- `powerdns_recursor_allow_from` — networks allowed to query (default loopback +
  RFC1918 + ULA/link-local; prevents an open resolver)
- `powerdns_recursor_dnssec` — DNSSEC validation mode (default `process`)
- `powerdns_auth_address` / `powerdns_auth_port` — where the recursor forwards the
  local zone; must match `pdns_config.local-address` / `local-port`

## Requirements

The `PowerDNS.pdns` and `PowerDNS.pdns_recursor` roles from `requirements.yml`:
`ansible-galaxy role install -r requirements.yml -p ./.galaxy/roles`

The recursor is installed from PowerDNS's official apt repository
(`powerdns_recursor_install_repo`, default `rec-54`) because the stock Ubuntu
package (recursor 4.9.x) predates the YAML settings this role uses; recursor
`>= 5.x` is required.

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/powerdns.yml`

Targets the `powerdns` inventory group.

> This role assumes the recursor owns port `53` on the host (standalone DNS
> server). Co-locating it with [pihole](../pihole/README.md), which also binds
> `:53`, is out of scope — run them on separate hosts, or set
> `powerdns_recursor_enabled: false` to keep only the authoritative server.

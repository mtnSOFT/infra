# opnsense_dns

Manages the DNS resolver built into [OPNsense](https://opnsense.org/),
**Unbound**. It answers for the local zone and forwards everything else to the
upstream resolvers. Like [opnsense_router](../opnsense_router/README.md), it
uses the [oxlorg.opnsense](https://ansible-opnsense.oxl.app/) collection to
call the OPNsense REST API **from the controller**. This role replaces
[powerdns](../powerdns/README.md).

## What it does

1. **validate**: checks the API credentials, then builds and checks the
   record lists. It always runs, because the later steps use its lists.
2. **general**: Unbound's general settings (enable, interfaces, port, DNSSEC,
   DHCP registration). Only when `opnsense_dns_general` is set.
3. **hosts**: host overrides. These are an A record for every inventory host
   plus `opnsense_dns_hosts`, followed by the aliases in `opnsense_dns_aliases`.
4. **forwards**: a global forward to `opnsense_dns_upstreams`, plus per-domain
   forwards
5. **acls**: access lists for networks that aren't directly attached

Every step stages its changes. Unbound is reloaded once at the end, only if
something changed.

Query flow: `client → Unbound :53` → (host override or alias in the zone →
answered locally) / (anything else → upstreams).

## Gotchas

- **A, AAAA and MX only.** Unbound host overrides support no other record
  types. A CNAME becomes an alias, and its `target` must be an A/AAAA override,
  either from the inventory or from `opnsense_dns_hosts`. The validation fails
  on TXT, SRV or anything else, and on an alias whose target doesn't exist.
  CNAMEs that point outside the zone aren't possible.
- **No TTL.** Overrides have no per-record TTL, so the pdns `ttl` is dropped.
- **No purge.** Unbound has no `*_multi` modules. Removing an entry from a
  list leaves it on the firewall. Set `state: absent` on the entry, run the
  playbook, then delete the entry. The same applies to upstreams and forwards.
- **`description` is the identity** of host overrides and aliases. It
  defaults to `<hostname>.<domain> <type>` or `<alias>.<domain> alias`.
  Renaming an entry or changing its type creates a new one.
- **Inventory hosts need an IP.** A host whose `ansible_host` is a name gets
  no A record. Any alias that points at that host fails validation.
- **Other interfaces need a firewall rule.** Only LAN's default rule allows
  DNS to the firewall. For VLANs or VPN networks, add an
  `opnsense_router_rules` entry for TCP/UDP 53 to the firewall, plus an
  `opnsense_dns_acls` entry.

## Key variables

The API connection (`opnsense_dns_api_*`, `opnsense_dns_ssl_verify`) defaults
to the `opnsense_router_*` variables: same firewall, same API user. The API user
needs privileges for _Services: Unbound DNS_. Like opnsense_router, the role
trusts the CA in `<inventory>/host_vars/<host>/opnsense_ca.pem` if that file
exists.

- `opnsense_dns_general`: `unbound_general` parameters (default `{}`, left
  alone)
- `opnsense_dns_domain`: the local zone. Entries without their own `domain` use
  it.
- `opnsense_dns_auto_inventory_records`: an A record for every inventory host
  with an IPv4 `ansible_host` (default `true`)
- `opnsense_dns_hosts`: `unbound_host` entries (`hostname`, `value`,
  `record_type` (default `A`), `prio`, `domain`, `description`, `state`). An
  entry with the same description as an inventory record replaces it.
- `opnsense_dns_aliases`: `unbound_host_alias` entries (`alias`, `target`,
  `domain`, `description`, `state`)
- `opnsense_dns_upstreams`: global forwarders (default `dns1`/`dns2`; `[]`
  means Unbound resolves the names itself)
- `opnsense_dns_forwards`: per-domain `unbound_forward` entries (`domain`,
  `target`, `port`)
- `opnsense_dns_acls`: `unbound_acl` entries (`name`, `action`, `networks`)
- `opnsense_dns_reload_timeout`: API timeout for the final reload (default
  `60`)

## Usage

```sh
ansible-playbook -i inventories/production/hosts playbooks/opnsense_dns.yml --check --diff
ansible-playbook -i inventories/production/hosts playbooks/opnsense_dns.yml
dig @<opnsense-lan-ip> pihole.int.example.net
```

The playbook targets `opnsense_routers`, the same group and vault credentials
as opnsense_router. Configure it in `group_vars/opnsense_routers/`:

```yaml
opnsense_dns_general:
  enabled: true
  interfaces: [lan]
  local_zone_type: transparent

opnsense_dns_domain: int.example.net

# node42, node1, … get A records from the inventory automatically
opnsense_dns_aliases:
  - alias: pihole
    target: node42.int.example.net
  - alias: code
    target: node1.int.example.net
```

### Migrating from powerdns

| powerdns                          | opnsense_dns                                                                            |
|-----------------------------------|-----------------------------------------------------------------------------------------|
| `pdns_zone_name`                  | `opnsense_dns_domain`                                                                   |
| `pdns_auto_inventory_records`     | `opnsense_dns_auto_inventory_records`                                                   |
| `pdns_records_manual` (A/AAAA/MX) | `opnsense_dns_hosts` (`name` → `hostname`, `content` → `value`, `type` → `record_type`) |
| `pdns_records_manual` (CNAME)     | `opnsense_dns_aliases` (`name` → `alias`, `content` → `target`)                         |
| `pdns_records_manual` (TXT)       | not supported                                                                           |
| `powerdns_recursor_upstreams`     | `opnsense_dns_upstreams`                                                                |
| `powerdns_listen_interfaces`      | `opnsense_dns_general.interfaces`                                                       |
| `powerdns_recursor_port`          | `opnsense_dns_general.port`                                                             |
| `powerdns_recursor_dnssec`        | `opnsense_dns_general.dnssec`                                                           |
| `powerdns_recursor_allow_from`    | `opnsense_dns_acls` (attached networks are allowed already)                             |

# powerdns

Installs an authoritative PowerDNS server and manages a DNS zone.

## What it does

- Includes the `PowerDNS.pdns` galaxy role to install PowerDNS (listens on `127.0.0.1:5300`)
- Auto-builds `A` records from inventory hosts (`ansible_host`) plus any manual records
- Creates/loads the zone with `pdnsutil` and bumps the serial on change

Pairs with [pihole](../pihole/README.md), which forwards the local zone to `127.0.0.1#5300`.

## Key variables

- `pdns_zone_name` — DNS zone to manage
- `pdns_records_manual` — extra records (A/AAAA/CNAME/MX/TXT)
- `pdns_auto_inventory_records` — auto-create A records from inventory (default `true`)
- `pdns_primary_ns` — primary nameserver (default `ns1.<zone>`)
- `pdns_port` — listen port (default `5300`)

## Requirements

The `PowerDNS.pdns` role from `requirements.yml`:
`ansible-galaxy role install -r requirements.yml -p ./.galaxy/roles`

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/powerdns.yml`

Targets the `powerdns` inventory group.

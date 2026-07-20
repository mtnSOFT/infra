# ufw

Configures the UFW firewall: default policies, rules and (optional) NAT masquerading.

## What it does

- Stops/disables the standalone `nftables` service (UFW manages the ruleset)
- Optionally disables IPv6 in `/etc/default/ufw`
- Resets UFW and sets default policies (in: deny, out: allow, routed: deny)
- Applies default, group and host rules, then enables UFW
- Renders NAT masquerade rules into a single `*nat` block in `before.rules`
  (server LAN NAT and/or WireGuard NAT), setting `DEFAULT_FORWARD_POLICY=ACCEPT`

## Key variables

- `ufw_enabled` / `ufw_reset` — enable UFW / reset before applying (default `true`)
- `ufw_default_policy_incoming|outgoing|routed` — default policies
- `ufw_logging_level` — `on|off|low|medium|high|full` (default `low`)
- `ufw_default_rules` / `ufw_group_rules` / `ufw_host_rules` — rule lists (see below)
- `ufw_applications` — UFW app profiles to allow
- `server_lan_cidr` / `lan_cidr` — network CIDRs used in rules
- `server_lan_nat` — masquerade `server_lan_cidr` out `lan_interface` (default `false`)
- `lan_interface` — upstream LAN-facing interface used as the NAT egress (default `eth0`)
- `ufw_nat_rules` — extra masquerade rules (`{ source, out_interface }`), same `*nat` block
- `wireguard_subnet` / `wireguard_external_interface` — add WireGuard NAT masquerading

## Defining rules

Defaults live in `roles/ufw/defaults/main.yml`. Override per scope in your inventory:

**Group rules** — e.g. `inventories/production/group_vars/linux_routers/vars.yml`:

```yaml
ufw_group_rules:
  - rule: allow
    port: "443"
    proto: tcp
    interface: "lanbr0"
    direction: in
    from_ip: "{{ server_lan_cidr }}"
    comment: "HTTPS server LAN"
```

**Host rules** — e.g. `inventories/production/host_vars/myhost/vars.yml`:

```yaml
ufw_host_rules:
  - rule: allow
    port: "80"
    proto: tcp
    interface: "eth1"
    direction: in
    from_ip: "192.168.42.2"
    comment: "HTTP server LAN"
```

**Default rules for all hosts** — e.g. `inventories/production/group_vars/all/vars.yml`
(overrides this role's defaults):

```yaml
ufw_default_rules:
  - rule: allow
    port: "42"
    proto: tcp
    comment: "Special service access"
```

## NAT masquerading

The role renders all masquerade rules into one `*nat` block in `before.rules`
(iptables-restore allows only a single `*nat` table) and sets
`DEFAULT_FORWARD_POLICY="ACCEPT"`. Forwarding itself is enabled by the
[linux_router](../linux_router/README.md) role (`net.ipv4.ip_forward=1`).

**Server LAN NAT** — make a router (e.g. the `stargate` gateway) NAT the server
LAN out to the upstream LAN / Internet
(`server LAN -> router -> LAN -> upstream router -> Internet`). Set on the router,
e.g. `inventories/production/group_vars/linux_routers/vars.yml`:

```yaml
server_lan_nat: true
server_lan_cidr: "10.0.0.0/24"  # source subnet to masquerade
lan_interface: "eth0"           # upstream LAN-facing (egress) interface
```

**Arbitrary rules** — for anything beyond the above:

```yaml
ufw_nat_rules:
  - source: "10.20.0.0/24"
    out_interface: "eth0"
```

WireGuard NAT is added automatically when `wireguard_subnet` is set, into the
same block.

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/ufw.yml`

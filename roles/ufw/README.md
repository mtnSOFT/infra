# ufw

Configures the UFW firewall: default policies, rules and (optional) WireGuard NAT.

## What it does

- Stops/disables the standalone `nftables` service (UFW manages the ruleset)
- Optionally disables IPv6 in `/etc/default/ufw`
- Resets UFW and sets default policies (in: deny, out: allow, routed: deny)
- Applies default, group and host rules, then enables UFW
- Adds WireGuard NAT masquerade rules to `before.rules` when `wireguard_subnet` is set

## Key variables

- `ufw_enabled` / `ufw_reset` — enable UFW / reset before applying (default `true`)
- `ufw_default_policy_incoming|outgoing|routed` — default policies
- `ufw_logging_level` — `on|off|low|medium|high|full` (default `low`)
- `ufw_default_rules` / `ufw_group_rules` / `ufw_host_rules` — rule lists (see below)
- `ufw_applications` — UFW app profiles to allow
- `secure_lan_cidr` / `guest_lan_cidr` — network CIDRs used in rules
- `wireguard_subnet` / `wireguard_external_interface` — enable + scope NAT masquerading

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
    from_ip: "{{ secure_lan_cidr }}"
    comment: "HTTPS secure LAN"
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
    comment: "HTTP secure LAN"
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

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/ufw.yml`

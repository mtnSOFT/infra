# opnsense_router

Configures an [OPNsense](https://opnsense.org/) firewall as the network's router:
gateways and static routes, aliases, outbound NAT and filter rules.
It uses the [oxlorg.opnsense](https://ansible-opnsense.oxl.app/) collection, which
talks to the OPNsense REST API **from the controller**. Nothing runs on the
firewall over SSH.

## What it does

1. **validate**: asserts that the API credentials are set and that every NAT and
   filter rule has a unique `description`
2. **routing**: gateways, then the static routes that use them
3. **aliases**: firewall aliases (named networks, hosts and ports) for rules to
   reference
4. **nat**: extra outbound (source) NAT rules
5. **rules**: filter rules, in Firewall › Automation › Filter

NAT and filter changes are staged without applying them, then applied through
an OPNsense **savepoint**. Applying starts a 60s timer that reverts to the
savepoint. Only a follow-up API call that gets through the _new_ ruleset cancels
that timer. If a rule cuts the controller off, the firewall rolls back by itself.

## Bootstrap (manual, once)

The API can't do these steps:

1. Install OPNsense from the ISO. On the console, assign the WAN and LAN NICs
   (_Assign interfaces_) and set the LAN IP. Interface assignment isn't
   available through the API.
2. In the web UI: System › Access › Users, create a user `ansible` and add an
   API key to it. Grant it privileges for the pages this role manages, or
   admin. Put the downloaded key and secret into the vault.
3. Make the web certificate verifiable: install one whose CN/SAN matches
   `opnsense_router_api_host`, or save the CA that signed it (PEM) as
   `<inventory>/host_vars/<host>/opnsense_ca.pem`. That path is fixed, and the
   role uses the file whenever it exists. Certificates are placed on hosts out
   of band, like for the other hosts. Use `opnsense_router_ssl_verify: false`
   only for the first run.
4. Keep the default _anti-lockout_ rule on LAN. It's the safety net while
   managed rules are applied.

## Gotchas

- **The collection is pinned to the OPNsense version.** `oxlorg.opnsense` 26.1.x
  supports OPNsense 26.1. Move the range in `requirements.yml` with every major
  firewall upgrade.
- **Automation rules, not GUI rules.** The rules land in Firewall › Automation ›
  Filter, which is evaluated _before_ the per-interface rules in the GUI. Rules
  added by hand in the GUI stay untouched, even with `opnsense_router_purge`.
- **`description` is a rule's identity.** NAT and filter rules are matched on
  it. Renaming one creates a new rule and leaves the old one behind, unless
  `opnsense_router_purge` is on.
- **No port forwards (DNAT) yet.** The collection has no destination-NAT module.
  Add port forwards by hand in the GUI for now.
- **The controller needs `httpx`.** The playbook runs the modules with the same
  Python that runs ansible (`ansible_playbook_python`), so `pip install httpx`
  there (the mtn-shell venv).

## Key variables

Entries use the collection module's own parameter names. See the commented
examples in `defaults/main.yml`.

- `opnsense_router_api_key` / `opnsense_router_api_secret`: API credentials
  (vault, no default)
- `opnsense_router_api_host` / `opnsense_router_api_port`: API endpoint (default
  `ansible_host` or the inventory name / `443`)
- `opnsense_router_ssl_verify`: certificate validation (default `true`). The
  CA is read from `host_vars/<host>/opnsense_ca.pem` if present; it isn't a
  variable.
- `opnsense_router_gateways`, `opnsense_router_routes`: `gateway` / `route`
  entries
- `opnsense_router_aliases`: `alias_multi` entries
- `opnsense_router_nat_source`: `nat_source` entries
- `opnsense_router_rules`: `rule_multi` entries
- `opnsense_router_purge`: delete automation rules and aliases that aren't
  listed (default `false`; run `--check --diff` first)

## Usage

```sh
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/production/hosts playbooks/opnsense_router.yml --check --diff
ansible-playbook -i inventories/production/hosts playbooks/opnsense_router.yml
```

Targets `opnsense_routers`. Configure it in `group_vars/opnsense_routers/`:

```yaml
# hosts
[opnsense_routers]
opnsense ansible_host=10.0.0.1

# vars.yml
opnsense_router_api_key: "{{ vault_opnsense_router_api_key }}"
opnsense_router_api_secret: "{{ vault_opnsense_router_api_secret }}"

opnsense_router_aliases:
  - name: int
    type: network
    content: [10.0.0.0/24]

opnsense_router_rules:
  - description: int to anywhere
    interface: [lan]
    source_net: int

# vault.yml (ansible-vault)
vault_opnsense_router_api_key: "..."
vault_opnsense_router_api_secret: "..."
```

### Migrating from linux_router / ufw

| linux_router / ufw                             | opnsense_router                                                                 |
| ---------------------------------------------- | ------------------------------------------------------------------------------- |
| `ufw_default_policy_incoming: deny`            | built-in default deny on WAN                                                    |
| `ufw_default_policy_routed: deny` + NAT allows | rule `interface: [lan]`, `source_net: <alias>`                                  |
| `server_lan_nat: true`                         | automatic outbound NAT (nothing to configure)                                   |
| `ufw_nat_rules`                                | `opnsense_router_nat_source` + outbound NAT in _hybrid_ mode                    |
| `ufw_group_rules` / `ufw_host_rules`           | `opnsense_router_rules` (`from_ip` → `source_net`, `port` → `destination_port`) |
| netplan routes                                 | `opnsense_router_gateways` + `opnsense_router_routes`                           |
| `net.ipv4.ip_forward`                          | inherent                                                                        |

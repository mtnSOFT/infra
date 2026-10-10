# opnsense_wireguard

Runs the WireGuard VPN on [OPNsense](https://opnsense.org/) instead of on a
Linux host. Like [opnsense_router](../opnsense_router/README.md), it uses the
[oxlorg.opnsense](https://ansible-opnsense.oxl.app/) collection to call the
OPNsense REST API **from the controller**. This role replaces
[wireguard](../wireguard/README.md) and the WireGuard NAT in
[ufw](../ufw/README.md).

## What it does

1. **validate**: checks the API credentials, the instance key pair, the tunnel
   address, and that `wg` is installed on the controller
2. **clients**: [wireguard_clients](../wireguard_clients/README.md) reads each
   client's keys back from its vaulted config, or creates a new client, and
   renders the client configs. These are the same files the Linux role wrote.
3. **peers**: one WireGuard peer per client (public key, PSK, tunnel IP)
4. **server**: the instance (`opnsense_wireguard_name`) with its key pair,
   listen port and tunnel address, with every peer linked to it. Then it
   enables the WireGuard service.

Every step stages its changes. WireGuard is reloaded once at the end, only if
something changed.

## Gotchas

- **Keep the server key pair.** Clients pin the server's public key. Copying
  stargate's key pair into the vault (see below) keeps every existing client
  config valid. A new key pair means distributing new configs to every client.
- **The controller needs `wireguard-tools`.** Client keys are generated and
  derived with `wg` on the controller.
- **Firewall, NAT and DNS are data in the other roles.** This role only creates
  the VPN. Without the entries below, the handshake works but no traffic flows.
- **No peer purge.** Removing a client from `wireguard_client_peers` unlinks it
  from the instance, but the peer itself stays in VPN › WireGuard › Peers.
  Delete it there.
- **`--tags peers` / `--tags server` also run the clients step.** They need its
  peer list. With a missing entry the server would unlink that client, so the
  clients step fails instead of returning a short list.

## Key variables

The API connection (`opnsense_wireguard_api_*`, `opnsense_wireguard_ssl_verify`)
defaults to the `opnsense_router_*` variables: same firewall, same API user. The
API user needs privileges for _VPN: WireGuard_. Like opnsense_router, the role
trusts the CA in `<inventory>/host_vars/<host>/opnsense_ca.pem` if that file
exists.

- `opnsense_wireguard_private_key` / `opnsense_wireguard_public_key`: the
  instance key pair (vault, no default)
- `opnsense_wireguard_name`: instance name (default `wg0`)
- `opnsense_wireguard_reload_timeout`: API timeout for the final reload
  (default `60`)
- These `wireguard_*` variables are shared with the Linux role:
  - `wireguard_internal_server_ip`: tunnel address with prefix (e.g.
    `10.10.0.1/24`, required)
  - `wireguard_port`: listen port (default `51820`)
  - `wireguard_mtu`: MTU (default empty, which means OPNsense's 1420)
  - `wireguard_client_peers`
  - plus the client-config variables of
    [wireguard_clients](../wireguard_clients/README.md)

## Usage

```sh
ansible-playbook -i inventories/production/hosts playbooks/opnsense_wireguard.yml --check --diff
ansible-playbook -i inventories/production/hosts playbooks/opnsense_wireguard.yml
```

The playbook targets `opnsense_routers`. Configure it in
`group_vars/opnsense_routers/`. The `wireguard_*` values are the same as in
the `wireguard` group:

```yaml
# vars.yml
opnsense_wireguard_private_key: "{{ vault_opnsense_wireguard_private_key }}"
opnsense_wireguard_public_key: "{{ vault_opnsense_wireguard_public_key }}"

wireguard_subnet: 10.10.0.0/24
wireguard_internal_server_ip: 10.10.0.1/24
wireguard_port: 51820
wireguard_endpoint: vpn.example.com
wireguard_allowed_lan_ips: "10.10.0.1/32, 10.0.0.0/24"
wireguard_dns_servers: [10.10.0.1] # Unbound on the tunnel address
wireguard_client_peers:
  - name: alice
    ip: 10.10.0.2/32

# What the other OPNsense roles need for the VPN
opnsense_router_rules:
  - description: WireGuard from internet
    interface: [wan]
    protocol: UDP
    destination_port: "{{ wireguard_port }}"
  - description: WireGuard clients to anywhere
    interface: [wireguard] # the WireGuard interface group; check its name on the box
    source_net: "{{ wireguard_subnet }}"

opnsense_router_nat_source: # needs outbound NAT in hybrid mode
  - description: WireGuard clients to internet
    interface: wan
    source_net: "{{ wireguard_subnet }}"
    target: wanip

opnsense_dns_acls:
  - name: wireguard
    action: allow
    networks: ["{{ wireguard_subnet }}"]

# vault.yml (ansible-vault)
vault_opnsense_wireguard_private_key: "..."
vault_opnsense_wireguard_public_key: "..."
```

Unbound has to listen on the tunnel too. Leave `opnsense_dns_general.interfaces`
unset (all interfaces), or include the WireGuard interface in it.

### Moving from the Linux wireguard role

1. On stargate, run `sudo wg show wg0 private-key` and
   `sudo wg show wg0 public-key`, and put both into the vault as above.
2. Copy the `wireguard_*` values from `group_vars/wireguard` into
   `group_vars/opnsense_routers`, and add the firewall, NAT and ACL entries.
3. Run `opnsense_router` and `opnsense_dns`, then run `opnsense_wireguard` with
   `--check --diff` and for real. The `.vaulted` client configs must not
   change. If they do, a `wireguard_*` value differs from the Linux setup.
4. Point the upstream UDP port forward for `wireguard_port` at the OPNsense
   WAN. Stop the old server with `sudo systemctl disable --now wg-quick@wg0` on
   stargate.
5. Test one client: the handshake in VPN › WireGuard › Status, LAN access, and
   DNS. Then remove stargate from the `wireguard` group.

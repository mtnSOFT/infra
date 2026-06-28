# wireguard

Installs and configures a WireGuard VPN server and generates client configs.

## What it does

- Installs WireGuard on the server
- Generates the server interface config (keys are reused if they already exist)
- Generates per-client configs (`all` = full tunnel, `lan` = split tunnel)
- Stores client + server configs encrypted with ansible-vault in the local inventory
- NAT/forwarding for WireGuard is handled by the [ufw](../ufw/README.md) role

## Key variables

- `wireguard_client_peers` — list of clients (`name`, `ip`)
- `wireguard_port` — listen port (default `51820`)
- `wireguard_dns_servers` — DNS pushed to clients (default `[10.10.0.1]`)
- `wireguard_company` — prefix for config filenames (default `acme`)
- `wireguard_interface` / `wireguard_endpoint` — interface name and public endpoint

## Client config

Configure clients in inventory `group_vars/wireguard`:

```yaml
wireguard_client_peers:
  - name: "alice"
    ip: "10.10.0.2/32"
```

Configs are stored encrypted in `inventories/production/wireguard_configs/clients`.

Show a client QR code:

`ansible-vault view vpn-acme-all.conf.vault | qrencode -t ansiutf8`

Or import into NetworkManager after decrypting:

`nmcli connection import type wireguard file vpn-acme-all.conf`

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/wireguard.yml`

Targets the `wireguard` inventory group.

# wireguard_clients

Generates WireGuard client configs and returns the peer list a server needs.
It is shared by [wireguard](../wireguard/README.md) (wg-quick on Linux) and
[opnsense_wireguard](../opnsense_wireguard/README.md) (OPNsense), so both read
and write the same client configs. It isn't run on its own: the server role
imports it.

## What it does

- For every `wireguard_client_peers` entry, it reads the client's private key
  and PSK back from its vaulted config. If there is no config yet, it generates
  both (`wg genkey` / `wg genpsk`). Existing clients keep their keys.
- Renders two configs per client into
  `<inventory>/wireguard_configs/clients/<name>/`: `all` routes everything
  through the tunnel, `lan` routes only `wireguard_allowed_lan_ips`. It
  re-encrypts them with ansible-vault only when the content changed, and
  shreds the plaintext.
- Returns `wireguard_clients_peers`, a list of
  `{name, ip, public_key, preshared_key}`, which the calling role turns into
  server-side peers.

## Gotchas

- **The `wg` commands run on the play's target host.** For the Linux server
  that's the server, as before. For OPNsense, the play is `connection: local`,
  so the controller needs `wireguard-tools`.
- The vault steps run `ansible-vault` on the controller as `$USER`, using the
  play's vault password.
- **The output contains private keys.** Callers that log results should import
  the role with `no_log: true`.

## Key variables

These have the same names as the wireguard role, so one set of inventory
variables drives both the server and its clients.

- `wireguard_client_peers`: clients (`name`, `ip`)
- `wireguard_endpoint`: public name or IP the clients connect to (required)
- `wireguard_port`: listen port (default `51820`)
- `wireguard_allowed_lan_ips`: routes in the `lan` config (required)
- `wireguard_dns_servers`: DNS pushed to clients (default `[10.10.0.1]`)
- `wireguard_mtu`: optional MTU
- `wireguard_company`: filename prefix (default `acme`)
- `local_wireguard_config_dir`: where configs are stored (default
  `<inventory>/wireguard_configs`)
- `wireguard_server_public_key`: set by the calling role, not in inventory

## Usage

```yaml
- name: Hand the server public key to wireguard_clients
  ansible.builtin.set_fact:
    wireguard_server_public_key: "{{ my_server_public_key }}"

- name: Create client configs
  ansible.builtin.import_role:
    name: wireguard_clients
  no_log: true
# wireguard_clients_peers is now set
```

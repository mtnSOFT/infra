# vaultwarden

[Vaultwarden](https://github.com/dani-garcia/vaultwarden) (Bitwarden-compatible
password manager) as a Docker Compose stack. Needs the
[docker-compose](../docker-compose/README.md) role first.

## What it does

- Renders the compose project into `{{ vaultwarden_dir }}` (default
  `/containers/vaultwarden`) and brings it up with `community.docker.docker_compose_v2`
- Runs **one container on SQLite** — no `DATABASE_URL` is set, so Vaultwarden
  keeps its database, attachments and token signing keys in
  `{{ vaultwarden_dir }}/data`
- **Terminates TLS itself** (`ROCKET_TLS`) from the certificate and key you
  supply, so there is no reverse proxy in the stack. The published port is
  therefore an HTTPS port: `vaultwarden_https_port` (default `443`) on
  `vaultwarden_bind_ip`
- Installs the PEM pair into `{{ vaultwarden_dir }}/ssl` (`cert.pem` `0644`,
  `key.pem` `0600`) and restarts the container when either changes
- Closes signups by default and enables invitations, so accounts are created by
  an existing user or from the `/admin` panel
- Enables the `/admin` panel only when `vaultwarden_admin_token` is set; the
  token is interpolated from a `0600` `.env` next to the compose file, never
  inlined into `compose.yaml`

## Gotchas

- **The certificate is yours to renew.** The role has no ACME client: it writes
  whatever `vaultwarden_tls_cert` / `vaultwarden_tls_key` hold and restarts the
  container. Renewal means updating those variables and converging again —
  Rocket reads both files once at startup, so nothing picks up a new certificate
  on its own.
- **The clients insist on HTTPS.** A browser or a Bitwarden app will not talk to
  a plain-HTTP vault (except on localhost), and a self-signed certificate is
  rejected by the mobile and desktop clients until its CA is trusted on the
  device. The published port speaks TLS only — nothing listens on plain HTTP to
  redirect, so `http://…` to that port just fails.
- **`vaultwarden_domain` must match what the browser shows, port included** (e.g.
  `https://vault.example.com:8443`). It is the origin for passkeys/WebAuthn and
  the base of invitation and password-reset links; changing it later invalidates
  registered passkeys and pending invites.
- **The first account needs a way in.** With signups closed and no admin token
  there is no way to register: set `vaultwarden_signups_allowed: true`,
  converge, create your account, then set it back to `false` — or set an admin
  token and invite from `/admin`.
- **Published ports bypass UFW.** Docker publishes via DNAT, so a
  `ufw_group_rules` entry will *not* restrict the vault — `vaultwarden_bind_ip`
  is the access control. Keep it on an internal address (e.g. wg0's) if the
  vault should be VPN-only.
- **The admin panel writes its own config.** Settings changed under `/admin` are
  stored in `{{ vaultwarden_dir }}/data/config.json`, outside Ansible's control,
  where they can shadow what this role renders. Change settings here and
  converge instead.
- **`$` in `.env` is compose syntax.** `openssl rand -base64 48` is a fine admin
  token. If you prefer the hashed form
  (`docker run --rm -it vaultwarden/server /vaultwarden hash`), double every `$`
  in the value — `docker compose` interpolates `.env` and would otherwise eat
  parts of the Argon2 string.
- **Back up `{{ vaultwarden_dir }}/data`.** It holds `db.sqlite3` plus the RSA
  keys that sign login tokens; a copy taken while the container writes can be
  torn, so stop the stack or use `sqlite3 db.sqlite3 ".backup ..."`.

## Key variables

- `vaultwarden_domain` — external URL clients use, including the port when it is
  not 443 (no default)
- `vaultwarden_tls_cert` / `vaultwarden_tls_key` — PEM certificate chain and
  private key (key from vault; no defaults)
- `vaultwarden_https_port` — published HTTPS port (default `443`)
- `vaultwarden_bind_ip` — host IP the port is published on (default `0.0.0.0`)
- `vaultwarden_dir` — compose project directory (default `/containers/vaultwarden`)
- `vaultwarden_deploy` — bring the stack up (default `true`; the molecule
  scenario sets it `false` to render config only)
- `vaultwarden_admin_token` — `/admin` panel token (vault; default empty = panel
  disabled)
- `vaultwarden_signups_allowed` — open registration (default `false`)
- `vaultwarden_invitations_allowed` — let existing users invite others (default
  `true`)
- `vaultwarden_image` / `vaultwarden_version_tag` — image and tag (default
  `vaultwarden/server:latest`; pin these in inventory)
- `timezone` — container timezone (default `UTC`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/vaultwarden.yml`

Targets the `vaultwarden` group. Configure it in `group_vars/vaultwarden/`:

```yaml
# vars.yml
vaultwarden_domain: "https://vault.example.com:8443"
vaultwarden_https_port: 8443
vaultwarden_bind_ip: "10.10.0.1" # wg0 -> reachable over the VPN only

vaultwarden_tls_cert: "{{ vault_vaultwarden_tls_cert }}"
vaultwarden_tls_key: "{{ vault_vaultwarden_tls_key }}"
vaultwarden_admin_token: "{{ vault_vaultwarden_admin_token }}"

# vault.yml (ansible-vault)
vault_vaultwarden_tls_cert: |
  -----BEGIN CERTIFICATE-----
  ...
vault_vaultwarden_tls_key: |
  -----BEGIN PRIVATE KEY-----
  ...
vault_vaultwarden_admin_token: "..." # openssl rand -base64 48
```

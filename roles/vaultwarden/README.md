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
- **Locks account creation down entirely**: `SIGNUPS_ALLOWED` and
  `INVITATIONS_ALLOWED` are rendered `false` and no `ADMIN_TOKEN` is set, so
  nobody can register or be invited, the `/admin` panel stays disabled and no
  admin secret lives in vault or on the host. None of that is configurable —
  adding an account is a deliberate manual step (see below)
- Installs `/usr/local/bin/vaultwarden-backup.sh` and a **daily cron job**
  (03:30 by default) that writes one timestamped `0600` tarball per run into
  `{{ vaultwarden_backup_dir }}` (default `{{ vaultwarden_dir }}/backup`) and
  keeps the newest `vaultwarden_backup_keep` (default 10), pruning the rest.
  The database is copied with SQLite's online backup API, so the stack keeps
  running; attachments, sends, `config.json` and the RSA token signing keys go
  into the same archive

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
- **Every account is created by hand.** Signups and invitations are both off and
  there is no admin panel, so a fresh vault has no way in — and the role has no
  variable to open one, for the first user or any later one. Open registration
  on the host for as long as it takes:

  ```sh
  cd /containers/vaultwarden
  sed -i 's/SIGNUPS_ALLOWED: "false"/SIGNUPS_ALLOWED: "true"/' compose.yaml
  docker compose up -d
  # register at vaultwarden_domain in a browser, then close it again:
  ansible-playbook -i inventories/production/hosts playbooks/vaultwarden.yml
  ```

  The converge rewrites `compose.yaml` from the template and recreates the
  container, which is what puts the setting back — leaving it open is a thing
  you have to actively forget to undo.

- **There is no admin token, on purpose.** Nothing here renders `ADMIN_TOKEN`,
  so `/admin` just reports that it is disabled and no admin secret sits in vault
  or on the host. If you ever need the panel (diagnostics, deleting a user), add
  the variable to `{{ vaultwarden_dir }}/compose.yaml` on the host the same way,
  and converge again when you are done.
- **Published ports bypass UFW.** Docker publishes via DNAT, so a
  `ufw_group_rules` entry will *not* restrict the vault — `vaultwarden_bind_ip`
  is the access control. Keep it on an internal address (e.g. wg0's) if the
  vault should be VPN-only.
- **The admin panel writes its own config.** Should you enable it by hand,
  settings changed under `/admin` are stored in
  `{{ vaultwarden_dir }}/data/config.json`, outside Ansible's control, where they
  can shadow what this role renders. Change settings here and converge instead.
- **Upgrades migrate the database.** Bumping `vaultwarden_version_tag` makes the
  next converge pull that release and migrate `data/db.sqlite3` on first start,
  which cannot be rolled back — read the release notes and take a backup first
  (`/usr/local/bin/vaultwarden-backup.sh`).
- **The backups stay on the same host.** Ten daily tarballs next to the data
  they came from survive a bad upgrade, not a dead disk — copy
  `{{ vaultwarden_backup_dir }}` off the machine with whatever does the rest of
  your off-site backups. The archives are unencrypted: vault *items* are
  end-to-end encrypted, but the token signing keys and attachment metadata in
  there are not.
- **Restoring means stopping the stack first**, and the stale WAL/SHM files have
  to go with it — they belong to the database you are replacing:

  ```sh
  cd /containers/vaultwarden
  docker compose down
  rm -f data/db.sqlite3 data/db.sqlite3-wal data/db.sqlite3-shm
  tar xzf backup/vaultwarden-<timestamp>.tar.gz -C data
  docker compose up -d
  ```

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
- `vaultwarden_image` / `vaultwarden_version_tag` — image and tag, pinned to an
  exact release (default `vaultwarden/server:1.37.1`)
- `vaultwarden_backup_enabled` — install the script and the cron job (default
  `true`; `false` removes the job again and leaves the archives alone)
- `vaultwarden_backup_dir` — where the archives land (default
  `{{ vaultwarden_dir }}/backup`)
- `vaultwarden_backup_keep` — archives kept, oldest pruned first (default `10`)
- `vaultwarden_backup_hour` / `vaultwarden_backup_minute` — when the daily run
  happens, in host time (default `3` / `30`)
- `vaultwarden_backup_script` — path of the rendered script (default
  `/usr/local/bin/vaultwarden-backup.sh`)
- `timezone` — container timezone (default `UTC`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/vaultwarden.yml`

Targets the `vaultwarden` group. `--tags backup` re-applies just the backup
script and its cron job; `/usr/local/bin/vaultwarden-backup.sh` also runs by hand
whenever you want an extra archive (before an image bump, say).

Configure it in `group_vars/vaultwarden/`:

```yaml
# vars.yml
vaultwarden_domain: "https://vault.example.com:8443"
vaultwarden_https_port: 8443
vaultwarden_bind_ip: "10.10.0.1" # wg0 -> reachable over the VPN only

vaultwarden_tls_cert: "{{ vault_vaultwarden_tls_cert }}"
vaultwarden_tls_key: "{{ vault_vaultwarden_tls_key }}"

# vault.yml (ansible-vault)
vault_vaultwarden_tls_cert: |
  -----BEGIN CERTIFICATE-----
  ...
vault_vaultwarden_tls_key: |
  -----BEGIN PRIVATE KEY-----
  ...
```

Accounts are not configured here at all — see the gotcha above for the manual
way to register the first one.

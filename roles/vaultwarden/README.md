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
- Installs `/usr/local/bin/vaultwarden-backup.sh` and a **daily cron job**
  (03:30 by default) that writes one timestamped `0640` tarball per run into the
  setgid `{{ vaultwarden_backup_dir }}` (default `{{ vaultwarden_dir }}/backup`,
  `2750 root:root` until a standby's account owns the group) and
  keeps the newest `vaultwarden_backup_keep` (default 10), pruning the rest.
  The database is copied with SQLite's online backup API, so the stack keeps
  running; attachments, sends, `config.json` and the RSA token signing keys go
  into the same archive
- Optionally keeps a **second site** in step: a standby host renders the same
  stack but leaves it stopped, pulls the primary's archives over SSH nightly and
  unpacks the newest into its data directory — see [Second site](#second-site)

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
- **Only one instance may ever run.** Vaultwarden has no replication: a write
  that reaches a second live instance diverges permanently, with no merge path
  and no warning to the user who loses it. That is why the standby's stack is
  rendered but stopped, and why the sync script exits untouched if it finds a
  running container — see [Second site](#second-site).
- **The standby is a copy, not a mirror.** It is as fresh as the last archive it
  pulled: worst case a backup interval plus the gap to the sync, so ~24h with the
  defaults. Vault edits after that are gone if the primary's disk is.
- **The backups still want to leave the building.** A [second
  site](#second-site) covers a dead host; two hosts in one rack do not cover the
  rack. Copy `{{ vaultwarden_backup_dir }}` off with whatever does the rest of
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

## Second site

Ten archives next to the data they came from survive a bad upgrade, not a dead
host. A second host closes that gap: it renders the **identical** stack — same
`vaultwarden_domain`, certificate and admin token — keeps the container
**stopped**, and pulls the primary's archives every night, unpacking the newest
into its data directory. Taking over is `docker compose up -d` plus a DNS
change; clients and their passkeys see no difference. RPO is one backup
interval, RTO a minute.

```yaml
# inventories/production/hosts
[vaultwarden]
vault-01
vault-02

[vaultwarden_standby]
vault-02
```

```yaml
# group_vars/vaultwarden/vars.yml  - shared, and that sameness is the point
vaultwarden_domain: "https://vault.example.com"
vaultwarden_tls_cert: "{{ vault_vaultwarden_tls_cert }}"
vaultwarden_tls_key: "{{ vault_vaultwarden_tls_key }}"

# group_vars/vaultwarden_standby/vars.yml
vaultwarden_standby: true
vaultwarden_sync_source: vault-01

# host_vars/vault-01/vars.yml  - the primary serves its archives
vaultwarden_sync_serve: true
vaultwarden_sync_from_ip: "10.10.0.9" # optional, pins the key to one address
```

`ansible-playbook … playbooks/vaultwarden.yml` then converges both sides in one
run. The two hosts exchange **public** material through
`{{ vaultwarden_sync_key_dir }}` on the control node
(`inventories/<env>/vaultwarden_keys/`, the same idiom the
[wireguard](../wireguard/README.md) role uses for generated configs): the standby
publishes its sync public key, the primary its SSH host key so the pull runs with
strict host checking. Both belong in git. Revoking a standby is deleting its
`.pub` and converging.

On the primary the standby's key is authorised for a `vwsync` account with no
shell, pinned to `command="rrsync -ro <backup dir>"` — that key yields the
backups and nothing else on the host. The standby needs to reach
`sshd_port` there, which is inventory's job via the [ufw](../ufw/README.md) role:

```yaml
# host_vars/vault-01/vars.yml
ufw_host_rules:
  - rule: allow
    port: "{{ sshd_port }}"
    proto: tcp
    from_ip: "10.10.0.9"
    comment: "Vaultwarden backup sync"
```

Best run over a private path. This role does not build one: the
[wireguard](../wireguard/README.md) role here is a road-warrior server, so
host-to-host means adding the standby as a peer and applying that config
yourself.

### Promoting the standby

1. **Make sure the primary is really down.** Two running instances diverge
   permanently — Vaultwarden has no replication and no merge path.
2. Set `vaultwarden_standby: false` for that host and converge: the sync cron
   goes away, the stack starts, and its own backup cron takes over. Without
   Ansible to hand: `docker compose up -d` in `{{ vaultwarden_dir }}` and
   `crontab -l -u root` to drop the sync job.
3. Point DNS at the promoted host. Nothing changes for clients.
4. Failing back: restore the **promoted** host's newest archive onto the repaired
   primary ([Restoring](#gotchas)), then swap the two hosts in inventory. Never
   just start the old primary again — its data is stale, and starting it while
   the other one serves is exactly the split brain above.

Rehearse this once in a maintenance window. An untested failover is a hope.

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
- `vaultwarden_backup_enabled` — install the script and the cron job (default
  `true`; `false` removes the job again and leaves the archives alone)
- `vaultwarden_backup_dir` — where the archives land (default
  `{{ vaultwarden_dir }}/backup`)
- `vaultwarden_backup_keep` — archives kept, oldest pruned first (default `10`)
- `vaultwarden_backup_hour` / `vaultwarden_backup_minute` — when the daily run
  happens, in host time (default `3` / `30`)
- `vaultwarden_backup_script` — path of the rendered script (default
  `/usr/local/bin/vaultwarden-backup.sh`)
- `vaultwarden_standby` — this host is the second site: stack rendered but not
  started, archives pulled instead of taken (default `false`)
- `vaultwarden_sync_serve` — this host serves its archives to a standby (default
  `false`)
- `vaultwarden_sync_source` — standby only: inventory hostname of the primary it
  pulls from (no default)
- `vaultwarden_sync_keep` — archives kept on the standby (default `30`)
- `vaultwarden_sync_restore` — unpack the newest archive into `data/` after every
  pull (default `true`; `false` keeps archives only)
- `vaultwarden_sync_hour` / `vaultwarden_sync_minute` — when the pull runs
  (default `4` / `0`, after the primary's backup)
- `vaultwarden_sync_from_ip` — optional `from=` on the authorised key
- `vaultwarden_sync_key_dir` — where the two sides exchange public keys (default
  `{{ inventory_dir }}/vaultwarden_keys`)
- `vaultwarden_sync_user` / `vaultwarden_sync_group` — restricted account on the
  primary (default `vwsync`)
- `vaultwarden_sync_port` / `vaultwarden_sync_address` — SSH port and address of
  the primary (default `sshd_port` and the source's `ansible_host`)
- `vaultwarden_sync_key` / `vaultwarden_sync_script` / `vaultwarden_sync_rrsync` —
  paths of the standby's key, its sync script and the `rrsync` wrapper
- `timezone` — container timezone (default `UTC`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/vaultwarden.yml`

Targets the `vaultwarden` group — primary and standby together, so one run wires
both sides up. `--tags backup` / `--tags sync` re-apply just those scripts and
their cron jobs; `/usr/local/bin/vaultwarden-backup.sh` and
`/usr/local/bin/vaultwarden-sync.sh` also run by hand whenever you want an extra
archive or an immediate pull (before an image bump, say).

Configure it in `group_vars/vaultwarden/`:

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

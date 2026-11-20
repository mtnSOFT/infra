# borgmatic_client

Backs a host up with [borgmatic](https://torsion.org/borgmatic/) to its own
repository on a [borg_server](../borg_server/README.md), on a systemd timer.

## What it does

- Installs `borgbackup`, `borgmatic` and `openssh-client` from apt (Ubuntu 24.04
  ships borgmatic 1.8, which uses the flat config format)
- Generates `/root/.ssh/borg_ed25519` once. The server reads it and pins it to
  `borg serve --append-only` on this host's repository.
- Reads the server's ed25519 host key from the server itself and adds it to
  root's `known_hosts`, so the first connection never trusts an unknown key
- Writes `/etc/borgmatic/passphrase` (`0600`) and `/etc/borgmatic/config.yaml`
  (`0600`, checked with `borgmatic config validate` before it is put in place)
- Renders `borgmatic.service` (`create --stats` + `check`) and `borgmatic.timer`
  (default daily at 02:00 plus up to 1h random delay) and enables the timer
  where systemd is PID 1

## Gotchas

- **No prune or compact here.** The repository is append-only for this host.
  Retention is applied by the server, and you set it per host with
  `borgmatic_client_retention`. Running `borgmatic prune` by hand does nothing
  useful.
- **The repository is created by the server**, not by this role. Run
  `playbooks/borg_backup.yml`, which orders the plays client keygen, then server,
  then client config, rather than this role on its own on a new host.
- **The repokey is exported by the server role**, vault-encrypted into the
  private inventory (`borg_keys/<host>.key`). You don't need to export it by hand.
- **The passphrase also ends up on the server** (see the borg_server README) and
  must come from vault.
- `one_file_system: true` is set. Mounts under a source directory are skipped
  unless you list them explicitly.
- Database dumps: set `borgmatic_client_postgresql_databases`, for example
  `[{name: all}]`. It is passed to borgmatic's `postgresql_databases` hook as-is.

## Key variables

- `borgmatic_client_server`: inventory hostname of the borg server (required)
- `borgmatic_client_passphrase`: repository passphrase, from vault (required)
- `borgmatic_client_server_address` / `_port`: SSH target (default: the server's
  `ansible_host` / `sshd_port`, else its inventory name / 22)
- `borgmatic_client_source_directories`: default `/etc`, `/root`, `/home`,
  `/var/backups`, `/usr/local`
- `borgmatic_client_exclude_patterns`: default root and home `.cache`
- `borgmatic_client_retention`: per-host override of `borg_server_retention`
  (default `{}`)
- `borgmatic_client_postgresql_databases`: borgmatic DB hook (default `[]`)
- `borgmatic_client_on_calendar`: systemd `OnCalendar` (default
  `*-*-* 02:00:00`)
- `borgmatic_client_backup_now`: run one backup during the converge (default
  `false`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/borg_backup.yml`

Configure it in `group_vars/borgmatic_clients/` or per host:

```yaml
# vars.yml
borgmatic_client_server: "backuphost"
borgmatic_client_passphrase: "{{ vault_borgmatic_client_passphrase }}"

# host_vars/apphost/vars.yml
borgmatic_client_retention:
  keep_daily: 14

# vault.yml (ansible-vault). Use one passphrase per host if you can.
vault_borgmatic_client_passphrase: "..."
```

To check a host by hand:

```bash
systemctl list-timers borgmatic.timer
borgmatic create --stats --verbosity 1
borgmatic list
```

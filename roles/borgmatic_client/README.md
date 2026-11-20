# borgmatic_client

Backs a host up with [borgmatic](https://torsion.org/borgmatic/) to its own
repository on a [borg_server](../borg_server/README.md), on a systemd timer.

## What it does

- Installs `borgbackup`, `borgmatic` and `openssh-client` from apt (Ubuntu 24.04
  ships borgmatic 1.8, which uses the flat config format)
- Generates `/root/.ssh/borg_ed25519` once. The server pins it to `borg serve`
  on this host's repository.
- Reads the server's ed25519 host key from the server itself and adds it to
  root's `known_hosts`, so the first connection never trusts an unknown key
- Writes `/etc/borgmatic/passphrase` (`0600`) and `/etc/borgmatic/config.yaml`
  (`0600`, checked with `borgmatic config validate` before it is put in place)
- Creates the repository on the server (`borg init`, `repokey-blake2`) if it
  doesn't exist yet
- Exports the repository key once and stores it vault-encrypted on the
  controller as `borg_keys/<host>.key` next to the inventory
- Renders `borgmatic.service` (`create`, `prune`, `compact`, `check`) and
  `borgmatic.timer` (default daily at 02:00 plus up to 1h random delay), and
  enables the timer where systemd is PID 1

## Gotchas

- **The passphrase exists only here and in vault.** The server never sees it,
  so a compromised server can't read the backups.
- **Retention is set here** (`borgmatic_client_retention`). Archives this host
  prunes stay recoverable from the server's btrfs snapshots for the snapshot
  retention (default about 3 months).
- **The repository is created over SSH**, so the server role must have rendered
  this host's `authorized_keys` line first. Add a new host with
  `playbooks/borg_backup.yml`. If the server's backup disk
  isn't mounted, repository creation fails, as it should.
- **The key export runs only if the key file is missing.** It never overwrites
  an export. If you re-create a repository, delete the old `.key` file first.
- **The key export needs the vault password non-interactively** because the key
  is piped into `ansible-vault encrypt` on the controller. That means
  `ANSIBLE_VAULT_PASSWORD_FILE` or `vault_identity_list` in the config, or a
  `--vault-id` in `borgmatic_client_key_export_vault_args`. `--ask-vault-pass`
  alone doesn't work.
- **Commit the exported keys to the private inventory repo**, not this one.
- `one_file_system: true` is set. Mounts under a source directory are skipped
  unless you list them explicitly.
- Database dumps: set `borgmatic_client_postgresql_databases`, for example
  `[{name: all}]`. It is passed to borgmatic's `postgresql_databases` hook as-is.

## Restoring after the repository config is lost

You need the repository data, the passphrase from vault and the exported key:

```bash
ansible-vault view inventories/production/borg_keys/apphost.key > /tmp/apphost.key
borg key import ssh://borg@backuphost:22/srv/borg/data/apphost /tmp/apphost.key
shred -u /tmp/apphost.key
```

## Key variables

- `borgmatic_client_server`: inventory hostname of the borg server (required)
- `borgmatic_client_passphrase`: repository passphrase, from vault (required)
- `borgmatic_client_server_address` / `_port`: SSH target (default: the server's
  `ansible_host` / `sshd_port`, else its inventory name / 22)
- `borgmatic_client_retention`: borgmatic `keep_*` options (default 7 daily,
  4 weekly, 6 monthly)
- `borgmatic_client_source_directories`: default `/etc`, `/root`, `/home`,
  `/var/backups`, `/usr/local`
- `borgmatic_client_exclude_patterns`: default root and home `.cache`
- `borgmatic_client_postgresql_databases`: borgmatic DB hook (default `[]`)
- `borgmatic_client_on_calendar`: systemd `OnCalendar` (default
  `*-*-* 02:00:00`)
- `borgmatic_client_backup_now`: run one backup during the converge (default
  `false`)
- `borgmatic_client_key_export` / `_dir` / `_vault_args`: repository key export
  (default on, `{{ inventory_dir }}/borg_keys`, no extra arguments)

## Usage

| Playbook | Runs | Use it for |
|---|---|---|
| `playbooks/borg_backup.yml` | client keygen, then server, then clients | adding a client, first setup |
| `playbooks/borg_server.yml` | server only | server changes (snapshots, scrub, removing a client) |
| `playbooks/borgmatic_clients.yml` | clients only | client changes (sources, retention, schedule) |

```bash
ansible-playbook -i inventories/production/hosts playbooks/borg_backup.yml -l apphost,backuphost
```

`borg_backup.yml` needs both the new client and its server in `--limit`.

Configure it in `group_vars/borgmatic_clients/` or per host:

```yaml
# vars.yml
borgmatic_client_server: "backuphost"
borgmatic_client_passphrase: "{{ vault_borgmatic_client_passphrase }}"

# host_vars/apphost/vars.yml
borgmatic_client_retention:
  keep_daily: 14
  keep_weekly: 8
  keep_monthly: 12

# vault.yml (ansible-vault). Use one passphrase per host if you can.
vault_borgmatic_client_passphrase: "..."
```

To check a host by hand:

```bash
systemctl list-timers borgmatic.timer
borgmatic create --stats --verbosity 1
borgmatic list
```

# borg_server

Stores [borg](https://www.borgbackup.org/) repositories for the hosts running
[borgmatic_client](../borgmatic_client/README.md). Each client gets one
repository, reachable only through an SSH forced command that runs `borg serve`
in append-only mode. Pruning and compacting happen on this host.

## What it does

- Installs `borgbackup` and creates the system user `borg` (home
  `borg_server_home`, default `/srv/borg`)
- Finds its clients: hosts in `borg_server_clients_group` (default
  `borgmatic_clients`) whose `borgmatic_client_server` names this host
- Reads each client's public key **from the client** (`delegate_to`) and renders
  `~borg/.ssh/authorized_keys` with one line per client:
  `command="borg serve --append-only --restrict-to-repository <repos>/<client>",restrict …`
- Writes each client's passphrase to `borg_server_passphrase_dir/<client>`
  (`0400 borg`) and runs `borg init --encryption repokey-blake2` on new
  repositories
- Installs `/usr/local/bin/borg-prune-all.sh` and a daily `borg-prune.timer`
  that runs `borg prune` + `borg compact` on every client repository

## Gotchas

- **This server holds every repository passphrase.** Append-only clients can't
  remove data, so pruning has to run here, and `borg prune` needs the key. A
  compromised server can therefore read the backups. A compromised client can't
  delete them, which is the trade-off this setup makes.
- **Append-only is a `borg serve` flag, not a repository setting.** Local `borg`
  commands on this host (the prune run, or you by hand) have full access.
- **Append-only protection only lasts until the next compact.** A delete or
  prune from a compromised client is only logged, and the data stays in the
  repository until `borg compact` runs here. If you suspect a client was
  compromised, stop `borg-prune.timer` first, then roll back the transactions as
  the borg docs on append-only mode describe.
- **A client removed from the inventory loses SSH access** on the next run
  because `authorized_keys` is rendered whole. Its repository and passphrase file
  stay, and you delete them by hand.
- **Every client must have run `borgmatic_client` at least once** (or at least
  its `2_ssh` tasks), otherwise reading its key fails.
  `playbooks/borg_backup.yml` handles that ordering.
- Repositories are created here, so the repokey lives only in the repository.
  Export it from the client and keep it outside the backup:
  `borgmatic key export`.
- The timer is only enabled where systemd is PID 1. In the molecule container
  the units are rendered and not enabled.
- Clients need to reach this host's sshd, so open that port for them in ufw or
  OPNsense.

## Key variables

- `borg_server_home`: home of the `borg` user (default `/srv/borg`)
- `borg_server_repos_dir`: one repository per client below it (default
  `{{ borg_server_home }}/repos`). Clients read it through hostvars.
- `borg_server_passphrase_dir`: per-client passphrase files (default
  `/etc/borg-server`)
- `borg_server_clients_group`: group to look for clients in (default
  `borgmatic_clients`)
- `borg_server_retention`: `keep_daily`/`keep_weekly`/`keep_monthly` (default
  7/4/6). Clients override any key with `borgmatic_client_retention`.
- `borg_server_prune_on_calendar`: systemd `OnCalendar` of the prune run (default
  `*-*-* 05:30:00`)
- `borg_server_lock_wait`: seconds the prune waits for a running backup (default
  600)
- `borg_server_encryption`: mode for new repositories (default `repokey-blake2`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/borg_backup.yml`

```ini
[borg_servers]
backuphost

[borgmatic_clients]
apphost
dnshost
```

To check by hand on the server:

```bash
systemctl list-timers borg-prune.timer
systemctl start borg-prune.service && journalctl -u borg-prune -n 50
```

# borg_server

Stores [borg](https://www.borgbackup.org/) repositories on a btrfs backup disk
for the hosts running [borgmatic_client](../borgmatic_client/README.md), and
protects them with read-only [btrbk](https://digint.ch/btrbk/) snapshots.

Clients have normal borg access to their own repository: they create, prune and
compact it themselves, and their passphrase never reaches this host. What keeps
a compromised client from destroying its backups is the snapshots. It can delete
its archives, but it can't touch the read-only snapshots on this host.

## What it does

- Installs `borgbackup`, `btrbk` and `btrfs-progs`, and creates the system user
  `borg` with its home at `/var/lib/borg`, off the backup disk
- Checks that `borg_server_repos_dir` (`/srv/borg/data`) exists and is a btrfs
  subvolume, and fails otherwise. **It never creates it.**
- Finds its clients: hosts in `borg_server_clients_group` (default
  `borgmatic_clients`) whose `borgmatic_client_server` names this host
- Reads each client's public key **from the client** (`delegate_to`) and renders
  `~borg/.ssh/authorized_keys` with one line per client:
  `command="borg serve --restrict-to-repository /srv/borg/data/<client>",restrict …`
- Configures btrbk to snapshot the `data` subvolume into `/srv/borg/.snapshots`
  (default retention `2d` minimum, then `14d 8w 3m`) and moves the packaged
  `btrbk.timer` to 06:00
- Adds a monthly `borg-scrub.timer` that runs `btrfs scrub` on the disk

## Disk setup (once, by hand)

```bash
mkfs.btrfs -L borg /dev/sdX                   # erases the disk
mount /dev/disk/by-label/borg /mnt
btrfs subvolume create /mnt/data              # the repositories: snapshotted
umount /mnt

mkdir -p /srv/borg
echo 'LABEL=borg  /srv/borg  btrfs  noatime,nofail  0 0' >> /etc/fstab
systemctl daemon-reload && mount /srv/borg
```

Then run the playbook. It fixes ownership of `/srv/borg/data` and creates
`/srv/borg/.snapshots`.

- **Why `data` is its own subvolume.** btrfs snapshots work per subvolume, and
  the snapshots shouldn't contain themselves.
- **Why the repositories aren't directly in `/srv/borg`.** When the disk isn't
  mounted, `/srv/borg` is an empty directory on the root filesystem, but
  `/srv/borg/data` doesn't exist. Every client backup then fails with
  "repository does not exist" instead of quietly filling the root disk, and
  `borg init` fails too because its parent directory is missing.
- **No btrfs compression.** borg data is already compressed and encrypted.

## Gotchas

- **Snapshot retention is how long you have to notice an attack.** A compromised
  client can delete its archives, and you have to notice before the last good
  snapshot expires.
- **Pruned data takes disk space until the snapshots expire.** Client prune and
  compact free space in borg, but the old segments stay on disk while any
  snapshot still references them. Size the disk for the borg data plus the
  churn over the snapshot window.
- **A snapshot taken during a backup is still usable.** borg treats it like a
  power cut and rolls the unfinished transaction back the next time the repo is
  opened. Snapshots run at 06:00, after the default backup window, so this
  rarely happens anyway.
- **Scrub only detects corruption on a single disk.** It can't repair data. A
  failed `borg-scrub.service` means corrupt blocks, so restore the affected
  repository from a snapshot.
- **This host holds no passphrases**, so it can't read the backups. The
  repository keys are exported by the client role into the private inventory.
- **A client removed from the inventory loses SSH access** on the next run
  because `authorized_keys` is rendered whole. Its repository stays, and you
  delete it by hand.
- **A client that has never run `borgmatic_client` is skipped with a warning.**
  It has no key yet. An unreachable client fails the run instead, because
  rendering `authorized_keys` without it would lock it out while it's only down.
- **Timers are only enabled with systemd and `borg_server_require_btrfs: true`.**
  The molecule container has neither, so the units are rendered and not
  enabled.
- **Firewall:** clients need to reach this host's sshd, so open that port for
  them in ufw or OPNsense.

## Restoring a client repository from a snapshot

Stop the client's timer first (`systemctl stop borgmatic.timer` on the client),
then on the server:

```bash
ls /srv/borg/.snapshots/                      # data.20261201T0600 …
mv /srv/borg/data/apphost /srv/borg/data/apphost.broken
cp -a --reflink=always /srv/borg/.snapshots/data.20261201T0600/apphost /srv/borg/data/apphost
```

`--reflink` makes the copy instant and free. Restart the client timer once
`borgmatic list` on the client looks right.

## Key variables

- `borg_server_mount`: where the backup disk is mounted (default `/srv/borg`)
- `borg_server_repos_dir`: the `data` subvolume holding one repository per
  client (default `{{ borg_server_mount }}/data`). Clients read it through
  hostvars.
- `borg_server_home`: home of the `borg` user (default `/var/lib/borg`)
- `borg_server_require_btrfs`: fail unless the data directory is a btrfs
  subvolume, and only enable the timers when it is (default `true`; `false` in
  molecule)
- `borg_server_snapshot_preserve` / `_preserve_min`: btrbk retention (default
  `14d 8w 3m` / `2d`)
- `borg_server_snapshot_dir`: relative to the mount (default `.snapshots`)
- `borg_server_snapshot_on_calendar`: btrbk timer time (default
  `*-*-* 06:00:00`)
- `borg_server_scrub_on_calendar`: scrub time (default `*-*-01 08:00:00`)
- `borg_server_clients_group`: group to look for clients in (default
  `borgmatic_clients`)

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

```ini
[borg_servers]
backuphost

[borgmatic_clients]
apphost
dnshost
```

To check by hand on the server:

```bash
systemctl list-timers btrbk.timer borg-scrub.timer
btrbk list snapshots
btrfs scrub status /srv/borg
```

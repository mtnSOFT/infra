# gitea

[Gitea](https://about.gitea.com/) (self-hosted git service) as a Docker Compose
stack. Needs the [docker-compose](../docker-compose/README.md) role first.

## What it does

- Renders the compose project into `{{ gitea_dir }}` (default
  `/containers/gitea`) and brings it up with `community.docker.docker_compose_v2`
- One container with SQLite inside its data volume — no database service, no
  secrets, nothing to put in vault
- Publishes the web UI / git endpoint on
  `{{ gitea_bind_ip }}:{{ gitea_http_port }}` (default `127.0.0.1:3000`)
- Serves HTTPS itself when `gitea_tls_cert_file` / `gitea_tls_key_file` point at a
  certificate on the host: the two files are mounted read-only, never copied or
  generated, so renewals stay with whatever manages the certificate — a manual
  copy today, an ACME/DNS-API service later. Without them it stays on plain HTTP
- Configures Gitea through `GITEA__<section>__<KEY>` environment variables, which
  the image writes into `app.ini` on every start: SQLite backend, the URL, git
  over SSH off, the web installer locked and registration disabled
- Derives Gitea's `DOMAIN` from `gitea_root_url`, so there is only one URL to set
- Config, repositories and the database live in `{{ gitea_dir }}/data`, owned by
  the UID the container's git user runs as

## Gotchas

- **Published ports bypass UFW.** Docker publishes via DNAT, so a
  `ufw_group_rules` entry will _not_ restrict Gitea — `gitea_bind_ip` is the
  access control. Default `127.0.0.1`.
- **A renewed certificate needs a container restart.** Gitea reads the cert and
  key once at startup, and a bind-mounted _file_ keeps pointing at the inode it
  was mounted from, so a replaced file is invisible to the running container.
  Whatever distributes the certificate should also run:

  ```bash
  docker compose -f /containers/gitea/compose.yaml restart gitea
  ```

- **The key must be readable by the container's git user** (uid/gid `1000`), which
  is who opens it — `chown root:1000` plus `chmod 0640` on the key, `0644` on the
  certificate. `0600 root:root` gives a container that crash-loops, so the role
  checks the permissions during converge and fails with that message instead. If
  the certificate's owner cannot relax them, terminate TLS in a proxy in front of
  Gitea and leave `gitea_tls_*` unset.
- `gitea_http_port` is the published port whichever protocol is served — with a
  certificate configured, that port speaks HTTPS (set it to `443`). Gitea listens
  on one port only; there is no HTTP→HTTPS redirect.
- **The first admin is created by hand.** The web installer is locked and
  registration is off, so no account exists after the first converge:

  ```bash
  docker compose -f /containers/gitea/compose.yaml exec -u git gitea \
    gitea admin user create --admin --username admin \
    --email admin@example.com --random-password
  ```

- **Ansible owns the keys it sets.** They are rewritten into
  `data/gitea/conf/app.ini` on every container start, so editing one there is
  lost on the next restart. Keys the role does not set (mailer, actions, …)
  persist and are yours to manage in that file.
- **No mailer**, so no notification mail and no self-service password reset — use
  `gitea admin user change-password`.
- Containers are named by compose (`gitea-gitea-1`), so address the service with
  `docker compose exec gitea …` rather than a fixed container name.
- Anonymous visitors can browse public repositories; keep repositories private,
  or set `REQUIRE_SIGNIN_VIEW` in `app.ini`.
- **Upgrades migrate the database.** Bumping `gitea_version_tag` makes the next
  converge pull that release and migrate `data` on first start, which cannot be
  rolled back — read the release notes and back up first.
- Back up with `gitea dump`, or stop the stack before copying
  `{{ gitea_dir }}/data` — copying a live SQLite database can yield a corrupt file.
- SQLite fits a small instance. Moving to PostgreSQL later is a `gitea dump` /
  `gitea restore`, not a config change.

## Key variables

- `gitea_dir` — compose project directory (default `/containers/gitea`)
- `gitea_deploy` — bring the stack up (default `true`; the molecule scenario sets
  it `false` to render config only)
- `gitea_bind_ip` — host IP the web UI binds to (default `127.0.0.1`)
- `gitea_http_port` — published host port (default `3000`)
- `gitea_root_url` — external URL of the instance, and the source of Gitea's
  `DOMAIN` (default `http://localhost:{{ gitea_http_port }}/`)
- `gitea_tls_cert_file` / `gitea_tls_key_file` — host paths of the certificate
  (full chain) and its private key, mounted read-only into the container. Set both
  or neither, and make `gitea_root_url` an `https://` URL (default empty = HTTP)
- `gitea_image` / `gitea_version_tag` — image and tag, pinned to an exact release
  (default `gitea/gitea:1.27.2`)
- `gitea_uid` / `gitea_gid` — UID/GID the image runs its git user as; the data
  directory is chowned to these and they are pinned as `USER_UID` / `USER_GID` in
  compose (defaults `1000`/`1000`)
- `timezone` — container timezone (default `UTC`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/gitea.yml`

Targets the `gitea` group. The defaults run as-is; configure it in
`group_vars/gitea/`:

```yaml
# vars.yml
gitea_root_url: "https://git.example.com/"
gitea_bind_ip: "10.10.0.1" # e.g. wg0's address; 127.0.0.1 behind a proxy
gitea_http_port: 443

# Certificate on the host - copied in by hand, or dropped there by the service
# that fetches it via the DNS API. This role only mounts it read-only.
gitea_tls_cert_file: "/etc/ssl/gitea/fullchain.pem"
gitea_tls_key_file: "/etc/ssl/gitea/privkey.pem"
```

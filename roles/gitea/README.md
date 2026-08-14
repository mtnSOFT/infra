# gitea

[Gitea](https://about.gitea.com/) (self-hosted git service) as a Docker Compose
stack. Needs the [docker-compose](../docker-compose/README.md) role first.

## What it does

- Renders the compose project into `{{ gitea_dir }}` (default
  `/containers/gitea`) and brings it up with `community.docker.docker_compose_v2`
- One container with SQLite inside its data volume — no database service, no
  secrets, nothing to put in vault
- Publishes the web UI / HTTP git endpoint on
  `{{ gitea_bind_ip }}:{{ gitea_http_port }}` (default `127.0.0.1:3000`)
- Configures Gitea through `GITEA__<section>__<KEY>` environment variables, which
  the image writes into `app.ini` on every start: SQLite backend, the URL, git
  over SSH off, the web installer locked and registration disabled
- Derives Gitea's `DOMAIN` from `gitea_root_url`, so there is only one URL to set
- Config, repositories and the database live in `{{ gitea_dir }}/data`, owned by
  the UID the container's git user runs as

## Gotchas

- **Published ports bypass UFW.** Docker publishes via DNAT, so a
  `ufw_group_rules` entry will *not* restrict Gitea — `gitea_bind_ip` is the
  access control. Default `127.0.0.1`. There is no reverse proxy and no TLS; put
  one in front of it before serving `gitea_root_url` over HTTPS.
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
```

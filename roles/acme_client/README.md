# acme_client

Issues one Let's Encrypt certificate with [acme.sh](https://acme.sh/) over a
DNS-01 challenge against the Infomaniak API, deploys it to a stable path on the
host, and renews it from cron.

## What it does

- Clones acme.sh at the pinned `acme_client_version` into `/usr/local/src/acme.sh`
  and installs it for root into `/root/.acme.sh` with `--nocron`
- Issues a single certificate covering every entry of `acme_client_domains` —
  wildcards included, which is why the challenge is DNS-01 and not HTTP-01
- Deploys `cert.pem`, `key.pem` and `fullchain.pem` into `acme_client_cert_dir`
  (default `/etc/ssl/acme/<first domain without the wildcard>/`), the path other
  roles point at
- Adds a root cron job at 03:00 running `acme.sh --cron`, which renews what is
  due, re-copies the files above, re-applies the key's `0640 root:<group>` and
  runs `acme_client_reload_command`

## Gotchas

- **The API token needs `domain:read`, `dns:read` and `dns:write`.** Create it in
  the Infomaniak manager under `/api/dashboard`. It is account-wide — there is no
  per-zone scoping, so the token can rewrite every zone in the account.
- **acme.sh caches the token on the host.** It is passed as
  `INFOMANIAK_API_TOKEN` on the first issue and saved into
  `/root/.acme.sh/account.conf` (`0600 root`), which is how the cron renewal
  authenticates without Ansible. Rotating the token in vault therefore is not
  enough on its own — re-run the role, or edit `SAVED_INFOMANIAK_API_TOKEN` there.
- **acme.sh defaults to ZeroSSL**, which needs EAB registration. The role passes
  `--server letsencrypt` explicitly. acme.sh records the CA per certificate, so
  the cron renewal stays on whichever CA issued it — switching
  `acme_client_server` afterwards needs a manual `--issue --force`.
- **Use `letsencrypt_test` first.** Let's Encrypt allows five duplicate
  certificates per name set per week, and a broken DNS setup burns through that in
  one afternoon.
- **A renewed certificate needs the consumer restarted.** A bind-mounted _file_
  keeps pointing at the inode it was mounted from, so a replaced file is invisible
  to a running container. Set `acme_client_reload_command`:

  ```yaml
  acme_client_reload_command: "docker compose -f /containers/gitea/compose.yaml restart gitea"
  ```

  The role always passes a `--reloadcmd`, whether or not you set one: it prefixes
  yours with `chown root:<acme_client_key_group>` and `chmod 0640` on the key.
  Two constraints follow. Use no double quotes in the value — the whole thing
  becomes one shell-quoted argument. And acme.sh treats a failing reload as an
  error, so on a fresh host, where this role runs before the consumer exists,
  either leave it empty for the first converge or end it with `|| true`.

- **A converge does not re-issue a valid certificate.** acme.sh renews only
  inside the renewal window and otherwise reports `Skipping. Next renewal time
  is: …` and exits `2`, which the role treats as "nothing to do" — that is what
  makes a second converge report no change. To replace a certificate before it is
  due, set `acme_client_force` for that one run:

  ```bash
  ansible-playbook -i inventories/production/hosts playbooks/acme_client.yml \
    -l <host> --tags certificate -e acme_client_force=true
  ```

  Leave it out of `group_vars` — every forced run spends one of the five
  duplicate certificates the CA allows per name set per week. Point
  `acme_client_server` at `letsencrypt_test` while you are still iterating.

- **The deploy step only runs when there is something new to deploy** — nothing
  in `acme_client_cert_dir` yet, or the issue step just obtained a certificate
  (a forced one counts). It cannot run on every converge, because acme.sh
  executes `--reloadcmd` inline as part of `--install-cert`, which would restart
  the consuming service each time. So a changed `acme_client_reload_command` or
  a changed path takes effect at the next issue or renewal; to apply it right
  away, run it once by hand:

  ```bash
  /root/.acme.sh/acme.sh --install-cert --ecc -d '*.int.example.com' \
    --cert-file /etc/ssl/acme/int.example.com/cert.pem \
    --key-file /etc/ssl/acme/int.example.com/key.pem \
    --fullchain-file /etc/ssl/acme/int.example.com/fullchain.pem \
    --reloadcmd "docker compose -f /containers/gitea/compose.yaml restart gitea"
  ```

- **The private key is `0640 root:{{ acme_client_key_group }}`**, not `0600
  root:root`, because a container that cannot read the key crash-loops on start.
  Set `acme_client_key_group` to the consumer's gid (gitea runs as `1000`).

  It is applied in two places, which is deliberate. acme.sh writes a fresh key as
  `0600 root:root` whenever it has to _create_ the file rather than overwrite it,
  and the renewal that does so runs unattended from cron — a converge-time task
  alone would leave the consumer broken until someone next ran Ansible. So the
  chown/chmod is also the first thing in the `--reloadcmd`, ahead of your restart,
  and the task stays as the thing that applies a _changed_ `acme_client_key_group`
  without waiting for a renewal.

  If the group looks wrong after a converge, check where you set the variable
  before changing anything else — `1000` is a gitea number, and it belongs in
  `group_vars/acme_client/`, not `group_vars/gitea/`. `ansible.cfg` sets
  `no_log` globally, so run with `ANSIBLE_NO_LOG=false … -v` to see what the task
  actually did.
- **One certificate per host.** `acme_client_domains` is a flat list, all of it on
  one certificate. A host that needs two independent certificates is out of scope
  here.
- The certificate is named after `acme_client_domains[0]`, so reordering the list
  makes acme.sh file it under a new name and issue a fresh one.
- `acme_client_issue: false` renders everything but talks to no CA — that is what
  the molecule scenario runs on.

## Key variables

- `acme_client_domains` — the `-d` arguments; first entry names the certificate,
  the rest are SANs on it (default `[]`, required)
- `acme_client_email` — ACME account contact (default empty, required)
- `acme_client_infomaniak_api_token` — from vault; required while
  `acme_client_issue` is `true` (default empty)
- `acme_client_server` — CA shorthand passed to `--server` (default
  `letsencrypt`; use `letsencrypt_test` while debugging)
- `acme_client_cert_dir` — where the certificate is deployed (default
  `/etc/ssl/acme/{{ acme_client_cert_name }}`)
- `acme_client_cert_name` — directory name, derived from the first domain with the
  wildcard stripped
- `acme_client_key_group` — group that may read `key.pem` at `0640` (default
  `root`)
- `acme_client_reload_command` — appended to the key's chown/chmod in the
  `--reloadcmd` acme.sh runs after a successful renewal (default empty)
- `acme_client_force` — re-issue even when the certificate is still valid; a
  one-off `-e acme_client_force=true`, not a `group_vars` setting (default
  `false`)
- `acme_client_keylength` — key type (default `ec-256`)
- `acme_client_version` — pinned acme.sh git tag (default `3.1.4`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/acme_client.yml`

Targets the `acme_client` group. Configure it in `group_vars/acme_client/`:

```yaml
# vars.yml
acme_client_email: "admin@example.com"
acme_client_domains:
  - "*.int.example.com"
  - "*.lan.example.com"
acme_client_infomaniak_api_token: "{{ vault_acme_client_infomaniak_api_token }}"

# The gid gitea's container reads the key as, plus the restart it needs after a
# renewal.
acme_client_key_group: "1000"
acme_client_reload_command: "docker compose -f /containers/gitea/compose.yaml restart gitea"

# vault.yml (ansible-vault)
vault_acme_client_infomaniak_api_token: "..."
```

Consumers then point at the deployed files, e.g. in `group_vars/gitea/vars.yml`:

```yaml
gitea_tls_cert_file: "/etc/ssl/acme/int.example.com/fullchain.pem"
gitea_tls_key_file: "/etc/ssl/acme/int.example.com/key.pem"
```

Run this role before the roles that consume the certificate — they assert the
files exist, so on a fresh host they fail if this has not run yet.

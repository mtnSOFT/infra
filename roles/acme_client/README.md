# acme_client

Wildcard TLS certificates for internal zones, obtained and renewed with
[lego](https://go-acme.github.io/lego/) over an ACME DNS-01 challenge against the
Infomaniak DNS API, and deployed where the service roles already read them.

## What it does

- Installs a pinned, checksummed `lego` release — a single static binary, so no
  Python virtualenv and no extra Ansible collections
- Takes a list of certificates in `acme_client_certificates` and, for each,
  renders a config file and a `acme-client-renew@<zone>` systemd service and
  timer, so every certificate is renewed independently of the others
- Writes each result to `/etc/ssl/<zone>/fullchain.pem` and
  `/etc/ssl/<zone>/privkey.pem`, with per-certificate ownership and modes — the
  paths `gitea_tls_cert_file` and `vaultwarden_tls_cert_file` already point at,
  so no consumer role or its inventory needs changing
- Runs the per-certificate `reload_commands` after, and only after, a pair is
  actually replaced
- Obtains anything missing during the converge too, so a fresh host has its
  certificates before a consumer role asserts they exist
- Retires a certificate when its entry is removed: the timer is disabled and the
  config deleted, while the deployed files and lego's state are left alone

The API token is never a shell argument, a unit-file value or an environment
variable. It is rendered to a `0600` file and passed to lego as
`INFOMANIAK_ACCESS_TOKEN_FILE`.

## Gotchas

- **The internal resolver never sees the challenge, and this is what breaks
  first.** The TXT record goes into the *public* zone as `_acme-challenge.<sub>`,
  but this host resolves through the internal DNS, which is authoritative for the
  internal zones. Left at the system resolver, lego's SOA walk stops at the
  internal zone, asks the internal server for the record, gets an authoritative
  NODATA and waits out the propagation timeout — no certificate, and an error
  that reads like a provider fault. `acme_client_dns_resolvers` is what prevents
  it; do not empty it. To confirm the setup, compare:

  ```bash
  dig @1.1.1.1 SOA _acme-challenge.int.example.com   # must be the public zone
  dig         SOA _acme-challenge.int.example.com   # will be the internal zone
  ```

  Do **not** reach for lego's `--dns.propagation-disable-ans` instead. It
  silences the check rather than fixing it, and then hides real propagation
  failures too.
- **The internal zones must stay undelegated in the public zone.** An `NS` record
  for one moves the challenge name into the child zone: the parent's nameservers
  stop serving it and the CA's own validators get NXDOMAIN, so validation breaks
  for everyone, not just locally. If a zone ever has to be delegated, put a
  public `_acme-challenge.<zone>` CNAME into a zone the API can still write —
  lego follows it.
- **`lego run` is not idempotent; `lego renew` is.** `run` issues a new
  certificate every time it is called and overwrites what is there. The renewal
  script picks between them, which is why it must not be bypassed. Never "just
  run it again" to debug: the limit is 5 per identical name set per 7 days, with
  no renewal exemption. Set `server:` on the entry to the staging endpoint
  instead.
- **A renewal is invisible until the consumers restart.** Docker bind-mounts a
  single file by inode, so a running container keeps reading the file it started
  with no matter what replaces the path. An empty `reload_commands` on a
  certificate that has consumers means silent expiry.
- **One key file per zone, so one group.** A zone read by gitea needs
  `key_group: "1000"` — gitea's container opens the mounted key as uid/gid 1000
  and crash-loops on a key it cannot read. A zone read only by a root container
  can stay `root`. If both consume the same zone on the same host, use the group
  they share.
- **Real files, not symlinks.** Consumer roles stat these paths without following
  links and require a regular file.
- **A trailing space in the vault token is a silent 401.** lego strips exactly
  one trailing newline and no other whitespace. Keep the vault value a plain
  quoted scalar; a YAML `>` block scalar appends its own newline.
- **The token is account-wide.** `dns:read` + `dns:write` covers every domain in
  the Infomaniak account — there is no per-zone scoping — and every host that
  declares a certificate holds a copy.
- **A wildcard covers one label only.** `*.lab.example.com` matches
  `host.lab.example.com` but not `host.dev.lab.example.com`, which needs its own
  entry in `domains`.
- **Never reorder `domains`, only append.** lego names the files it writes after
  the *first* domain, so inserting a name at the top renames the certificate on
  disk. The next run then finds nothing to renew and issues a fresh certificate
  instead — one of the five per week. Several wildcards in one certificate are
  fine; the first one just has to stay first.
- **A zone on five or more hosts sits permanently at the rate limit.** Hosts
  sharing a zone all issue on the same day at bring-up, so they share an expiry
  and then cross the renewal threshold together, forever — `RandomizedDelaySec`
  only spreads them within a day. Keep a zone to four hosts or fewer, or stagger
  `renew_days` per host (30, 34, 38, 42 …) so each renews in a different week.
- **Modes must be quoted.** `key_mode: 0640` unquoted is read as octal by YAML
  and arrives as `416`. The role asserts the format.
- **Old lego versions accumulate** under `/usr/local/lib/lego/`, about 70 MB
  each. Nothing prunes them on purpose: one of them is the running binary, and
  reverting `acme_client_lego_version` is how a bad release is rolled back.
- **`--tags certificate` is the only tag that talks to a CA.** The rest render
  configuration.
- **Egress matters, eventually.** TCP/443 to the ACME directory and
  `api.infomaniak.com`, and 53 to `acme_client_dns_resolvers`.
  `ufw_default_policy_outgoing` is `allow` today, so there is nothing to add —
  but tightening it would break renewals a month later rather than immediately.

## Key variables

| Variable | Default | Purpose |
|-------------------------------|-------------------------|-------------------------------------------------------|
| `acme_client_certificates` | `[]` | The certificates this host issues; see below |
| `acme_client_email` | `""` | ACME account contact; names the account directory |
| `acme_client_dns_api_token` | `""` | Infomaniak token, `dns:read` + `dns:write`; vault only |
| `acme_client_server` | Let's Encrypt production | ACME directory URL, overridable per certificate |
| `acme_client_dns_resolvers` | `1.1.1.1:53`, `8.8.8.8:53` | Resolvers for the DNS-01 pre-check; see the gotchas |
| `acme_client_renew_days` | `30` | Renew below this much remaining validity |
| `acme_client_deploy_dir_parent` | `/etc/ssl` | Certificates land in `<parent>/<zone>/` |
| `acme_client_default_key_group` | `root` | Fallback group for the private key |
| `acme_client_lego_version` | `5.3.1` | Pinned release; bump with the checksum |
| `acme_client_issue` | `true` | Obtain missing certificates during the converge |
| `acme_client_enable_timers` | `true` | Install and enable the renewal timers |

Per-entry keys of `acme_client_certificates` — only `zone` is required:

| Key | Default | Purpose |
|--------------------|-------------------------------|--------------------------------------------------|
| `zone` | — | Names the deploy dir, the systemd instance, the config |
| `domains` | `["*.<zone>", "<zone>"]` | SANs; wildcard first |
| `reload_commands` | `[]` | Run after the pair is replaced |
| `key_group` | `acme_client_default_key_group` | Group of the private key |
| `key_mode` | `"0640"` | Mode of the private key |
| `cert_owner`/`cert_group`/`cert_mode` | the `acme_client_default_cert_*` values | Ownership of the certificate |
| `key_owner` | `acme_client_default_key_owner` | Owner of the private key |
| `server` | `acme_client_server` | Per-certificate ACME directory, e.g. staging |
| `renew_days` | `acme_client_renew_days` | Per-certificate renewal threshold |
| `key_type` | `acme_client_key_type` | Per-certificate key algorithm |
| `deploy_dir` | `<parent>/<zone>` | Override the deploy directory entirely |

## Usage

```bash
ansible-playbook -i inventories/production/hosts playbooks/acme_client.yml
```

Run this before the roles that consume the certificates, since they assert the
files exist.

```yaml
# group_vars/acme_client/vars.yml
acme_client_email: "admin@example.com"
acme_client_dns_api_token: "{{ vault_acme_client_dns_api_token }}"

acme_client_certificates:
  - zone: "int.example.com"
    # gitea reads the mounted key as uid/gid 1000 and crash-loops otherwise
    key_group: "1000"
    reload_commands:
      - "docker compose -f /containers/gitea/compose.yaml restart gitea"
      - "docker compose -f /containers/vaultwarden/compose.yaml restart vaultwarden"

  # Everything but zone is optional
  - zone: "lan.example.com"

  # A wildcard covers one label, so a deeper name needs its own entry
  - zone: "lab.example.com"
    domains:
      - "*.lab.example.com"
      - "lab.example.com"
      - "*.dev.lab.example.com"
```

```yaml
# group_vars/acme_client/vault.yml (ansible-vault encrypted)
vault_acme_client_dns_api_token: "..."
```

### Putting a certificate on several hosts

There is no host list inside the variable — that is what inventory groups are
for. A certificate is issued on every host whose resolved
`acme_client_certificates` contains it, so the shape of the `group_vars` decides
the shape of the deployment:

```ini
[acme_client]
titan                  # all three get the certificates in
stargate               # group_vars/acme_client/vars.yml
labhost
```

For one certificate on one host, put the entry in `host_vars/<host>.yml`, or in
the `group_vars` of a group with a single member.

Note that Ansible **replaces** rather than merges a list across `group_vars` of
different precedence, so a host that needs the group's certificates *plus* one
more has to restate the whole list in its own more-specific vars file. That is
the one sharp edge of a flat list; the alternative, `hash_behaviour = merge`, is
a global setting with much worse consequences elsewhere.

### Adding a zone

1. Add an entry to `acme_client_certificates`.
2. Confirm the zone is not delegated in the public zone — see the gotchas.
3. Converge. The certificate is obtained and its timer installed.

Names under a new internal zone will not *resolve* internally until that zone
exists in the [powerdns](../powerdns/README.md) configuration. That is
independent of issuance, which happens entirely against the public zone.

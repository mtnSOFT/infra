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
  `/etc/ssl/<zone>/privkey.pem` — the paths `gitea_tls_cert_file` and
  `vaultwarden_tls_cert_file` already point at, so no consumer role or its
  inventory needs changing
- Runs the per-certificate `reload_commands` after, and only after, a pair is
  actually replaced
- Obtains anything missing during the converge too, so a fresh host has its
  certificates before a consumer role asserts they exist

It does *not* retire a certificate when its entry is removed — see the gotchas.

The API token itself is never a shell argument, a unit-file value or an
environment variable. It is rendered to a `0600` file, and only that file's
*path* is exported — as `INFOMANIAK_ACCESS_TOKEN_FILE`, by the renewal script
rather than by the systemd unit, so that lego is given it identically whether
the timer or an Ansible converge invoked the script.

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

  Do **not** reach for lego's `--dns.propagation.disable-ans` (or
  `--dns.propagation.disable-rns`, or `--dns.propagation.wait`) instead. They
  silence the check rather than fixing it, and then hide real propagation
  failures too.
- **The internal zones must stay undelegated in the public zone.** An `NS` record
  for one moves the challenge name into the child zone: the parent's nameservers
  stop serving it and the CA's own validators get NXDOMAIN, so validation breaks
  for everyone, not just locally. If a zone ever has to be delegated, put a
  public `_acme-challenge.<zone>` CNAME into a zone the API can still write —
  lego follows it.
- **lego logs to stdout, including its errors — its stderr stays empty.** When a
  renewal fails, the reason is in stdout; a tool that reports only stderr shows
  nothing. To see it by hand:
  ```bash
  /usr/local/bin/acme-client-renew.sh <zone> --now
  journalctl -u acme-client-renew@<zone> --no-pager -n 50   # timer runs
  ```
- **lego v5's flags are `run` flags, not global ones.** `lego --accept-tos … run`
  fails with `flag provided but not defined: -accept-tos`; everything goes
  *after* the command. The v4 `renew` command no longer exists — v5's `run` is
  "get or renew" and decides for itself whether the certificate is due
  (`--renew-days` sets the threshold, `--renew-force` overrides it). Older
  examples on the internet, and older versions of this role, get this wrong.
- **Debugging still costs certificates.** `run` skips a certificate that is not
  due, but `--renew-force` and a deleted state directory both cause a real
  issuance, and the limit is 5 per identical name set per 7 days with no renewal
  exemption. Point `acme_client_server` at the staging endpoint instead.
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
- **Editing `domains` reissues the certificate.** The role passes lego's
  `--cert.name` (so the files on disk are named after the zone, and reordering
  the list is harmless) together with `--force-cert-domains`, which makes lego
  compare the SANs on disk against `domains` and reissue when they differ.
  Without that flag an added domain would be silently ignored until the next
  natural renewal; with it, the edit costs one of the five issuances per week.
  Several wildcards in one certificate are fine.
- **Keep a zone to four hosts or fewer.** Hosts sharing a zone all issue on the
  same day at bring-up, so they share an expiry and then cross the 30-day
  renewal threshold together, forever — `RandomizedDelaySec` only spreads them
  within a day. At five hosts that is 5 issuances in one week, exactly the
  duplicate-certificate limit, and one retry blocks the whole group. If you ever
  need more, reintroduce a per-entry `renew_days` and stagger it (30, 34, 38 …)
  so each host renews in a different week.
- **Retiring a zone is manual.** Removing its entry from
  `acme_client_certificates` stops Ansible managing it but leaves the timer
  enabled, renewing forever against the rate limit:
  ```bash
  systemctl disable --now acme-client-renew@<zone>.timer
  rm /etc/acme-client/certs/<zone>.conf /etc/acme-client/reload.d/<zone>.sh
  ```
  The deployed files in `/etc/ssl/<zone>/` and lego's state are left alone —
  delete them yourself once nothing is serving them.
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

All of them, in full:

| Variable | Default | Purpose |
|-------------------------------|-------------------------|-------------------------------------------------------|
| `acme_client_certificates` | `[]` | The certificates this host issues; see below |
| `acme_client_email` | `""` | ACME account contact; names the account directory |
| `acme_client_dns_api_token` | `""` | Infomaniak token, `dns:read` + `dns:write`; vault only |
| `acme_client_server` | Let's Encrypt production | ACME directory URL; point at staging while debugging |
| `acme_client_dns_resolvers` | `1.1.1.1:53`, `8.8.8.8:53` | Resolvers for the DNS-01 pre-check; see the gotchas |
| `acme_client_lego_version` | `5.3.1` | Pinned release; bump with the checksum |
| `acme_client_lego_checksum` | sha256 of the tarball | Bump with the version |
| `acme_client_issue` | `true` | Obtain missing certificates during the converge |
| `acme_client_enable_timers` | `true` | Install and enable the renewal timers |

Everything else is fixed on purpose: certificates land in `/etc/ssl/<zone>/`,
state in `/var/lib/acme_client/<ca-host>/`, config in `/etc/acme-client/`, the
binary in `/usr/local/lib/lego/<version>/`. Keys are `ec256`, renewal is at 30
days remaining, the timer runs daily at 03:17 with a 3 h jitter, the certificate
is `root:root 0644` and the private key `root:<key_group> 0640`.

Per-entry keys of `acme_client_certificates` — only `zone` is required:

| Key | Default | Purpose |
|--------------------|-------------------------------|--------------------------------------------------|
| `zone` | — | Names the deploy dir, the systemd instance, the config |
| `domains` | `["*.<zone>", "<zone>"]` | SANs; the first one names the files on disk |
| `key_group` | `root` | Group of the private key; `"1000"` for a gitea host |
| `reload_commands` | `[]` | Run after the pair is replaced |

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
apphost                # all three get the certificates in
dnshost                # group_vars/acme_client/vars.yml
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

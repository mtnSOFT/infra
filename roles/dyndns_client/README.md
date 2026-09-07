# dyndns_client

Keeps one `A` record current at [Infomaniak](https://www.infomaniak.com/) by
polling their dyndns2 endpoint from a root cron job.

## What it does

- Installs `curl` and `cron`
- Renders `{{ dyndns_client_config_dir }}/curl.conf` (`0600 root:root`) with the
  basic-auth credential, and `/usr/local/bin/update-dyndns.sh` (`0700 root:root`)
  with everything else
- Runs the script once during the converge unless `dyndns_client_update` is
  `false`, so a wrong credential fails the play instead of a cron mail later
- Adds a root cron job on `dyndns_client_cron_minute` (default every 5 minutes)
- Appends one line per run to `dyndns_client_log_file` (default
  `/var/log/dyndns_update.log`), trimmed to its last 1000 lines
- Removes the netzone-era `Update netzone.ch DynDNS` cron entry on hosts that
  still carry it

## Gotchas

- **The credential is per Dynamic DNS entry, not an account login.** Create the
  entry and its ID/password pair in the Infomaniak manager under the domain's
  **Dynamic DNS** section.
- **Keep the ID and password alphanumeric.** Infomaniak recommends it, and it is
  also what keeps the pair safe in a basic-auth header with no escaping. The role
  does no URL- or shell-encoding of either.
- **The record has to exist first.** The endpoint updates a Dynamic DNS entry, it
  does not create one — an unknown name comes back as `nohost`, which the script
  reports as a failure.
- **`--ipv4` is load-bearing.** Infomaniak picks the record type from the protocol
  the request arrives over, so on a host with working IPv6 curl would silently
  update the `AAAA` record instead of the `A` record. This role is IPv4-only; an
  `AAAA` record needs a second call and is out of scope.
- **`myip` is deliberately not sent.** Infomaniak then uses the request's source
  address, which behind NAT is the public one the host is actually seen as. That
  is why nothing here has to ask an external service what that address is — and
  why the script cannot tell whether the address changed without asking.
- **288 requests a day is deliberate.** Following from the above, every cron tick
  is a real request; Infomaniak's documentation warns about abuse, so widen
  `dyndns_client_cron_minute` on a host whose address is stable.
- **The script exits non-zero on any failure**, which is what makes cron mail
  root. `badauth`, `nohost`, `notfqdn`, an unrecognised body and a curl failure
  all count; only `successfully_changed`/`no_change` and the legacy
  `good`/`nochg` are a success. Both go to the log either way.
- **The credential is not in the script.** It reaches curl through `--config`,
  because arguments are visible to any local user in `ps` output. Do not inline it
  back into the URL.
- `dyndns_client_update: false` renders everything but talks to no provider — that
  is what the molecule scenario runs on.

## Key variables

- `dyndns_client_hostname` — FQDN whose `A` record is updated; must match an
  existing Infomaniak Dynamic DNS entry (default empty, required)
- `dyndns_client_username` — ID of that Dynamic DNS entry (default empty,
  required)
- `dyndns_client_password` — its password, from vault (default empty, required)
- `dyndns_client_update` — run the update once during the converge (default
  `true`; `false` in the molecule scenario)
- `dyndns_client_cron_minute` — minute field of the cron job (default `*/5`)
- `dyndns_client_update_url` — dyndns2 endpoint (default
  `https://infomaniak.com/nic/update`)
- `dyndns_client_config_dir` — holds `curl.conf` (default `/etc/dyndns-client`)
- `dyndns_client_log_file` — one line per run (default
  `/var/log/dyndns_update.log`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/dyndns_clients.yml`

Targets the `dyndns_clients` group. Configure it in `group_vars/dyndns_clients/`:

```yaml
# vars.yml
dyndns_client_hostname: "dyn.example.com"
dyndns_client_username: "dyndnsexample"
dyndns_client_password: "{{ vault_dyndns_client_password }}"

# vault.yml (ansible-vault)
vault_dyndns_client_password: "..."
```

To check a host by hand:

```bash
/usr/local/bin/update-dyndns.sh; echo "exit=$?"
tail -1 /var/log/dyndns_update.log
```

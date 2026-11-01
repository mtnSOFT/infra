# gatus

[Gatus](https://github.com/TwiN/gatus) health/status dashboard as a Docker
Compose stack. Needs the [docker-compose](../docker-compose/README.md) role first.

## What it does

- Renders the compose project into `{{ gatus_dir }}` (default `/containers/gatus`)
  and brings it up with `community.docker.docker_compose_v2`
- **Watches every inventory host automatically**: each host in `groups['all']`
  gets a `<host> ping` (ICMP) and a `<host> ssh` (TCP connect to `sshd_port`, else
  22) check in the `Hosts` group. A host is addressed by `ansible_host`, else
  `<host>.<internal_zone_name>`, else its inventory name
- Hosts outside the inventory get the same checks via `gatus_extra_hosts`
- Any other service (HTTP(S), TCP, UDP, DNS, TLS, STARTTLS, …) via
  `gatus_endpoints`, in Gatus' own endpoint syntax
- **Certificates**: Gatus fails an `https://` check whose chain or hostname does
  not verify. On top, every `https://`, `tls://` and `starttls://` endpoint gets
  `[CERTIFICATE_EXPIRATION] > 336h` unless it already has an expiration condition
- Results are kept in SQLite under `data/`; `/metrics` is exposed for Prometheus
- Config changes need no restart: Gatus reloads `config/config.yaml` on its own

## Gotchas

- **Published ports bypass UFW.** Docker publishes via DNAT, so a
  `ufw_group_rules` entry will *not* restrict the dashboard — `gatus_bind_ip` is
  the access control. Default `127.0.0.1`. There is no reverse proxy or TLS.
- Checks run from inside the container: internal DNS names (the
  `<host>.<internal_zone_name>` fallback) must resolve via the host's resolver,
  and the gatus host must be able to route to every checked address.
- ICMP needs `NET_RAW`, which Docker grants by default; the image runs as root.
- Hosts that block ping or have no SSH: set the host var `gatus_ping: false` /
  `gatus_ssh: false` on them.
- `gatus_endpoint_defaults` is a shallow merge: an endpoint's own `alerts` list
  replaces the default one.
- Alerts need both an `alerting` provider and an `alerts:` entry on the endpoint
  — `gatus_host_alerts` covers the generated host checks.

## Key variables

- `gatus_dir` — compose project directory (default `/containers/gatus`)
- `gatus_deploy` — bring the stack up (default `true`; the molecule scenario sets
  it `false` to render config only)
- `gatus_image` / `gatus_version_tag` — image and tag (default `latest`; pin it)
- `gatus_bind_ip` / `gatus_port` — published UI address (`127.0.0.1`, `8080`)
- `gatus_metrics` — expose `/metrics` (default `true`)
- `gatus_ui` — Gatus' `ui:` block (default `{title: Status}`)
- `gatus_inventory_hosts` — generate checks for inventory hosts (default `true`)
- `gatus_inventory_hosts_exclude` — inventory hosts to skip; or set the host var
  `gatus_monitor: false`
- `gatus_host_ping` / `gatus_host_ssh` — which host checks to generate (both
  `true`); per host via the host vars `gatus_ping` / `gatus_ssh`
- `gatus_host_group` / `gatus_host_interval` — group and cadence of host checks
  (`Hosts`, `1m`)
- `gatus_host_alerts` — alerts attached to every host check (default none)
- `gatus_extra_hosts` — `{name, address, ssh_port?, ping?, ssh?}` entries
- `gatus_endpoints` — Gatus endpoint definitions; the only extra key is
  `certificate_check: false`, which skips the expiry condition
- `gatus_endpoint_defaults` — keys merged under every `gatus_endpoints` entry
- `gatus_certificate_expiration_min` — minimum remaining certificate lifetime
  (default `336h` = 14 days; `""` disables the automatic condition)
- `gatus_alerting` — Gatus' `alerting:` block (secrets from vault; the config is
  rendered `0600`)
- `timezone` — container timezone (default `UTC`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/gatus.yml`

Targets the `gatus` group. Example `group_vars/gatus/vars.yml`:

```yaml
gatus_bind_ip: "10.10.0.1"            # e.g. the wg0 address: VPN-only dashboard
gatus_version_tag: "v5"

gatus_inventory_hosts_exclude: [labhost]
gatus_extra_hosts:
  - name: router
    address: 192.0.2.1
    ssh: false

gatus_endpoint_defaults:
  interval: 2m
  alerts:
    - type: ntfy

gatus_endpoints:
  # HTTP status + response time; chain/hostname verified, expiry > 14d added
  - name: website
    group: Services
    url: "https://example.com"
    conditions:
      - "[STATUS] == 200"
      - "[RESPONSE_TIME] < 1000"

  # Certificate-only check on any TLS port, with a stricter expiry
  - name: mail certificate
    group: Certificates
    url: "starttls://mail.example.com:587"
    interval: 1h
    conditions:
      - "[CONNECTED] == true"
      - "[CERTIFICATE_EXPIRATION] > 720h"

  # Internal service with a self-signed certificate
  - name: router ui
    group: Services
    url: "https://192.0.2.1"
    certificate_check: false
    client:
      insecure: true
    conditions: ["[STATUS] == 200"]

  # Plain TCP port
  - name: postgres
    group: Services
    url: "tcp://dbhost.int.example.com:5432"
    conditions: ["[CONNECTED] == true"]

  # DNS resolver answers
  - name: resolver
    group: Services
    url: "192.0.2.53"
    dns:
      query-name: "example.com"
      query-type: "A"
    conditions: ["[DNS_RCODE] == NOERROR"]

gatus_host_alerts:
  - type: ntfy

gatus_alerting:
  ntfy:
    url: "https://ntfy.example.com"
    topic: "infra"
    token: "{{ vault_gatus_ntfy_token }}"
    default-alert:
      failure-threshold: 3
      send-on-resolved: true
```

To graph the results, scrape Gatus from the [monitoring](../monitoring/README.md)
stack (bind Gatus to an address Prometheus can reach):

```yaml
monitoring_prometheus_extra_scrape_configs:
  - job_name: gatus
    static_configs:
      - targets: ["10.10.0.1:8080"]
```

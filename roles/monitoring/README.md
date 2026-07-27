# monitoring

Runs [Prometheus](https://prometheus.io/), [Grafana](https://grafana.com/) and
[Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) as a
single Docker Compose stack. Requires the
[docker-compose](../docker-compose/README.md) role to have installed Docker
Engine and the Compose plugin first.

## What it does

- Creates the compose project under `{{ monitoring_dir }}` (default `/containers/monitoring`)
- Renders `prometheus.yml`, `alertmanager.yml`, the Grafana provisioning files,
  `.env` (Grafana admin password, `0600`) and `compose.yaml`
- Copies any dashboard JSON from the role's `files/dashboards/` to the host
- Brings the stack up with `docker compose` (via `community.docker.docker_compose_v2`)
- Restarts the affected service when its config file changes

The three services share the compose project's default **bridge network** and
address each other by service name — Grafana's provisioned datasource points at
`http://prometheus:9090` and Prometheus sends alerts to `alertmanager:9093`. The
Prometheus datasource is provisioned declaratively, so there is nothing to click
in the Grafana UI.

Persistent data lives in bind mounts under the project directory:
`prometheus/data` (TSDB), `alertmanager/data` (silences, notification log) and
`grafana/data` (Grafana's sqlite DB). These are chowned to the UID/GID the
upstream images run as (`472:0` for Grafana, which runs in the root group like
its own image expects; `65534:65534` for the two Prometheus images), and the
same values are pinned as `user:` on the compose services so the two cannot
drift apart. Config files are mounted read-only.

### Exposure

Published ports are bound to an explicit host IP, never the wildcard. This
matters: Docker publishes ports via DNAT, which **bypasses UFW's INPUT chain**,
so a `ufw_group_rules` entry will *not* restrict Grafana — the bind address is
the access control.

Keep Prometheus and Alertmanager on `127.0.0.1` (the default) and set
`monitoring_grafana_bind_ip` to an internal address, e.g. the host's WireGuard
address, to make the UI reachable over the VPN only:

```yaml
monitoring_grafana_bind_ip: "10.10.0.1"
```

This is the same reachability model the [pihole](../pihole/README.md) role uses
for its web admin, arrived at by a different mechanism (pihole uses host
networking, so its ports really are UFW-governed INPUT traffic).

There is no reverse proxy or TLS in front of the stack — nothing in this repo
terminates TLS on a host today, so Grafana is served over plain HTTP on the
address you bind it to.

### Alerting

Alertmanager ships with a single receiver named `default` that has no
notification config, which is valid and silently drops alerts. Define a real
receiver once you have picked a channel, for example in `group_vars/monitoring`:

```yaml
monitoring_alertmanager_global:
  resolve_timeout: "5m"
  smtp_smarthost: "smtp.example.com:587"
  smtp_from: "alertmanager@example.com"
  smtp_auth_username: "alertmanager"
  smtp_auth_password: "{{ vault_monitoring_smtp_password }}"

monitoring_alertmanager_default_receiver: "ops-email"
monitoring_alertmanager_receivers:
  - name: "ops-email"
    email_configs:
      - to: "ops@example.com"
```

Alertmanager does not expand environment variables in its config, so receiver
secrets are rendered inline into `alertmanager.yml`. That file is `0640`
`root:65534` — readable by root and the container UID only, never
world-readable. Put the values in vault.

Prometheus alert rules are wired up (`rule_files: /etc/prometheus/rules/*.yml`)
but ship empty — drop rule files into `{{ monitoring_dir }}/prometheus/rules`.

### Dashboards

The dashboard provider polls `/etc/grafana/dashboards` every 30s. To manage a
dashboard in git, export its JSON and commit it to
`roles/monitoring/files/dashboards/`; the role copies every `*.json` there to
the host. UI edits are not persisted (`allowUiUpdates: false`).

### Exporters

Exporters on the monitored nodes are not part of this role yet. Prometheus
scrapes only itself out of the box. Add scrape jobs through
`monitoring_prometheus_extra_scrape_configs`, which is appended verbatim to
`scrape_configs`:

```yaml
monitoring_prometheus_extra_scrape_configs:
  - job_name: node
    static_configs:
      - targets: ["10.0.0.10:9100", "10.0.0.11:9100"]
```

## Key variables

- `monitoring_grafana_admin_password` — Grafana admin password (put it in vault;
  intentionally has no default)
- `monitoring_dir` — compose project directory (default `/containers/monitoring`)
- `monitoring_deploy` — bring the stack up and restart on config change
  (default `true`; the molecule scenario sets it `false` to render config only)
- `monitoring_bind_ip` — host IP Prometheus and Alertmanager bind to
  (default `127.0.0.1`)
- `monitoring_grafana_bind_ip` — host IP Grafana binds to (defaults to
  `monitoring_bind_ip`)
- `monitoring_prometheus_port` / `monitoring_grafana_port` /
  `monitoring_alertmanager_port` — published host ports (default `9090`, `3000`, `9093`)
- `monitoring_prometheus_retention` — TSDB retention (default `30d`)
- `monitoring_prometheus_scrape_interval` — default scrape cadence (default `30s`)
- `monitoring_prometheus_external_labels` — labels added to every series and alert
- `monitoring_prometheus_extra_scrape_configs` — extra scrape jobs, appended to
  `scrape_configs`
- `monitoring_alertmanager_global` — rendered as Alertmanager's `global:` block
  (SMTP / Slack credentials go here, from vault)
- `monitoring_alertmanager_receivers` / `monitoring_alertmanager_default_receiver`
  / `monitoring_alertmanager_routes` / `monitoring_alertmanager_inhibit_rules`
- `monitoring_grafana_admin_user` — Grafana admin login (default `admin`)
- `monitoring_grafana_root_url` — Grafana's external URL
- `monitoring_*_image` / `monitoring_*_version_tag` — image and tag per service
  (default `latest`; pin these in inventory)
- `monitoring_grafana_uid` / `monitoring_grafana_gid` /
  `monitoring_nobody_uid` / `monitoring_nobody_gid` — UID/GID the containers run
  as and the data dirs are chowned to (defaults `472`/`0` and `65534`/`65534`)
- `timezone` — container timezone (default `UTC`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/monitoring.yml`

Targets the `monitoring` group, which needs to exist in the inventory:

```ini
[monitoring]
monitor-1
```

The Grafana password is not defined in the test inventory (same as
`pihole_password`). For production, add it to the group's vault:

```
ansible-vault create inventories/production/group_vars/monitoring/vault.yml
```

```yaml
# vault.yml
vault_monitoring_grafana_admin_password: "..."
```

```yaml
# vars.yml
monitoring_grafana_admin_password: "{{ vault_monitoring_grafana_admin_password }}"
```

Changing `monitoring_grafana_admin_password` after the first run does **not**
reset the password: Grafana only reads `GF_SECURITY_ADMIN_PASSWORD` when it
initialises its database. Reset it with
`docker exec -it grafana grafana cli admin reset-admin-password '<new>'`.

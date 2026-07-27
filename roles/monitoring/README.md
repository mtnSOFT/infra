# monitoring

Prometheus, Grafana and Alertmanager as one Docker Compose stack. Needs the
[docker-compose](../docker-compose/README.md) role first.

## What it does

- Renders the compose project into `{{ monitoring_dir }}` (default
  `/containers/monitoring`) and brings it up with `community.docker.docker_compose_v2`
- The services share the compose bridge network, so Grafana's provisioned
  datasource points at `http://prometheus:9090` and Prometheus alerts to
  `alertmanager:9093` — nothing to click in the Grafana UI
- Data lives in bind mounts (`prometheus/data`, `alertmanager/data`,
  `grafana/data`) chowned to the UIDs the images run as; config is mounted `:ro`
- Restarts a service when its config file changes

## Gotchas

- **Published ports bypass UFW.** Docker publishes via DNAT, so a
  `ufw_group_rules` entry will *not* restrict Grafana — `monitoring_bind_ip` /
  `monitoring_grafana_bind_ip` is the access control. Default `127.0.0.1`. There
  is no reverse proxy or TLS.
- **Alerts are dropped by default.** The `default` receiver has no notification
  config. Set `monitoring_alertmanager_receivers`, secrets in vault —
  `alertmanager.yml` is rendered `0640` because Alertmanager cannot read env vars.
- **Password changes do not apply.** Grafana reads `GF_SECURITY_ADMIN_PASSWORD`
  only when initialising its DB. Reset with `docker compose -f
  {{ monitoring_dir }}/compose.yaml exec grafana grafana cli admin
  reset-admin-password '<new>'`.
- Containers are named by compose (`monitoring-grafana-1`, …), so address them
  with `docker compose exec <service>` rather than a fixed container name.
- **Job names must be unique.** Hosts in the `monitored` group are scraped by a
  derived job called `node`, so don't reuse that name in
  `monitoring_prometheus_extra_scrape_configs` — Prometheus refuses to start on a
  duplicate `job_name`.
- Alert rules are wired up (`/etc/prometheus/rules/*.yml`) but ship empty.
- Dashboards: commit JSON to `files/dashboards/`; UI edits are not persisted
  (`allowUiUpdates: false`). Ships **Node Exporter Full**
  ([grafana.com/dashboards/1860](https://grafana.com/grafana/dashboards/1860),
  revision 45), vendored byte-identical to upstream so a newer revision diffs
  cleanly. Refresh it with
  `curl -o roles/monitoring/files/dashboards/node-exporter-full.json https://grafana.com/api/dashboards/1860/revisions/<n>/download`.
- A few 1860 panels need collectors that are off by default — add
  `--collector.systemd` / `--collector.processes` to `node_exporter_extra_args`
  if you want them, otherwise those panels read "No data".
- Exporters are not included yet — add scrape jobs via
  `monitoring_prometheus_extra_scrape_configs`.

## Key variables

- `monitoring_grafana_admin_password` — Grafana admin password (vault; no default)
- `monitoring_dir` — compose project directory (default `/containers/monitoring`)
- `monitoring_deploy` — bring the stack up and restart on config change
  (default `true`; the molecule scenario sets it `false` to render config only)
- `monitoring_bind_ip` — host IP Prometheus and Alertmanager bind to
  (default `127.0.0.1`)
- `monitoring_grafana_bind_ip` — host IP Grafana binds to (defaults to
  `monitoring_bind_ip`)
- `monitoring_prometheus_port` / `monitoring_grafana_port` /
  `monitoring_alertmanager_port` — published host ports (`9090`, `3000`, `9093`)
- `monitoring_prometheus_retention` — TSDB retention (default `30d`)
- `monitoring_prometheus_scrape_interval` — scrape cadence (default `30s`)
- `monitoring_prometheus_external_labels` — labels added to every series and alert
- `monitoring_node_group` — inventory group scraped as node exporters
  (default `monitored`; see [node_exporter](../node_exporter/README.md))
- `monitoring_node_exporter_port` — port for those targets (default `9100`)
- `monitoring_prometheus_extra_scrape_configs` — extra scrape jobs, appended to
  `scrape_configs`
- `monitoring_alertmanager_global` — Alertmanager's `global:` block (SMTP / Slack
  credentials go here, from vault)
- `monitoring_alertmanager_receivers` / `monitoring_alertmanager_default_receiver`
  / `monitoring_alertmanager_routes` / `monitoring_alertmanager_inhibit_rules`
- `monitoring_grafana_admin_user` — Grafana admin login (default `admin`)
- `monitoring_grafana_root_url` — Grafana's external URL
- `monitoring_*_image` / `monitoring_*_version_tag` — image and tag per service
  (default `latest`; pin these in inventory)
- `monitoring_grafana_uid` / `monitoring_grafana_gid` / `monitoring_nobody_uid` /
  `monitoring_nobody_gid` — UID/GID the containers run as and the data dirs are
  chowned to (defaults `472`/`0` and `65534`/`65534`)
- `timezone` — container timezone (default `UTC`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/monitoring.yml`

Targets the `monitoring` group. Set the password in `group_vars/monitoring/`:

```yaml
# vars.yml
monitoring_grafana_admin_password: "{{ vault_monitoring_grafana_admin_password }}"

# vault.yml (ansible-vault)
vault_monitoring_grafana_admin_password: "..."
```

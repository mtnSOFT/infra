# node_exporter

Installs the Prometheus [node exporter](https://github.com/prometheus/node_exporter)
on hosts that should be scraped by the [monitoring](../monitoring/README.md) stack.

## What it does

- Installs the `prometheus-node-exporter` apt package, which ships the systemd
  unit and a `prometheus` service user, and is patched by the
  unattended-upgrades that [linux_base](../linux_base/README.md) enables
- Writes `ARGS` into `/etc/default/prometheus-node-exporter` (the packaged unit is
  `ExecStart=/usr/bin/prometheus-node-exporter $ARGS`), so the unit itself is
  never modified
- Enables and starts the service, restarting it when the arguments change

Metrics are served on `:{{ node_exporter_port }}/metrics`.

## Enrolling a host

1. Add it to `[monitored]` in the inventory
2. `ansible-playbook -i inventories/production/hosts playbooks/node_exporter.yml`
3. Re-run `playbooks/monitoring.yml` — the monitoring role derives its scrape
   targets from this group, so no target list needs editing

## Firewall

This is a plain systemd service, so UFW **does** govern it (unlike the monitoring
stack's docker-published ports, which are DNAT'd past the INPUT chain). Allow the
monitoring host in `group_vars/monitored/vars.yml`:

```yaml
ufw_group_rules:
  - rule: allow
    port: 9100
    proto: tcp
    from_ip: "<monitoring host IP>"
    comment: "node exporter scrape"
```

`ufw_group_rules` is a flat list and Ansible does not merge it across groups — if
a host is in two groups that both define it, only one applies. Keep it in one
group per host, or use `ufw_host_rules`.

## Key variables

- `node_exporter_port` — listen port (default `9100`)
- `node_exporter_bind_ip` — address to bind; empty (default) = all interfaces, or
  an internal IP to keep the exporter off public interfaces
- `node_exporter_extra_args` — extra flags, e.g. `["--collector.systemd"]`
- `node_exporter_address` — per-host override for the address Prometheus scrapes
  (set in host_vars; defaults to `ansible_host`, then `inventory_hostname`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/node_exporter.yml`

# dyndns_client

Keeps a dynamic DNS record up to date from the host.

## What it does

- Installs `curl`
- Deploys `/usr/local/bin/update-dyndns.sh` (from template)
- Adds a root cron job running the script every 5 minutes
- Logs results to `/var/log/dyndns_update.log` (trimmed to last 1000 lines)

## Key variables

- `dyndns_server` — DynDNS update URL
- `dyndns_hostname` — hostname to update
- `dyndns_username` / `dyndns_password` — credentials

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/dyndns_clients.yml`

Targets the `dyndns_clients` inventory group.

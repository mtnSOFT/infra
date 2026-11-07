# netplan

Deploys per-host netplan network configuration.

## What it does

- Installs `netplan.io`
- Copies all `*.yaml` configs from `inventories/<env>/netplan_configs/<hostname>/` to `/etc/netplan`
- Removes the default `00-installer-config.yaml` and `50-cloud-init.yaml` when custom configs exist (unless the host ships a file with the same name)
- Validates with `netplan try` then runs `netplan apply`

## Tasks

- `1_install` — install netplan
- `2_config` — deploy and apply configs

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/netplan.yml`

Place a host's network config in `inventories/<env>/netplan_configs/<hostname>/*.yaml`.

# Ansible Infrastructure Repository

🚀✨🙌💡🔥🌟🎉🥇👏

this is my ansible repo for managing infrastructure and deployments including:

- linux system config
- k3s cluster setup
- postgresql server
- all other deployments are managed with argocd for deployment on k3s

directory structure:

- **inventories** holds different environment inventories (e.g., production, staging)
- **roles** contains reusable Ansible roles for various services and configurations
- **playbooks** contains playbooks for deploying and managing services

## Roles

| Role | Description |
| --- | --- |
| [docker-compose](roles/docker-compose/README.md) | Docker Engine + Compose plugin from the official apt repo |
| [dyndns_client](roles/dyndns_client/README.md) | Keeps a dynamic DNS record up to date via cron |
| [k3s](roles/k3s/README.md) | k3s Kubernetes cluster with cert-manager + ArgoCD |
| [linux_base](roles/linux_base/README.md) | Base configuration applied to every host |
| [linux_bootstrap](roles/linux_bootstrap/README.md) | First run against a fresh cloud-init host |
| [linux_router](roles/linux_router/README.md) | Turns a host into a router/gateway |
| [netplan](roles/netplan/README.md) | Deploys per-host netplan network config |
| [pihole](roles/pihole/README.md) | Pi-hole DNS sinkhole / ad blocker |
| [postgresql](roles/postgresql/README.md) | PostgreSQL 17 server |
| [powerdns](roles/powerdns/README.md) | Authoritative PowerDNS server + Recursor (resolves outside the local zone) |
| [ufw](roles/ufw/README.md) | UFW firewall: policies, rules and WireGuard NAT |
| [wireguard](roles/wireguard/README.md) | WireGuard VPN server + client config generation |

## Getting Started

- start mtn-shell (see github.com/mtnstar/mtn-shell)
- clone this repository
- `ansible-galaxy role install -r requirements.yml -p ./.galaxy/roles`
- copy test inventory directory and customize it (e.g. ./inventories/test -> ./inventories/production)
- add desired public ssh keys to `inventories/production/ssh_keys/*.pub`

## Bootstrap a new ubuntu system

after bootstrapping new ubuntu system with cloud-init:

1. add new host to inventory (e.g. `inventories/production/hosts`)
2. specify ansible_user and ansible_port if needed
3. run `ansible-playbook -i inventories/production/hosts playbooks/linux_bootstrap.yml -l mynewhost`
4. remove ansible_user in inventory hosts
5. apply linux_base playbook to set up basic linux configuration and users: `ansible-playbook -i inventories/production/hosts playbooks/linux_base.yml -l mynewhost`
6. remove ansible_port if you specified it in inventory hosts

## Role Task Layout

Each role splits its tasks into ordered files (`1_*.yml`, `2_*.yml`, …) imported from `tasks/main.yml`, and every file carries a tag named after it. Run a subset of a role with `--tags`, e.g.:

`ansible-playbook -i inventories/production/hosts playbooks/linux_base.yml --tags user`

To run a single task file of a role on its own, use `tasks_from`, e.g. `linux_update.yml` runs `linux_base`'s `update.yml`.

## Running molecule tests

inside mtn-shell in this repo run `molecule test -s linux_base`

see [Molecule Testing](molecule/README.md) for more details on how to run molecule tests.

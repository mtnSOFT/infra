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

| Role                                             | Description                                                                |
|--------------------------------------------------|----------------------------------------------------------------------------|
| [docker-compose](roles/docker-compose/README.md) | Docker Engine + Compose plugin from the official apt repo                  |
| [dyndns_client](roles/dyndns_client/README.md)   | Keeps a dynamic DNS record up to date via cron                             |
| [k3s](roles/k3s/README.md)                       | k3s Kubernetes cluster with cert-manager + ArgoCD                          |
| [linux_base](roles/linux_base/README.md)         | Base configuration + first-run bootstrap for every host                    |
| [linux_router](roles/linux_router/README.md)     | Turns a host into a router/gateway                                         |
| [monitoring](roles/monitoring/README.md)         | Prometheus + Grafana + Alertmanager as a Docker Compose stack              |
| [netplan](roles/netplan/README.md)               | Deploys per-host netplan network config                                    |
| [pihole](roles/pihole/README.md)                 | Pi-hole DNS sinkhole / ad blocker                                          |
| [postgresql](roles/postgresql/README.md)         | PostgreSQL 17 server                                                       |
| [powerdns](roles/powerdns/README.md)             | Authoritative PowerDNS server + Recursor (resolves outside the local zone) |
| [ufw](roles/ufw/README.md)                       | UFW firewall: policies, rules and WireGuard NAT                            |
| [wireguard](roles/wireguard/README.md)           | WireGuard VPN server + client config generation                            |

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
3. run the bootstrap tasks as the temporary user: `ansible-playbook -i inventories/production/hosts playbooks/linux_base.yml --tags bootstrap -l mynewhost`
4. remove ansible_user in inventory hosts
5. apply the full linux_base playbook to finish basic configuration and remove the bootstrap user: `ansible-playbook -i inventories/production/hosts playbooks/linux_base.yml -l mynewhost`
6. remove ansible_port if you specified it in inventory hosts

## Role Task Layout

Each role splits its tasks into ordered files (`1_*.yml`, `2_*.yml`, …) imported from `tasks/main.yml`, and every file carries a tag named after it. Run a subset of a role with `--tags`, e.g.:

`ansible-playbook -i inventories/production/hosts playbooks/linux_base.yml --tags sshd`

To run a single task file of a role on its own, use `tasks_from`, e.g. `linux_update.yml` runs `linux_base`'s `update.yml`.

## Running molecule tests

inside mtn-shell in this repo run `molecule test -s linux_base`

see [Molecule Testing](molecule/README.md) for more details on how to run molecule tests.

## Dependency updates

[Renovate](https://docs.renovatebot.com/) opens pull requests for the versions pinned in this
repository, configured in [renovate.json](renovate.json). It runs weekly, early Monday morning.

- **CI-only updates automerge** once checks pass: GitHub Actions, the test Dockerfile, and the
  molecule platform images. These cannot affect a production host.
- **Anything deployed is reviewed by hand.** Updates to `requirements.yml` or to a version in
  `roles/**` are labelled `deployed-version` and never automerged.
- **Ubuntu major and minor bumps are disabled** on purpose. The fleet targets 24.04 LTS, and
  moving it is a project rather than a pull request.
- Grouped: Prometheus and Alertmanager move together. k3s patch and minor updates are
  separated, because a k3s minor is a Kubernetes minor and those must be applied one at a
  time.

### Adding a new pinned version

Renovate finds versions in Ansible variables through `# renovate:` annotation comments, so two
rules apply when you pin something new:

1. Put a `# renovate: datasource=… depName=…` comment on the line directly above the variable.
2. Name the variable `*_version` or `*_version_tag`, or the manager will not match it.

For example, in a role's `defaults/main.yml`:

```yaml
some_image: "vendor/thing"
# renovate: datasource=docker depName=vendor/thing
some_version_tag: "1.2.3"
```

A malformed or missing annotation **fails silently** — the dependency simply never appears.
After adding one, confirm Renovate sees it:

```sh
npx --yes renovate --platform=local --dry-run=extract
```

Commit or at least `git add` your change first. This reads the file list from git, so an
untracked file is invisible to it — including `renovate.json` itself, which is reported as "No
renovate config file found" and makes every custom manager silently do nothing. To check a
config that is not committed yet, pass it explicitly:

```sh
RENOVATE_CONFIG_FILE=$PWD/renovate.json npx --yes renovate --platform=local --dry-run=extract
```

Pin tags in role defaults rather than in inventory: `inventories/production` lives outside this
repository, so a version pinned there is invisible to Renovate.

### What Renovate does not cover

- PostgreSQL — the major version is part of the apt package names (`postgresql-17`)
- PowerDNS Recursor — the repo channel is chosen by variable _name_
  (`pdns_rec_powerdns_repo_54`)
- `runs-on: ubuntu-latest` — Renovate does read runner labels, but `latest` gives it no version
  to compare against. Pinning them to a release (`ubuntu-24.04`) would make them updatable
- Unpinned apt and pip packages, which install whatever the repo currently serves
- ansible-core, molecule and ansible-lint — these live in the `mtn-shell` image, not here

### Checking what is actually installed

`playbooks/report_versions.yml` reports the versions running on the hosts, which is how you
verify a pin matches reality before applying it, and how you spot drift afterwards. It only
reads, and needs `ANSIBLE_NO_LOG=false` because `ansible.cfg` defaults `no_log` to true:

```sh
ANSIBLE_NO_LOG=false ansible-playbook -i inventories/production playbooks/report_versions.yml
```

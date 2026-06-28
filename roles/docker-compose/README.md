# docker-compose

Installs Docker Engine and the Compose plugin from Docker's official apt repository.

## What it does

- Installs `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin` and `docker-compose-plugin`
- Writes `/etc/docker/daemon.json` (nftables backend, json-file log rotation: 10m × 5 files)
- Creates `/containers` for compose stacks
- Enables and starts the docker service

## Key variables

- `arch` — CPU arch used in the apt repo line (e.g. `amd64`, `arm64`)

## Usage

Add the role to a play for hosts that should run Docker workloads.

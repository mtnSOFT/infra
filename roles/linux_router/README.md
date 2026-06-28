# linux_router

Turns a host into a Linux router/gateway.

## What it does

- Installs `nftables` and `ufw`
- Enables and starts the `nftables` service
- Enables IPv4 forwarding (`net.ipv4.ip_forward=1`)

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/linux_router.yml`

Targets `linux_routers`. The playbook combines this role with [netplan](../netplan/README.md),
[pihole](../pihole/README.md), [wireguard](../wireguard/README.md) and [ufw](../ufw/README.md)
to build a full router (DNS + VPN + firewall).

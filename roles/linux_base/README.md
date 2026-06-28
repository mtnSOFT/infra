# linux_base

Base configuration applied to every managed host.

## What it does

- Updates the apt cache
- Installs base packages (netplan, curl, vim, python3-pip, net-tools, ssh, cron, dnsutils, ufw)
- Enables `unattended-upgrades` for automatic security updates
- Removes the temporary bootstrap user
- Hardens SSH: disables password auth, disables root login, sets the SSH port, locks the root password
- Sets the timezone and (optionally) disables IPv6
- Installs an Ansible-managed MOTD

## Key variables

- `sshd_port` — SSH port (default `22`)
- `disable_ipv6` — disable IPv6 via sysctl (default `true`)
- `timezone` — system timezone
- `bootstrap_user` — bootstrap user removed after base setup
- `motd_message_url` — link shown in the MOTD

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/linux_base.yml`

To only run apt upgrades (with reboot if required) use the `update` tasks:

`ansible-playbook -i inventories/production/hosts playbooks/linux_update.yml`

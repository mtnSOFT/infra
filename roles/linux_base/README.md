# linux_base

Base configuration applied to every managed host, including the first-run
bootstrap of a fresh cloud-init host.

## What it does

Bootstrap tasks (tag `bootstrap`, run once against a fresh host):

- Sets the hostname from `inventory_hostname`
- Sets the host FQDN in `/etc/hosts` from `local_zone_name` (when defined)
- Removes the `cloud-init` package (keeps `netplan.io`)
- Creates the infra admin user (uid 4242, sudo, passwordless sudo)
- Installs the SSH public keys from `inventories/<env>/ssh_keys/*.pub` into `authorized_keys`

Base tasks (run on every host):

- Updates the apt cache
- Installs base packages (netplan, curl, vim, python3-pip, net-tools, ssh, cron, dnsutils, ufw)
- Enables `unattended-upgrades` for automatic security updates
- Removes the temporary bootstrap user
- Hardens SSH: disables password auth, disables root login, sets the SSH port, locks the root password
- Sets the timezone and (optionally) disables IPv6
- Installs an Ansible-managed MOTD

## Key variables

- `infra_admin_username` — admin user created during bootstrap
- `infra_admin_password_hash` — hashed password for that user
- `local_zone_name` — local DNS domain; when set, the host FQDN (`<hostname>.<local_zone_name>`) is written to `/etc/hosts`
- `sshd_port` — SSH port (default `22`)
- `disable_ipv6` — disable IPv6 via sysctl (default `true`)
- `timezone` — system timezone
- `bootstrap_user` — bootstrap user removed after base setup
- `motd_message_url` — link shown in the MOTD
- `linux_base_bootstrap` — run the bootstrap tasks (default `true`; set `false` to skip them)

## Usage

Against a freshly bootstrapped host, first run only the bootstrap tasks using
the temporary bootstrap user/port:

`ansible-playbook -i inventories/production/hosts playbooks/linux_base.yml --tags bootstrap --limit=my-new-host -e ansible_user=default-bootstrap -e ansible_port=22`

Then reconnect as the infra admin user and apply the full role (which also
removes the bootstrap user):

`ansible-playbook -i inventories/production/hosts playbooks/linux_base.yml`

To only run apt upgrades (with reboot if required) use the `update` tasks:

`ansible-playbook -i inventories/production/hosts playbooks/linux_update.yml`

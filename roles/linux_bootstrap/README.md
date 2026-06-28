# linux_bootstrap

First run against a fresh host, right after a minimal Ubuntu 24.04 cloud-init install.

## What it does

- Sets the hostname from `inventory_hostname`
- Removes the `cloud-init` package (keeps `netplan.io`)
- Creates the infra admin user (uid 4242, sudo, passwordless sudo)
- Installs the SSH public keys from `inventories/<env>/ssh_keys/*.pub` into `authorized_keys`

## Key variables

- `infra_admin_username` — admin user to create
- `infra_admin_password_hash` — hashed password for that user

## Usage

Run against a freshly bootstrapped host using the temporary bootstrap user/port:

`ansible-playbook -i inventories/production/hosts playbooks/linux_bootstrap.yml --limit=my-new-host -e ansible_user=default-bootstrap -e ansible_port=22`

Afterwards apply `linux_base` to finish setup and remove the bootstrap user.

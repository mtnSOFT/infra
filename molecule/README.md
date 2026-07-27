# Molecule tests

as test container ghcr.io/mtnsoft/infra-test-ubuntu:24.04 is used. (see <https://github.com/mtnsoft/infra-test-ubuntu>)

## Inventory

the inventory in `inventories/test/hosts` is used for testing.

## Ansible Vault

`ANSIBLE_VAULT_PASSWORD_FILE=./molecule/.ansible_vault_pass.txt ansible-vault create inventories/test/group_vars/all/vault.yml`

Password is: 'test'

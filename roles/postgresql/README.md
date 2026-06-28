# postgresql

Installs a PostgreSQL 17 server from the official PGDG apt repository.

## What it does

- Adds the PGDG apt key and repository
- Installs `postgresql-17`, `postgresql-contrib-17`, `postgresql-client-17`
- Installs the Python adapter (`python3-psycopg2`)
- Ensures the service is started

> Database/user provisioning (`2_databases.yml`) and backup (`3_backup.yml`) tasks exist
> but are currently **disabled** (`.disabled` suffix). Rename to `.yml` to enable.

## Usage

`ansible-playbook -i inventories/production/hosts playbooks/postgresql.yml`

Targets the `postgresql_servers` inventory group.

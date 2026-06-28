# shared

Helper role — **not deployed directly**. Provides the dynamic task loader used by every role.

## What it does

`tasks/dynamic_tasks_main.yml` is symlinked as each role's `tasks/main.yml`. It:

- discovers numbered task files (`1_foo.yml`, `2_bar.yml`, …) in the role's `tasks/`
- runs them in filename order
- lets you run a subset via `task_list` / `fixed_task_list`

## Usage

Run only specific tasks of a role:

`ansible-playbook ... playbooks/linux_bootstrap.yml -e '{task_list: ["2_user"]}'`

When creating a new role, symlink this file to the role's `tasks/main.yml` and add the
symlink to `.prettierignore` and `.mega-linter.yml`. See the repo README "Dynamic Role Tasks".

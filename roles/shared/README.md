# shared

Helper role — **not deployed directly**. Provides the dynamic task loader used by every role.

## Dynamic Role Tasks

For every role, the `tasks/main.yml` is symlinked from `roles/shared/tasks/dynamic_tasks_main.yml`. This enables us to split up a role's tasks easely into seperate files which makes the code cleaner. It also makes it possible to only run a role's specific tasks by defining param tasks:

`ansible-playbook -i inventories/production/hosts playbooks/linux_bootstrap.yml -e '{task_list: ["2_user"]}'`

just add new task ymls in the format `1_mynewtask.yml` to `roles/$ROLE/tasks/` where as the leading number defines the order the task is being executed.

- see `roles/linux_base/tasks` for an example
- when creating a new role, symlink `roles/shared/tasks/dynamic_tasks_main.yml` to it's `tasks/main.yml`
- add main.yml path to `.prettierignore` and `.mega-linter.yml` since it hates symlinks ;)

checkout `roles/linux_base/tasks/` for an example.

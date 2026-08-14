import yaml

BASE = "/containers/gitea"


def _load(host, path):
    """Parse a rendered config file - also proves the template emits valid YAML."""
    return yaml.safe_load(host.file(path).content_string)


def _gitea(host):
    return _load(host, f"{BASE}/compose.yaml")["services"]["gitea"]


def _gitea_env(host):
    return _gitea(host)["environment"]


def test_project_directory(host):
    project = host.file(BASE)
    assert project.is_directory
    assert project.user == "root"
    assert project.group == "root"
    assert project.mode == 0o750


def test_data_directory_belongs_to_the_container_git_user(host):
    # Config, repositories and the SQLite database live here, so it is owned by
    # the UID the image drops to (gitea_uid / gitea_gid) and stays unreadable to
    # other host users. Compared by ID, since the name of uid 1000 is a property
    # of the host, not of the role.
    data = host.file(f"{BASE}/data")
    assert data.is_directory
    assert data.uid == 1000
    assert data.gid == 1000
    assert data.mode == 0o750


def test_no_secrets_file(host):
    # SQLite needs no password and Gitea generates its own SECRET_KEY /
    # INTERNAL_TOKEN into data/gitea/conf/app.ini, so unlike the pihole and
    # monitoring stacks this one renders no .env.
    assert not host.file(f"{BASE}/.env").exists


def test_compose_file(host):
    compose = host.file(f"{BASE}/compose.yaml")
    assert compose.mode == 0o644

    services = _load(host, f"{BASE}/compose.yaml")["services"]
    assert set(services) == {"gitea"}

    gitea = services["gitea"]
    assert gitea["image"] == "gitea/gitea:latest"
    assert gitea["restart"] == "unless-stopped"
    # Everything persistent is in the one data volume
    assert gitea["volumes"] == [f"{BASE}/data:/data"]
    # Compose owns the container name (gitea-gitea-1), so it cannot collide with
    # a container outside this project
    assert "container_name" not in gitea


def test_web_interface_is_published_on_the_configured_address(host):
    # gitea_bind_ip / gitea_http_port from the test inventory. Published ports
    # bypass UFW, so this binding is the access control - never the wildcard.
    assert _gitea(host)["ports"] == ["10.10.0.1:3080:3000"]


def test_sqlite_backend(host):
    # No database container: the DB is a file in the data volume
    assert _gitea_env(host)["GITEA__database__DB_TYPE"] == "sqlite3"


def test_domain_is_derived_from_the_root_url(host):
    # gitea_root_url is the only URL setting; DOMAIN is its host part, so the
    # two cannot drift apart
    env = _gitea_env(host)
    assert env["GITEA__server__ROOT_URL"] == "https://git.example.com/"
    assert env["GITEA__server__DOMAIN"] == "git.example.com"


def test_git_over_ssh_is_disabled(host):
    # The host's sshd owns :22; clone and push go over HTTP(S)
    assert _gitea_env(host)["GITEA__server__DISABLE_SSH"] == "true"


def test_instance_is_closed(host):
    # Ansible renders the configuration, so the web installer is locked, and
    # accounts are created by an admin rather than by signup
    env = _gitea_env(host)
    assert env["GITEA__security__INSTALL_LOCK"] == "true"
    assert env["GITEA__service__DISABLE_REGISTRATION"] == "true"


def test_container_user_matches_the_data_directory(host):
    # Same UID/GID the data directory is chowned to
    env = _gitea_env(host)
    assert env["USER_UID"] == "1000"
    assert env["USER_GID"] == "1000"


def test_timezone_comes_from_the_inventory(host):
    # timezone in inventories/test/group_vars/all/vars.yml
    assert _gitea_env(host)["TZ"] == "Europe/Zurich"

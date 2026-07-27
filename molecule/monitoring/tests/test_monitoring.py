import yaml

BASE = "/containers/monitoring"

# UID/GID the upstream images run as; must match the role defaults.
NOBODY_UID = NOBODY_GID = 65534
GRAFANA_UID = 472
GRAFANA_GID = 0  # grafana's image runs as uid 472 in the root group


def _load(host, path):
    """Parse a rendered config file - also proves the template emits valid YAML."""
    return yaml.safe_load(host.file(path).content_string)


def test_project_directory(host):
    project = host.file(BASE)
    assert project.is_directory
    assert project.user == "root"
    assert project.group == "root"
    assert project.mode == 0o750


def test_data_dirs_owned_by_container_uids(host):
    prometheus_data = host.file(f"{BASE}/prometheus/data")
    assert prometheus_data.is_directory
    assert prometheus_data.uid == NOBODY_UID
    assert prometheus_data.gid == NOBODY_GID
    assert prometheus_data.mode == 0o750

    alertmanager_data = host.file(f"{BASE}/alertmanager/data")
    assert alertmanager_data.is_directory
    assert alertmanager_data.uid == NOBODY_UID
    assert alertmanager_data.gid == NOBODY_GID

    grafana_data = host.file(f"{BASE}/grafana/data")
    assert grafana_data.is_directory
    assert grafana_data.uid == GRAFANA_UID
    assert grafana_data.gid == GRAFANA_GID
    assert grafana_data.mode == 0o750


def test_rules_directory_ships_empty(host):
    rules = host.file(f"{BASE}/prometheus/rules")
    assert rules.is_directory
    assert host.run(f"ls -A {BASE}/prometheus/rules").stdout.strip() == ""


def test_env_file_holds_the_secret_and_is_not_world_readable(host):
    env = host.file(f"{BASE}/.env")
    assert env.exists
    assert env.user == "root"
    assert env.mode == 0o600
    assert env.contains("GF_SECURITY_ADMIN_PASSWORD=molecule-test-password")


def test_compose_file(host):
    compose = host.file(f"{BASE}/compose.yaml")
    assert compose.mode == 0o644
    # compose.yaml is world-readable, so the password must not be inlined here
    assert "molecule-test-password" not in compose.content_string

    services = _load(host, f"{BASE}/compose.yaml")["services"]
    assert set(services) == {"prometheus", "alertmanager", "grafana"}

    # Published ports bind the configured host IPs, never the wildcard
    assert services["prometheus"]["ports"] == ["127.0.0.1:9090:9090"]
    assert services["alertmanager"]["ports"] == ["127.0.0.1:9093:9093"]
    assert services["grafana"]["ports"] == ["10.10.0.1:3000:3000"]

    # `user:` must match what the data dirs were chowned to
    assert services["prometheus"]["user"] == f"{NOBODY_UID}:{NOBODY_GID}"
    assert services["alertmanager"]["user"] == f"{NOBODY_UID}:{NOBODY_GID}"
    assert services["grafana"]["user"] == f"{GRAFANA_UID}:{GRAFANA_GID}"

    grafana_env = services["grafana"]["environment"]
    assert grafana_env["GF_SECURITY_ADMIN_PASSWORD"] == "${GF_SECURITY_ADMIN_PASSWORD}"
    assert grafana_env["GF_USERS_ALLOW_SIGN_UP"] == "false"

    for service in services.values():
        assert service["restart"] == "unless-stopped"


def test_prometheus_config(host):
    config_file = host.file(f"{BASE}/prometheus/prometheus.yml")
    assert config_file.mode == 0o644

    config = _load(host, f"{BASE}/prometheus/prometheus.yml")
    assert config["global"]["scrape_interval"] == "30s"
    assert config["global"]["external_labels"] == {"cluster": "molecule"}
    assert config["rule_files"] == ["/etc/prometheus/rules/*.yml"]

    alertmanagers = config["alerting"]["alertmanagers"][0]["static_configs"][0]
    assert alertmanagers["targets"] == ["alertmanager:9093"]

    # self-scrape plus the extra jobs from monitoring_prometheus_extra_scrape_configs
    assert [job["job_name"] for job in config["scrape_configs"]] == ["prometheus", "node"]
    assert config["scrape_configs"][1]["static_configs"][0]["targets"] == ["10.0.0.10:9100"]


def test_alertmanager_config(host):
    config_file = host.file(f"{BASE}/alertmanager/alertmanager.yml")
    # may hold receiver secrets: readable by root and the container UID only
    assert config_file.user == "root"
    assert config_file.gid == NOBODY_GID
    assert config_file.mode == 0o640

    config = _load(host, f"{BASE}/alertmanager/alertmanager.yml")
    assert config["global"]["resolve_timeout"] == "5m"
    assert config["route"]["receiver"] == "default"
    assert config["route"]["group_by"] == ["alertname", "instance"]

    assert [receiver["name"] for receiver in config["receivers"]] == ["default", "ntfy"]
    assert config["receivers"][1]["webhook_configs"][0]["url"] == "https://ntfy.example.com/alerts"


def test_grafana_provisioning(host):
    datasource = _load(
        host, f"{BASE}/grafana/provisioning/datasources/prometheus.yml"
    )["datasources"][0]
    # resolved over the compose bridge network, not the published host port
    assert datasource["url"] == "http://prometheus:9090"
    assert datasource["type"] == "prometheus"
    assert datasource["isDefault"] is True

    provider = _load(
        host, f"{BASE}/grafana/provisioning/dashboards/default.yml"
    )["providers"][0]
    assert provider["type"] == "file"
    assert provider["options"]["path"] == "/etc/grafana/dashboards"

    assert host.file(f"{BASE}/grafana/dashboards").is_directory

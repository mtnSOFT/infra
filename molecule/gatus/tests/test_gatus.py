import yaml

BASE = "/containers/gatus"
TEST_HOST = "testhost-ubuntu-24.04"
CERT_CONDITION = "[CERTIFICATE_EXPIRATION] > 336h"


def _config(host):
    """Parse the rendered config - also proves the template emits valid YAML."""
    return yaml.safe_load(host.file(f"{BASE}/config/config.yaml").content_string)


def _endpoints(host):
    return {endpoint["name"]: endpoint for endpoint in _config(host)["endpoints"]}


def test_directories(host):
    for path in (BASE, f"{BASE}/config", f"{BASE}/data"):
        directory = host.file(path)
        assert directory.is_directory
        assert directory.user == "root"
        assert directory.group == "root"
        assert directory.mode == 0o750


def test_config_file_is_private(host):
    # may hold alerting secrets
    config_file = host.file(f"{BASE}/config/config.yaml")
    assert config_file.user == "root"
    assert config_file.mode == 0o600


def test_compose_file(host):
    compose = host.file(f"{BASE}/compose.yaml")
    assert compose.mode == 0o644

    services = yaml.safe_load(compose.content_string)["services"]
    assert set(services) == {"gatus"}
    gatus = services["gatus"]
    # Published port binds the configured host IP, never the wildcard
    assert gatus["ports"] == ["10.10.0.1:8080:8080"]
    assert gatus["environment"]["GATUS_CONFIG_PATH"] == "/config/config.yaml"
    # Directory mount, so hot reload sees the re-rendered file
    assert f"{BASE}/config:/config:ro" in gatus["volumes"]
    assert gatus["restart"] == "unless-stopped"


def test_global_settings(host):
    config = _config(host)
    assert config["metrics"] is True
    assert config["storage"] == {"type": "sqlite", "path": "/data/data.db"}
    assert config["web"]["port"] == 8080
    assert config["alerting"]["ntfy"]["topic"] == "infra"


def test_inventory_host_checks(host):
    endpoints = _endpoints(host)
    ping = endpoints[f"{TEST_HOST} ping"]
    ssh = endpoints[f"{TEST_HOST} ssh"]

    # addressed by ansible_host if molecule sets one, else by its internal FQDN
    assert ping["url"] in (
        f"icmp://{TEST_HOST}.example.internal",
        f"icmp://{TEST_HOST}",
    )
    assert ssh["url"] == ping["url"].replace("icmp://", "tcp://") + ":22"

    for check in (ping, ssh):
        assert check["group"] == "Hosts"
        assert check["interval"] == "1m"
        assert check["conditions"] == ["[CONNECTED] == true"]
        assert check["alerts"] == [{"type": "ntfy"}]


def test_extra_host_checks(host):
    endpoints = _endpoints(host)
    assert endpoints["apphost ping"]["url"] == "icmp://192.0.2.10"
    assert endpoints["apphost ssh"]["url"] == "tcp://192.0.2.10:2222"
    assert endpoints["labhost ping"]["url"] == "icmp://192.0.2.20"
    assert "labhost ssh" not in endpoints


def test_endpoint_defaults(host):
    endpoints = _endpoints(host)
    assert endpoints["website"]["interval"] == "5m"
    # an endpoint's own value wins over gatus_endpoint_defaults
    assert endpoints["certificate"]["interval"] == "1h"


def test_certificate_expiration_condition(host):
    endpoints = _endpoints(host)
    # appended to https:// endpoints
    assert endpoints["website"]["conditions"] == ["[STATUS] == 200", CERT_CONDITION]
    # opted out - and the role-only key is not rendered
    assert endpoints["internal"]["conditions"] == ["[STATUS] == 200"]
    assert "certificate_check" not in endpoints["internal"]
    assert endpoints["internal"]["client"] == {"insecure": True}
    # an existing expiration condition is kept, not duplicated
    assert endpoints["certificate"]["conditions"] == [
        "[CONNECTED] == true",
        "[CERTIFICATE_EXPIRATION] > 720h",
    ]
    # not a TLS endpoint
    assert endpoints["resolver"]["conditions"] == ["[DNS_RCODE] == NOERROR"]
    assert endpoints["resolver"]["dns"]["query-type"] == "A"

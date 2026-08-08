import yaml

BASE = "/containers/vaultwarden"


def _load(host, path):
    """Parse a rendered config file - also proves the template emits valid YAML."""
    return yaml.safe_load(host.file(path).content_string)


def _admin_token(host):
    """The rendered token, read back from .env rather than hardcoded here."""
    lines = [
        line
        for line in host.file(f"{BASE}/.env").content_string.splitlines()
        if line and not line.startswith("#")
    ]
    # The only variable in there
    assert len(lines) == 1, lines
    name, _, value = lines[0].partition("=")
    assert name == "VAULTWARDEN_ADMIN_TOKEN"
    return value


def _service(host):
    return _load(host, f"{BASE}/compose.yaml")["services"]["vaultwarden"]


def test_directory_tree(host):
    # The data directory holds the SQLite database and the token signing keys,
    # the ssl one the private key - both stay root-only.
    tree = ((BASE, 0o750), (f"{BASE}/data", 0o700), (f"{BASE}/ssl", 0o700))
    for path, mode in tree:
        directory = host.file(path)
        assert directory.is_directory
        assert directory.user == "root"
        assert directory.group == "root"
        assert directory.mode == mode


def test_tls_material_is_installed(host):
    cert = host.file(f"{BASE}/ssl/cert.pem")
    assert cert.mode == 0o644
    assert cert.content_string.startswith("-----BEGIN CERTIFICATE-----")
    assert cert.content_string.rstrip().endswith("-----END CERTIFICATE-----")

    # Same PEM pair as the certificate, from the test group's vault
    key = host.file(f"{BASE}/ssl/key.pem")
    assert key.user == "root"
    assert key.mode == 0o600
    assert key.content_string.startswith("-----BEGIN PRIVATE KEY-----")


def test_env_file_holds_the_admin_token_and_is_not_world_readable(host):
    env = host.file(f"{BASE}/.env")
    assert env.exists
    assert env.user == "root"
    assert env.mode == 0o600

    # The token reaches the role as vault_vaultwarden_admin_token, so a leftover
    # "{{" or an empty value means that indirection is broken.
    token = _admin_token(host)
    assert token
    assert "{{" not in token


def test_compose_file(host):
    compose = host.file(f"{BASE}/compose.yaml")
    assert compose.mode == 0o644
    # compose.yaml is world-readable, so neither the admin token nor the private
    # key may be inlined here
    assert _admin_token(host) not in compose.content_string
    assert "PRIVATE KEY" not in compose.content_string

    services = _load(host, f"{BASE}/compose.yaml")["services"]
    assert set(services) == {"vaultwarden"}

    vaultwarden = services["vaultwarden"]
    assert vaultwarden["container_name"] == "vaultwarden"
    assert vaultwarden["image"] == "vaultwarden/server:latest"
    assert vaultwarden["restart"] == "unless-stopped"
    assert vaultwarden["volumes"] == [
        f"{BASE}/data:/data",
        f"{BASE}/ssl:/ssl:ro",
    ]


def test_published_port_is_the_configured_https_port(host):
    # vaultwarden_bind_ip / vaultwarden_https_port from the test group_vars; the
    # container itself listens on 80, with TLS on top (see ROCKET_TLS below).
    assert _service(host)["ports"] == ["10.10.0.1:8443:80"]


def test_tls_is_terminated_by_vaultwarden(host):
    assert _service(host)["environment"]["ROCKET_TLS"] == (
        '{certs="/ssl/cert.pem",key="/ssl/key.pem"}'
    )


def test_domain_carries_the_custom_port(host):
    # Passkey origin and the base of invitation links, so it has to match what
    # the browser shows - port included.
    assert _service(host)["environment"]["DOMAIN"] == (
        "https://vault.example.com:8443"
    )


def test_database_is_sqlite(host):
    # No DATABASE_URL at all: that is what makes Vaultwarden fall back to SQLite
    # in /data, the whole point of this stack.
    assert "DATABASE_URL" not in _service(host)["environment"]


def test_account_handling(host):
    env = _service(host)["environment"]
    # Booleans reach the container as the strings Vaultwarden parses
    assert env["SIGNUPS_ALLOWED"] == "false"
    assert env["INVITATIONS_ALLOWED"] == "true"
    # Present because the test inventory sets a token; without one the key is
    # omitted entirely, which disables the /admin panel
    assert env["ADMIN_TOKEN"] == "${VAULTWARDEN_ADMIN_TOKEN}"

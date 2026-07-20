# Tests run against the single molecule platform host (see the working
# wireguard / linux_base scenarios for the same default-host pattern).


# --- Authoritative server (loopback, behind the recursor) ---

def test_pdns_auth_running(host):
    """The authoritative PowerDNS service is running and enabled."""
    pdns = host.service("pdns")
    assert pdns.is_running
    assert pdns.is_enabled


def test_pdns_auth_listens_on_loopback(host):
    """Auth server now listens on 127.0.0.1:5300, fronted by the recursor."""
    assert host.socket("tcp://127.0.0.1:5300").is_listening


def test_pdns_auth_config_loopback(host):
    """Auth config binds loopback only (no longer 0.0.0.0)."""
    config = host.file("/etc/powerdns/pdns.conf")
    assert config.exists
    assert config.contains("local-address=127.0.0.1")
    assert config.contains("local-port=5300")


def test_pdns_database_exists(host):
    """The PowerDNS SQLite database exists and is owned by pdns."""
    db_file = host.file("/var/lib/powerdns/pdns.sqlite3")
    assert db_file.exists
    assert db_file.user == "pdns"
    assert db_file.group == "pdns"


# --- Recursor (front-end resolver on :53) ---

def test_recursor_running(host):
    """The PowerDNS Recursor service is running and enabled."""
    rec = host.service("pdns-recursor")
    assert rec.is_running
    assert rec.is_enabled


def test_recursor_listening(host):
    """Recursor listens on 127.0.0.1:53 (resolved from the 'lo' interface)."""
    assert host.socket("tcp://127.0.0.1:53").is_listening


def test_recursor_resolves_local_zone(host):
    """Local-zone query is forwarded to the authoritative server on :5300."""
    cmd = host.run("dig @127.0.0.1 -p 53 www.example.local A +short")
    assert cmd.rc == 0
    assert "192.168.1.100" in cmd.stdout


def test_recursor_resolves_external(host):
    """Queries outside the local zone are forwarded to the upstream resolvers."""
    cmd = host.run("dig @127.0.0.1 -p 53 example.com A +short")
    assert cmd.rc == 0
    assert cmd.stdout.strip() != ""

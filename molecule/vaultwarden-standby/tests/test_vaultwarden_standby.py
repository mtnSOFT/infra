BASE = "/containers/vaultwarden"
SYNC = "/usr/local/bin/vaultwarden-sync.sh"
KEY = "/root/.ssh/vaultwarden-sync"
SOURCE = "vault-01.example.com"
# The host key fixture this scenario published, in place of a primary converge
HOST_KEY = "AAAAC3NzaC1lZDI1NTE5AAAAIKw575LaJV9znEN57H3"


def _script(host):
    return host.file(SYNC).content_string


def test_sync_key_pair_is_generated(host):
    key = host.file(KEY)
    assert key.exists
    assert key.user == "root"
    assert key.mode == 0o600

    pub = host.file(f"{KEY}.pub").content_string
    assert pub.startswith("ssh-ed25519 ")
    # Comment carries the host, so an authorized_keys line is traceable
    assert "vaultwarden-sync testhost-ubuntu-24.04" in pub


def test_the_primary_host_key_is_pinned(host):
    # Strict host checking with a key from the inventory, not trust on first use
    known_hosts = host.file("/root/.ssh/known_hosts").content_string
    assert SOURCE in known_hosts
    assert HOST_KEY in known_hosts


def test_sync_script(host):
    script = host.file(SYNC)
    assert script.exists
    assert script.user == "root"
    assert script.mode == 0o700

    body = _script(host)
    assert f'SOURCE="vwsync@{SOURCE}"' in body
    assert f"-i {KEY}" in body
    assert "-p 22" in body
    assert "StrictHostKeyChecking=yes" in body
    # Retention here is the standby's own, larger than the primary's
    assert "KEEP=30" in body
    # No --delete: a primary that wipes its archives must not wipe this copy
    assert "--delete" not in body


def test_sync_script_leaves_a_promoted_host_alone(host):
    body = _script(host)
    assert "ps -q --status running" in body
    # The guard has to come before anything that writes to the data directory
    assert body.index("exit 0") < body.index("tar xzf")


def test_sync_script_restores_the_newest_archive(host):
    body = _script(host)
    assert "tar xzf" in body
    # The WAL/SHM sidecars belong to the database being replaced
    assert "db.sqlite3-wal" in body
    assert "db.sqlite3-shm" in body


def test_sync_runs_daily_from_cron(host):
    crontab = host.file("/var/spool/cron/crontabs/root").content_string
    assert "#Ansible: Vaultwarden sync" in crontab
    assert f"0 4 * * * {SYNC}" in crontab
    # A standby has no live database, so the backup job belongs to the primary
    # only - and this asserts converting a host to a standby removes it.
    assert "Vaultwarden backup" not in crontab
    assert not host.file("/usr/local/bin/vaultwarden-backup.sh").exists


def test_archive_directory_is_ready_for_the_pull(host):
    # 3_backup.yml does not run here, so the rsync target comes from the sync
    # tasks instead - and stays root-only.
    backup = host.file(f"{BASE}/backup")
    assert backup.is_directory
    assert backup.user == "root"
    assert backup.mode == 0o700


def test_the_stack_is_rendered_ready_for_promotion(host):
    # Promotion is `docker compose up -d` on this host, so its project has to be
    # complete and identical to the primary's: same domain, same certificate.
    compose = host.file(f"{BASE}/compose.yaml").content_string
    assert 'DOMAIN: "https://vault.example.com:8443"' in compose
    assert 'ROCKET_TLS: \'{certs="/ssl/cert.pem",key="/ssl/key.pem"}\'' in compose
    assert host.file(f"{BASE}/ssl/cert.pem").exists
    assert host.file(f"{BASE}/ssl/key.pem").mode == 0o600

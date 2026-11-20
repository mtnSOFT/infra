import os

import pytest

CLIENT = "testhost-ubuntu-24.04"
BORG_HOME = "/srv/borg"
REPO = f"{BORG_HOME}/repos/{CLIENT}"
PASSFILE = f"/etc/borg-server/{CLIENT}"
SSH_KEY = "/root/.ssh/borg_ed25519"
SSH = f"ssh -i {SSH_KEY} -o BatchMode=yes"


@pytest.fixture(scope="module")
def sshd(host):
    # The container has no init system; start sshd by hand for the live tests.
    host.run("mkdir -p /run/sshd && (pgrep -x sshd || /usr/sbin/sshd)")
    yield


# --- server ---------------------------------------------------------------


def test_borg_user(host):
    user = host.user("borg")
    assert user.home == BORG_HOME
    assert user.shell == "/bin/sh"


@pytest.mark.parametrize(
    "path", [BORG_HOME, f"{BORG_HOME}/.ssh", f"{BORG_HOME}/repos", "/etc/borg-server"]
)
def test_borg_directories_are_private(host, path):
    d = host.file(path)
    assert d.is_directory
    assert d.user == "borg"
    assert d.mode == 0o700


def test_authorized_keys_pins_client_to_append_only_repo(host):
    keys = host.file(f"{BORG_HOME}/.ssh/authorized_keys")
    assert keys.mode == 0o600
    client_pub = host.file(f"{SSH_KEY}.pub").content_string.split()[1]
    line = next(l for l in keys.content_string.splitlines() if client_pub in l)
    assert line.startswith(
        f'command="borg serve --append-only --restrict-to-repository {REPO}",restrict '
    )


def test_passphrase_file(host):
    f = host.file(PASSFILE)
    assert f.user == "borg"
    assert f.mode == 0o400
    assert f.content_string == "molecule-test-passphrase"


def test_repository_initialised(host):
    assert host.file(f"{REPO}/config").exists


def test_repository_key_exported_vault_encrypted():
    # Lands on the controller, not in the container: borg_server_key_export_dir
    # points into molecule's ephemeral directory for this scenario.
    path = os.path.join(
        os.environ["MOLECULE_EPHEMERAL_DIRECTORY"], "borg_keys", f"{CLIENT}.key"
    )
    with open(path) as f:
        content = f.read()
    assert content.startswith("$ANSIBLE_VAULT;")
    assert "BORG_KEY" not in content


def test_prune_script_uses_client_retention(host):
    script = host.file("/usr/local/bin/borg-prune-all.sh").content_string
    # keep_daily overridden in the test inventory, the others from the defaults.
    assert f"prune_repo {CLIENT} --keep-daily 3 --keep-monthly 6 --keep-weekly 4" in script


def test_prune_timer_rendered(host):
    assert host.file("/etc/systemd/system/borg-prune.timer").contains("OnCalendar=")
    assert host.file("/etc/systemd/system/borg-prune.service").contains("User=borg")


# --- client ---------------------------------------------------------------


def test_client_key(host):
    assert host.file(SSH_KEY).mode == 0o600
    assert host.file(f"{SSH_KEY}.pub").contains("borgmatic@")


def test_server_host_key_trusted(host):
    hostkey = host.file("/etc/ssh/ssh_host_ed25519_key.pub").content_string.split()[1]
    assert host.file("/root/.ssh/known_hosts").contains(hostkey)


def test_borgmatic_config_is_valid(host):
    assert host.file("/etc/borgmatic/config.yaml").mode == 0o600
    assert host.file("/etc/borgmatic/passphrase").mode == 0o600
    host.run_expect([0], "borgmatic config validate")


def test_borgmatic_config_has_no_retention(host):
    assert not host.file("/etc/borgmatic/config.yaml").contains("keep_")


def test_borgmatic_timer_rendered(host):
    service = host.file("/etc/systemd/system/borgmatic.service").content_string
    assert "create --stats check" in service
    assert "prune" not in service


# --- live, over SSH ---------------------------------------------------------


def test_forced_command_blocks_shell(host, sshd):
    # stdin closed so borg serve, which runs instead of `id`, exits right away.
    out = host.run(f"timeout 20 {SSH} borg@localhost id </dev/null")
    assert "uid=" not in out.stdout


def test_backup_and_list(host, sshd):
    host.run_expect([0], "borgmatic create")
    listing = host.check_output("borgmatic list")
    assert CLIENT in listing


def test_other_repository_refused(host, sshd):
    out = host.run(
        f"BORG_RSH='{SSH}' BORG_PASSPHRASE=x "
        f"borg info ssh://borg@localhost{BORG_HOME}/repos/someone-else"
    )
    assert out.rc != 0


def test_server_prune_runs(host, sshd):
    host.run_expect([0], "runuser -u borg -- /usr/local/bin/borg-prune-all.sh")

import os

import pytest
import yaml

CLIENT = "testhost-ubuntu-24.04"
BORG_HOME = "/var/lib/borg"
DATA = "/srv/borg/data"
REPO = f"{DATA}/{CLIENT}"
SSH_KEY = "/root/.ssh/borg_ed25519"
SSH = f"ssh -i {SSH_KEY} -o BatchMode=yes"


# --- server ---------------------------------------------------------------


def test_borg_user_home_is_off_the_backup_disk(host):
    user = host.user("borg")
    assert user.home == BORG_HOME
    assert user.shell == "/bin/sh"


@pytest.mark.parametrize("path", [BORG_HOME, f"{BORG_HOME}/.ssh", DATA])
def test_borg_directories_are_private(host, path):
    d = host.file(path)
    assert d.is_directory
    assert d.user == "borg"
    assert d.mode == 0o700


def test_authorized_keys_pins_client_to_its_repo(host):
    keys = host.file(f"{BORG_HOME}/.ssh/authorized_keys")
    assert keys.mode == 0o600
    client_pub = host.file(f"{SSH_KEY}.pub").content_string.split()[1]
    line = next(l for l in keys.content_string.splitlines() if client_pub in l)
    assert line.startswith(f'command="borg serve --restrict-to-repository {REPO}",restrict ')


def test_server_holds_no_passphrase(host):
    assert not host.file("/etc/borg-server").exists
    assert "molecule-test-passphrase" not in host.check_output(
        f"grep -rs molecule-test-passphrase {BORG_HOME} {DATA} || true"
    )


def test_btrbk_config(host):
    conf = host.file("/etc/btrbk/btrbk.conf").content_string
    assert "snapshot_preserve       14d 8w 3m" in conf
    assert "volume /srv/borg" in conf
    assert "subvolume data" in conf
    assert host.file("/srv/borg/.snapshots").is_directory


def test_btrbk_timer_override(host):
    override = host.file("/etc/systemd/system/btrbk.timer.d/override.conf")
    assert "OnCalendar=*-*-* 06:00:00" in override.content_string


def test_scrub_units(host):
    service = host.file("/etc/systemd/system/borg-scrub.service").content_string
    assert "btrfs scrub start -B /srv/borg" in service
    assert host.file("/etc/systemd/system/borg-scrub.timer").contains("OnCalendar=")


# --- client ---------------------------------------------------------------


def test_client_key(host):
    assert host.file(SSH_KEY).mode == 0o600
    assert host.file(f"{SSH_KEY}.pub").contains("borgmatic@")


def test_server_host_key_trusted(host):
    hostkey = host.file("/etc/ssh/ssh_host_ed25519_key.pub").content_string.split()[1]
    assert host.file("/root/.ssh/known_hosts").contains(hostkey)


def test_borgmatic_config(host):
    assert host.file("/etc/borgmatic/passphrase").mode == 0o600
    config = host.file("/etc/borgmatic/config.yaml")
    assert config.mode == 0o600
    host.run_expect([0], "borgmatic config validate")
    parsed = yaml.safe_load(config.content_string)
    assert parsed["keep_daily"] == 3
    assert parsed["repositories"][0]["path"] == f"ssh://borg@localhost:22{REPO}"


def test_repository_created_by_client(host):
    assert host.file(f"{REPO}/config").exists


def test_repository_key_exported_vault_encrypted():
    # Lands on the controller, not in the container: borgmatic_client_key_export_dir
    # points into molecule's ephemeral directory for this scenario.
    path = os.path.join(
        os.environ["MOLECULE_EPHEMERAL_DIRECTORY"], "borg_keys", f"{CLIENT}.key"
    )
    with open(path) as f:
        content = f.read()
    assert content.startswith("$ANSIBLE_VAULT;")
    assert "BORG_KEY" not in content


def test_borgmatic_service_runs_all_actions(host):
    service = host.file("/etc/systemd/system/borgmatic.service").content_string
    assert "create --stats prune compact check" in service


# --- live, over SSH ---------------------------------------------------------


def test_forced_command_blocks_shell(host):
    # stdin closed so borg serve, which runs instead of `id`, exits right away.
    out = host.run(f"timeout 20 {SSH} borg@localhost id </dev/null")
    assert "uid=" not in out.stdout


def test_backup_prune_and_list(host):
    host.run_expect([0], "borgmatic create prune compact")
    assert CLIENT in host.check_output("borgmatic list")


def test_other_repository_refused(host):
    out = host.run(
        f"BORG_RSH='{SSH}' BORG_PASSPHRASE=x "
        f"borg info ssh://borg@localhost{DATA}/someone-else"
    )
    assert out.rc != 0

SCRIPT = "/usr/local/bin/update-dyndns.sh"
CONFIG_DIR = "/etc/dyndns-client"
CURL_CONF = f"{CONFIG_DIR}/curl.conf"
LOG_FILE = "/var/log/dyndns_update.log"

# Spelled out rather than read from the role, so these independently check what
# the inventory asked for and what the defaults supply.
HOSTNAME = "dynhost.alice.example.com"
USERNAME = "dyndns-alice"
UPDATE_URL = "https://infomaniak.com/nic/update"

# Answers with an HTTP 200 status line and whatever FAKE_BODY holds, so the
# script's response handling can be driven without a credential or a route to
# Infomaniak - this scenario has neither.
CURL_SHIM = r"""#!/bin/bash
printf '%s\n200' "$FAKE_BODY"
"""


def _root_crontab(host):
    return host.check_output("crontab -l -u root")


def _password(host):
    line = next(
        line
        for line in host.file(CURL_CONF).content_string.splitlines()
        if line.startswith("user = ")
    )
    return line.split('"')[1].partition(":")[2]


def test_config_directory_is_root_only(host):
    # Holds the basic-auth credential and nothing else, so nothing but root has
    # any reason to be able to list it.
    config_dir = host.file(CONFIG_DIR)
    assert config_dir.is_directory
    assert config_dir.user == "root"
    assert config_dir.group == "root"
    assert config_dir.mode == 0o700


def test_curl_config_holds_the_credential_and_is_not_world_readable(host):
    curl_conf = host.file(CURL_CONF)
    assert curl_conf.exists
    assert curl_conf.user == "root"
    assert curl_conf.group == "root"
    assert curl_conf.mode == 0o600

    # The credential reaches the role as vault_dyndns_client_password, so a
    # leftover "{{" or an empty password means that indirection is broken.
    assert f'user = "{USERNAME}:' in curl_conf.content_string
    password = _password(host)
    assert password
    assert "{{" not in password


def test_script_is_root_only_and_parses(host):
    script = host.file(SCRIPT)
    assert script.exists
    assert script.user == "root"
    assert script.group == "root"
    assert script.mode == 0o700

    # dyndns_client_update is false here, so the converge renders the template
    # without ever running it - nothing else would catch a syntax error
    # introduced by a Jinja edit.
    assert host.run("bash -n %s" % SCRIPT).rc == 0


def test_script_targets_infomaniak_over_ipv4_and_carries_no_credential(host):
    content = host.file(SCRIPT).content_string

    assert UPDATE_URL in content
    assert "hostname=${DYNDNS_HOSTNAME}" in content
    assert HOSTNAME in content

    # Infomaniak picks A vs AAAA from the protocol the request arrives over, so
    # without --ipv4 a host with working IPv6 updates the wrong record type.
    assert "--ipv4" in content

    # myip is deliberately not sent - Infomaniak then uses the request's source
    # address, which is what makes this work behind NAT with no IP-echo service.
    assert "myip=" not in content

    # The credential belongs in curl.conf, reached via --config, so that it never
    # shows up in ps output. It must therefore not be inlined here.
    assert "--config" in content
    assert _password(host) not in content


def test_update_cron_job(host):
    crontab = _root_crontab(host)
    assert "dyndns_client update" in crontab

    lines = [
        line
        for line in crontab.splitlines()
        if SCRIPT in line and not line.startswith("#")
    ]
    assert len(lines) == 1
    assert lines[0].startswith("*/5 * * * *")


def test_no_netzone_era_cron_job_is_left_behind(host):
    # The role renames the job, and ansible.builtin.cron keys entries on that
    # name - so without the explicit removal task a host converged before the
    # provider switch would keep polling on the old entry as well.
    assert "netzone" not in _root_crontab(host).lower()


def test_script_exit_status_and_log_reflect_the_provider_response(host):
    # The only test that covers the failure path. The netzone-era script ended in
    # an unconditional `exit 0`, so a badauth was written to the log and then
    # ignored forever; cron only mails root when the script actually fails.
    shim_dir = "/tmp/dyndns-shim"
    host.check_output("mkdir -p " + shim_dir)
    host.check_output(
        "cat > {0}/curl <<'SHIM'\n{1}SHIM\nchmod 0755 {0}/curl".format(
            shim_dir, CURL_SHIM
        )
    )

    def run(body):
        return host.run(
            'FAKE_BODY="{0}" PATH={1}:$PATH {2}'.format(body, shim_dir, SCRIPT)
        ).rc

    try:
        # Both spellings Infomaniak answers with, current and legacy.
        assert run("successfully_changed 198.51.100.7") == 0
        assert run("no_change 198.51.100.7") == 0
        assert run("good 198.51.100.7") == 0
        assert run("nochg 198.51.100.7") == 0

        assert run("badauth") != 0
        assert run("nohost") != 0
        # An unrecognised body is a failure too, not a silent success.
        assert run("something else entirely") != 0
    finally:
        host.check_output("rm -rf " + shim_dir)

    # The runs above are the first thing to write the log, since the converge
    # itself never called the provider. Bounded to its last 1000 lines, which is
    # why the role ships no logrotate entry.
    log = host.file(LOG_FILE)
    assert log.exists
    assert "credentials rejected" in log.content_string
    assert "unchanged" in log.content_string
    assert len(log.content_string.splitlines()) <= 1000

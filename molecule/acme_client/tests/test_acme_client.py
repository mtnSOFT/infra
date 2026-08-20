import re

CONFIG = "/etc/acme-client"
STATE = "/var/lib/acme_client"
CA_DIR = f"{STATE}/acme-v02.api.letsencrypt.org"

TOKEN = "molecule-test-token-not-a-real-credential"

# The certificate with everything overridden, and the bare one that falls back to
# the acme_client_default_* values. Kept as constants so a test that reads the
# wrong one is obvious.
ZONE_A = "int.example.internal"
ZONE_B = "lab.example.internal"


def _conf(host, zone):
    """Parse a rendered .conf into a dict, the way the shell would source it."""
    values = {}
    for line in host.file(f"{CONFIG}/certs/{zone}.conf").content_string.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key] = value.strip("'")
    return values


def test_lego_binary_is_installed_at_the_versioned_path(host):
    # The version is read back out of the path rather than hard-coded, so bumping
    # acme_client_lego_version does not mean editing this test - but the binary
    # still has to agree with the directory it was extracted into, which is what
    # catches a stale checksum or a moved release URL.
    links = host.file("/usr/local/bin/lego")
    assert links.is_symlink
    target = links.linked_to
    assert target.startswith("/usr/local/lib/lego/")

    binary = host.file(target)
    assert binary.is_file
    assert binary.user == "root"
    assert binary.group == "root"
    assert binary.mode == 0o755

    version = target.split("/")[-2]
    assert version in host.run(f"{target} --version").stdout


def test_api_token_is_written_only_to_its_own_file(host):
    config_dir = host.file(CONFIG)
    assert config_dir.is_directory
    assert config_dir.mode == 0o700

    token = host.file(f"{CONFIG}/dns-api-token")
    assert token.is_file
    assert token.user == "root"
    assert token.group == "root"
    assert token.mode == 0o600

    # Exactly one trailing newline. lego strips one "\n" and no other
    # whitespace, so a second newline or a trailing space is sent to the API
    # verbatim and comes back as a 401 that explains nothing.
    assert token.content_string == f"{TOKEN}\n"
    assert token.content_string.count("\n") == 1


def test_the_token_appears_nowhere_else(host):
    # A security regression test: the token must not reach the unit file (which
    # is world-readable and printed by `systemctl cat`), the scripts, or either
    # .conf.
    for path in (
        "/etc/systemd/system/acme-client-renew@.service",
        "/etc/systemd/system/acme-client-renew@.timer",
        "/usr/local/bin/acme-client-renew.sh",
        "/usr/local/bin/acme-client-deploy.sh",
        f"{CONFIG}/certs/{ZONE_A}.conf",
        f"{CONFIG}/certs/{ZONE_B}.conf",
        f"{CONFIG}/reload.d/{ZONE_A}.sh",
    ):
        content = host.file(path).content_string
        assert TOKEN not in content, path
        assert "INFOMANIAK_ACCESS_TOKEN=" not in content, path


def test_state_and_deploy_directories(host):
    # One state directory per CA host, so an entry pointed at staging cannot
    # overwrite a production certificate.
    ca = host.file(CA_DIR)
    assert ca.is_directory
    assert ca.mode == 0o700

    for zone in (ZONE_A, ZONE_B):
        deploy = host.file(f"/etc/ssl/{zone}")
        assert deploy.is_directory
        assert deploy.user == "root"
        # 0755, not 0700: the private key's own mode is the protection, and the
        # directory has to stay traversable for the docker daemon and anything
        # else that reads the certificate.
        assert deploy.mode == 0o755


def test_the_role_never_fabricates_certificate_material(host):
    # lab.example.internal has no placeholder source in the converge, so nothing
    # should have appeared in its deploy directory. If this ever fails, the role
    # has started generating a certificate rather than deploying one.
    assert not host.file(f"/etc/ssl/{ZONE_B}/fullchain.pem").exists
    assert not host.file(f"/etc/ssl/{ZONE_B}/privkey.pem").exists


def test_overridden_certificate_conf(host):
    conf = _conf(host, ZONE_A)
    assert conf["ZONE"] == ZONE_A
    # All three SANs, in order, with the wildcard first - several wildcards in
    # one certificate is legitimate and must survive rendering.
    assert conf["DOMAINS"] == (
        f"*.{ZONE_A} {ZONE_A} *.dev.{ZONE_A}"
    )
    # lego derives the filename from the FIRST domain, "*" replaced by "_".
    assert conf["SRC_CERT"] == f"{CA_DIR}/certificates/_.{ZONE_A}.crt"
    assert conf["SRC_KEY"] == f"{CA_DIR}/certificates/_.{ZONE_A}.key"
    assert conf["DST_CERT"] == f"/etc/ssl/{ZONE_A}/fullchain.pem"
    assert conf["DST_KEY"] == f"/etc/ssl/{ZONE_A}/privkey.pem"
    # Per-entry overrides win over the role-level values.
    assert conf["RENEW_DAYS"] == "34"
    assert conf["KEY_GROUP"] == "1000"
    assert conf["RELOAD_SCRIPT"] == f"{CONFIG}/reload.d/{ZONE_A}.sh"
    # Non-default resolvers from the test inventory, so this cannot pass by
    # matching the role default.
    assert conf["DNS_RESOLVERS"] == "9.9.9.9:53 149.112.112.112:53"
    assert conf["DNS_PROVIDER"] == "infomaniak"


def test_bare_certificate_conf_falls_back_to_the_defaults(host):
    conf = _conf(host, ZONE_B)
    # domains defaults to the wildcard plus the apex.
    assert conf["DOMAINS"] == f"*.{ZONE_B} {ZONE_B}"
    assert conf["SRC_CERT"] == f"{CA_DIR}/certificates/_.{ZONE_B}.crt"
    # Role-level renew_days, not the other entry's override.
    assert conf["RENEW_DAYS"] == "45"
    # acme_client_default_key_group, not the other entry's "1000".
    assert conf["KEY_GROUP"] == "root"
    assert conf["KEY_MODE"] == "0640"
    assert conf["CERT_MODE"] == "0644"


def test_reload_script_exists_only_where_there_are_commands(host):
    script = host.file(f"{CONFIG}/reload.d/{ZONE_A}.sh")
    assert script.is_file
    assert script.mode == 0o700
    body = script.content_string
    assert "/containers/gitea/compose.yaml restart gitea" in body
    assert "/containers/vaultwarden/compose.yaml restart vaultwarden" in body

    # The bare entry has no reload commands, so it must have no script at all
    # rather than an empty one.
    assert not host.file(f"{CONFIG}/reload.d/{ZONE_B}.sh").exists


def test_renew_script(host):
    script = host.file("/usr/local/bin/acme-client-renew.sh")
    assert script.is_file
    assert script.mode == 0o700
    body = script.content_string
    # The run/renew split is the whole point of the script: `lego run` issues a
    # new certificate every time it is called.
    assert "renew --days" in body
    assert '"$LEGO_BIN" "$@" run' in body
    # The split-horizon fix.
    assert "--dns.resolvers" in body
    # Reads its settings from the per-zone conf rather than being templated per
    # certificate.
    assert f"{CONFIG}/certs/${{ZONE}}.conf" in body


def test_deploy_script(host):
    script = host.file("/usr/local/bin/acme-client-deploy.sh")
    assert script.is_file
    assert script.mode == 0o700
    body = script.content_string
    # Compares before copying, which is what makes it safe to call on every
    # converge.
    assert "cmp -s" in body
    # Mode and owner are set before the file becomes visible, then renamed.
    assert "install -o" in body
    assert "mv -f" in body
    # Consumer roles stat these paths without following links, so a symlink here
    # would break them.
    assert "ln -s" not in body


def test_service_unit(host):
    body = host.file("/etc/systemd/system/acme-client-renew@.service").content_string
    assert "Type=oneshot" in body
    assert "ExecStart=/usr/local/bin/acme-client-renew.sh %i" in body
    # Only the path of the token, never its value.
    assert (
        f"Environment=INFOMANIAK_ACCESS_TOKEN_FILE={CONFIG}/dns-api-token" in body
    )
    assert "Environment=INFOMANIAK_PROPAGATION_TIMEOUT=120" in body
    # Type=oneshot has no start timeout by default, and systemd skips a timer
    # trigger whose unit is still running - an unbounded hang would stop
    # renewals for good, quietly.
    assert re.search(r"^TimeoutStartSec=\S+", body, re.MULTILINE)
    # The timer pulls the service in, so it must not install itself. Anchored to
    # the start of a line: the unit explains its own missing [Install] in a
    # comment, and a bare substring check matches that instead.
    assert not re.search(r"^\[Install\]", body, re.MULTILINE)


def test_timer_unit(host):
    body = host.file("/etc/systemd/system/acme-client-renew@.timer").content_string
    assert re.search(r"^OnCalendar=\S", body, re.MULTILINE)
    assert re.search(r"^RandomizedDelaySec=\S", body, re.MULTILINE)
    # A host that was powered off when the timer came due catches up after boot.
    assert "Persistent=true" in body
    assert "Unit=acme-client-renew@%i.service" in body
    assert "WantedBy=timers.target" in body


def test_deploy_is_a_silent_noop_before_anything_is_issued(host):
    # lab.example.internal has no source files. A converge of a host whose first
    # run has not happened must do nothing quietly, not fail.
    result = host.run(f"/usr/local/bin/acme-client-deploy.sh {ZONE_B}")
    assert result.rc == 0
    assert result.stdout.strip() == ""
    assert not host.file(f"/etc/ssl/{ZONE_B}/fullchain.pem").exists


def test_deploy_places_the_pair_then_becomes_idempotent(host):
    # The full contract of the one script that touches key material, in the order
    # it matters. int.example.internal has placeholder sources from the converge.
    dst_cert = f"/etc/ssl/{ZONE_A}/fullchain.pem"
    dst_key = f"/etc/ssl/{ZONE_A}/privkey.pem"

    # Start from a defined state rather than assuming a pristine host: the
    # contract here is "deploys, then does nothing", which is only meaningful
    # from a known starting point. Without this the test passes on a fresh
    # converge and fails on a second `molecule verify`, for no real reason.
    host.run(f"rm -f {dst_cert} {dst_key}")

    first = host.run(f"/usr/local/bin/acme-client-deploy.sh {ZONE_A}")
    # The reload commands run docker, which is not installed here, so the script
    # is expected to fail - after the files are in place, which is the point of
    # the ordering.
    assert "acme-client: deployed" in first.stdout
    assert first.rc == 1
    assert "reload failed" in first.stderr
    # Both commands are attempted; one broken consumer does not hide the rest.
    assert first.stderr.count("reload failed") == 2

    cert = host.file(dst_cert)
    assert cert.is_file
    assert not cert.is_symlink
    assert cert.mode == 0o644
    assert cert.user == "root"

    key = host.file(dst_key)
    assert key.is_file
    assert not key.is_symlink
    # The per-entry key_group override, which is what a gitea host needs.
    assert key.gid == 1000
    assert key.mode == 0o640

    # No temporary files left behind.
    assert not host.file(f"{dst_cert}.new").exists
    assert not host.file(f"{dst_key}.new").exists

    # Second run: already current, so no copy, no reload, no output - and rc 0
    # even though the reload command would have failed, because it is not run.
    second = host.run(f"/usr/local/bin/acme-client-deploy.sh {ZONE_A}")
    assert second.rc == 0
    assert second.stdout.strip() == ""


def test_scripts_reject_an_unknown_zone(host):
    for script in ("acme-client-renew.sh", "acme-client-deploy.sh"):
        result = host.run(f"/usr/local/bin/{script} no-such.example.internal")
        assert result.rc == 2
        assert "no configuration" in result.stderr

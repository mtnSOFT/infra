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
    versions = host.run("ls /usr/local/lib/lego").stdout.split()
    assert len(versions) == 1
    version = versions[0]

    binary = host.file(f"/usr/local/lib/lego/{version}/lego")
    assert binary.is_file
    assert binary.user == "root"
    assert binary.group == "root"
    assert binary.mode == 0o755
    assert version in host.run(f"/usr/local/lib/lego/{version}/lego --version").stdout

    # No convenience symlink in /usr/local/bin: the units and scripts reference
    # the versioned path, so nothing needs one.
    assert not host.file("/usr/local/bin/lego").exists


def test_api_token_is_written_only_to_its_own_file(host):
    config_dir = host.file(CONFIG)
    assert config_dir.is_directory
    assert config_dir.mode == 0o700

    token = host.file(f"{CONFIG}/dns-api-token")
    assert token.is_file
    assert token.user == "root"
    assert token.group == "root"
    assert token.mode == 0o600

    # The value, compared loosely on purpose: testinfra's ansible backend reads
    # file content through a command, and Ansible strips trailing whitespace from
    # command output, so content_string cannot be trusted to show a trailing
    # newline. Comparing it exactly here passes under the podman backend and
    # fails under the ansible one, for a file that is byte-identical.
    assert token.content_string.strip() == TOKEN

    # So the property that actually matters is checked by byte count, which no
    # backend can distort: exactly the token plus one newline. lego strips one
    # "\n" and no other whitespace, so a second newline or a trailing space is
    # sent to the API verbatim and comes back as a 401 that explains nothing.
    size = int(host.run(f"wc -c < {CONFIG}/dns-api-token").stdout.strip())
    assert size == len(TOKEN) + 1


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


def test_deploy_directories(host):
    # CA_DIR is deliberately not asserted here: the role no longer creates it,
    # because lego creates its own --path tree with the same 0700. In this
    # scenario it exists only because converge.yml fabricates it for the
    # placeholders, so asserting it would just be testing the fixture.
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


def test_certificate_conf_holds_only_what_varies_per_zone(host):
    # The conf is deliberately tiny: everything identical across zones lives in
    # the renew script instead. If this grows again, something that should have
    # been static has been made per-certificate.
    assert set(_conf(host, ZONE_A)) == {"DOMAINS", "KEY_GROUP"}
    assert set(_conf(host, ZONE_B)) == {"DOMAINS", "KEY_GROUP"}


def test_overridden_certificate_conf(host):
    conf = _conf(host, ZONE_A)
    # All three SANs, in order, with the wildcard first - several wildcards in
    # one certificate is legitimate and must survive rendering.
    assert conf["DOMAINS"] == f"*.{ZONE_A} {ZONE_A} *.dev.{ZONE_A}"
    # Per-entry override, which is what a gitea host needs.
    assert conf["KEY_GROUP"] == "1000"


def test_bare_certificate_conf_falls_back_to_the_defaults(host):
    conf = _conf(host, ZONE_B)
    # domains defaults to the wildcard plus the apex.
    assert conf["DOMAINS"] == f"*.{ZONE_B} {ZONE_B}"
    # Not the other entry's "1000".
    assert conf["KEY_GROUP"] == "root"


def test_reload_scripts(host):
    script = host.file(f"{CONFIG}/reload.d/{ZONE_A}.sh")
    assert script.is_file
    assert script.mode == 0o700
    body = script.content_string
    assert "/containers/gitea/compose.yaml restart gitea" in body
    assert "/containers/vaultwarden/compose.yaml restart vaultwarden" in body

    # The bare entry gets a script too - always rendered, so there is no `when:`
    # and no task to clean up a leftover. It must simply contain no command.
    bare = host.file(f"{CONFIG}/reload.d/{ZONE_B}.sh")
    assert bare.is_file
    assert "docker" not in bare.content_string
    assert host.run(f"{CONFIG}/reload.d/{ZONE_B}.sh").rc == 0


def test_renew_script(host):
    script = host.file("/usr/local/bin/acme-client-renew.sh")
    assert script.is_file
    assert script.mode == 0o700
    body = script.content_string
    # lego v5 has a single "get or renew" command that decides for itself
    # whether the certificate is due, so there is one invocation and no branch.
    assert '"$LEGO_BIN" run "$@"' in body
    assert "--renew-days" in body
    # v5 flags are command flags: passing them before `run` fails with "flag
    # provided but not defined", and the v4 `renew` command no longer exists.
    assert "renew --days" not in body
    assert '"$LEGO_BIN" "$@" run' not in body
    # The credential lives here, not in the unit, so that a converge running
    # this script directly has it too - only the path, never the token value.
    assert (
        f"export INFOMANIAK_ACCESS_TOKEN_FILE={CONFIG}/dns-api-token" in body
    )
    # Storage name pinned, so the deploy paths do not depend on lego deriving a
    # filename from the domain list.
    assert '--cert.name "$ZONE"' in body
    # Makes an edit to `domains` actually take effect.
    assert "--force-cert-domains" in body
    # The split-horizon fix.
    assert "--dns.resolvers" in body
    # Reads what varies from the per-zone conf rather than being templated per
    # certificate.
    assert f"{CONFIG}/certs/${{ZONE}}.conf" in body

    # Everything identical across zones is baked in here, not repeated in each
    # conf. Non-default values from the test inventory, so these cannot pass by
    # matching a role default.
    assert "EMAIL='acme-test@example.internal'" in body
    assert "SERVER='https://acme-v02.api.letsencrypt.org/directory'" in body
    assert "RESOLVERS='9.9.9.9:53 149.112.112.112:53'" in body
    assert "RENEW_DAYS=30" in body
    assert f"LEGO_DIR='{CA_DIR}'" in body
    assert "--dns infomaniak" in body
    assert "--key-type ec256" in body


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
    # No Environment= at all: the credential is exported by the script, so that
    # it reaches lego identically here and when a converge runs the script
    # directly. Setting it only here is what broke the converge path.
    assert not re.search(r"^Environment=", body, re.MULTILINE)
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


def test_lego_gets_its_credential_when_run_outside_systemd(host):
    # Regression test. The credential used to be set only by the systemd unit,
    # but an Ansible converge runs this script directly - so lego got no
    # credentials there and failed with "some credentials information are
    # missing", and because lego logs to stdout the role reported an empty
    # error. Stub the binary with one that dumps its environment and check what
    # lego would actually receive.
    stub = "/tmp/legostub.sh"
    host.run(f"printf '#!/bin/sh\\nenv\\nexit 7\\n' > {stub} && chmod 0755 {stub}")
    host.run(
        f"sed 's#^LEGO_BIN=.*#LEGO_BIN={stub}#' /usr/local/bin/acme-client-renew.sh"
        " > /tmp/renew-probe.sh && chmod 0755 /tmp/renew-probe.sh"
    )
    # env -i: an empty environment, the worst case the converge path can present.
    result = host.run(f"env -i /tmp/renew-probe.sh {ZONE_A}")

    token_file = f"{CONFIG}/dns-api-token"
    assert f"INFOMANIAK_ACCESS_TOKEN_FILE={token_file}" in result.stdout
    # ...and the path it points at has to be real, or lego fails the same way.
    assert host.file(token_file).exists
    # The token value itself never enters the environment - only its path.
    assert TOKEN not in result.stdout

    host.run(f"rm -f {stub} /tmp/renew-probe.sh")


def test_scripts_reject_an_unknown_zone(host):
    for script in ("acme-client-renew.sh", "acme-client-deploy.sh"):
        result = host.run(f"/usr/local/bin/{script} no-such.example.internal")
        assert result.rc == 2
        assert "no configuration" in result.stderr

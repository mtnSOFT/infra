ACME_HOME = "/root/.acme.sh"
SRC = "/usr/local/src/acme.sh"

# Derived from the first entry of acme_client_domains with the wildcard
# stripped. Spelled out rather than taken from the role, so this independently
# checks that derivation - acme.sh's own state directory is literally named
# "*.int.example.internal_ecc", which is the path nobody wants to consume.
CERT_DIR = "/etc/ssl/acme/int.example.internal"


def _root_crontab(host):
    return host.check_output("crontab -l -u root")


def test_acme_sh_is_installed_from_the_pinned_checkout(host):
    # The installer runs from this checkout, not piped from get.acme.sh, so the
    # version that ends up handling the DNS API token is the reviewed one.
    assert host.file(f"{SRC}/acme.sh").exists

    acme = host.file(f"{ACME_HOME}/acme.sh")
    assert acme.exists
    assert acme.user == "root"
    assert acme.mode & 0o100

    # Asserted on the installed copy rather than on the checkout: that is the
    # one cron runs, and it is what proves the install step used the checkout.
    assert "v3.1.4" in host.check_output(f"{ACME_HOME}/acme.sh --version")


def test_account_config_carries_the_contact(host):
    # acme.sh writes the contact given to --accountemail here and reuses it for
    # every certificate, so an empty value means the install step ran without
    # the variable reaching it.
    conf = host.file(f"{ACME_HOME}/account.conf")
    assert conf.exists
    assert conf.mode == 0o600
    assert "acme-test@example.internal" in conf.content_string


def test_certificate_directory_is_created_before_anything_is_issued(host):
    # Created unconditionally, so the path a consuming role points at exists
    # from the first converge - this scenario issues nothing.
    cert_dir = host.file(CERT_DIR)
    assert cert_dir.is_directory
    assert cert_dir.user == "root"
    assert cert_dir.group == "root"
    assert cert_dir.mode == 0o755

    assert not host.file(f"{CERT_DIR}/fullchain.pem").exists
    assert not host.file(f"{CERT_DIR}/key.pem").exists


def test_renewal_cron_job(host):
    crontab = _root_crontab(host)
    assert "acme.sh renew certificates" in crontab
    assert f"{ACME_HOME}/acme.sh --cron" in crontab


def test_acme_sh_installed_no_cron_job_of_its_own(host):
    # --install adds its own daily entry unless --nocron is passed. Two entries
    # would mean the role's schedule is not the one in effect, and removing the
    # role's cron job would leave a renewal running behind its back.
    acme_lines = [
        line
        for line in _root_crontab(host).splitlines()
        if "acme.sh" in line and not line.startswith("#")
    ]
    assert len(acme_lines) == 1

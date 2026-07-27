import yaml

BASE = "/containers/pihole"


def _load(host, path):
    """Parse a rendered config file - also proves the template emits valid YAML."""
    return yaml.safe_load(host.file(path).content_string)


def _pihole_password(host):
    """The rendered password, read back from .env rather than hardcoded here."""
    prefix = "PIHOLE_WEBPASSWORD="
    lines = [
        line for line in host.file(f"{BASE}/.env").content_string.splitlines()
        if line.startswith(prefix)
    ]
    assert len(lines) == 1, lines
    return lines[0][len(prefix):]


def _pihole_env(host):
    return _load(host, f"{BASE}/compose.yaml")["services"]["pihole"]["environment"]


def test_project_directory(host):
    project = host.file(BASE)
    assert project.is_directory
    assert project.user == "root"
    assert project.group == "root"
    assert project.mode == 0o750


def test_persistent_config_directory(host):
    etc_pihole = host.file(f"{BASE}/etc-pihole")
    assert etc_pihole.is_directory
    assert etc_pihole.user == "root"
    assert etc_pihole.group == "root"
    assert etc_pihole.mode == 0o755


def test_env_file_holds_the_secret_and_is_not_world_readable(host):
    env = host.file(f"{BASE}/.env")
    assert env.exists
    assert env.user == "root"
    assert env.mode == 0o600

    password = _pihole_password(host)
    assert password
    assert "{{" not in password


def test_compose_file(host):
    compose = host.file(f"{BASE}/compose.yaml")
    assert compose.mode == 0o644
    # compose.yaml is world-readable, so the password must not be inlined here
    assert _pihole_password(host) not in compose.content_string

    services = _load(host, f"{BASE}/compose.yaml")["services"]
    assert set(services) == {"pihole"}

    pihole = services["pihole"]
    # Host networking: FTL binds the host's interfaces, no published ports
    assert pihole["network_mode"] == "host"
    assert "ports" not in pihole
    assert pihole["restart"] == "unless-stopped"
    assert pihole["volumes"] == [f"{BASE}/etc-pihole:/etc/pihole"]
    assert pihole["environment"]["FTLCONF_webserver_api_password"] == (
        "${PIHOLE_WEBPASSWORD}"
    )


def test_local_dns_records(host):
    # "IP HOSTNAME" entries joined with ";", in the order they were declared.
    # The template emits this key unconditionally - an empty pihole_dns_records
    # renders an empty value, which FTL reads as an empty array, so dropping a
    # record from inventory actually removes it. That branch is not reachable in
    # this scenario, which needs records present to assert the format.
    assert _pihole_env(host)["FTLCONF_dns_hosts"] == (
        "10.10.0.1 vpn.example.com;10.10.0.20 nas.example.com"
    )


def test_dns_listens_on_the_configured_interfaces_only(host):
    env = _pihole_env(host)
    # No wildcard bind, so Pi-hole can share :53 with another resolver
    assert env["FTLCONF_dns_listeningMode"] == "NONE"

    lines = env["FTLCONF_misc_dnsmasq_lines"].splitlines()
    assert "bind-dynamic" in lines
    assert "interface=eth0" in lines
    assert "interface=wg0" in lines


def test_web_admin_is_bound_to_one_ip(host):
    # 80 redirects to TLS, 443 is TLS - both on pihole_web_ip only
    assert _pihole_env(host)["FTLCONF_webserver_port"] == (
        "10.10.0.1:80o,10.10.0.1:443os"
    )


def test_upstreams_come_from_the_inventory(host):
    # dns1 / dns2 in inventories/test/group_vars/all/vars.yml
    assert _pihole_env(host)["FTLCONF_dns_upstreams"] == "8.8.8.8;8.8.4.4"


def test_unused_services_are_disabled(host):
    env = _pihole_env(host)
    assert env["FTLCONF_dhcp_active"] == "false"
    assert env["FTLCONF_ntp_ipv4_active"] == "false"
    assert env["FTLCONF_ntp_ipv6_active"] == "false"
    assert env["FTLCONF_ntp_sync_active"] == "false"

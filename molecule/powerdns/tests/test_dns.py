import os
import pytest
import testinfra.utils.ansible_runner

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ['MOLECULE_INVENTORY_FILE']).get_hosts('all')

def test_pdns_service_running(host):
    """Check if PowerDNS service is running"""
    pdns = host.service("pdns")
    assert pdns.is_running
    assert pdns.is_enabled


def test_pdns_listening_on_port(host):
    """Check if PowerDNS is listening on port 5300"""
    socket = host.socket("tcp://127.0.0.1:5300")
    assert socket.is_listening


def test_dns_zone_example_local(host):
    """Test DNS query for example.local zone"""
    # Query the SOA record for the zone
    cmd = host.run("dig @127.0.0.1 -p 5300 example.local SOA +short")
    assert cmd.rc == 0
    assert "ns1.example.local" in cmd.stdout or "example.local" in cmd.stdout


def test_dns_query_ns_record(host):
    """Test DNS NS record query"""
    cmd = host.run("dig @127.0.0.1 -p 5300 example.local NS +short")
    assert cmd.rc == 0
    assert "ns1.example.local" in cmd.stdout


def test_dns_query_manual_record(host):
    """Test DNS query for the manually configured A record.

    The converge play sets pdns_records_manual to www.example.local -> 192.168.1.100.
    (Auto-generated records from inventory hosts are not tested here: no test host
    carries an IP, so pdns_auto_inventory_records is disabled for this scenario.)
    """
    cmd = host.run("dig @127.0.0.1 -p 5300 www.example.local A +short")
    assert cmd.rc == 0
    assert "192.168.1.100" in cmd.stdout


def test_pdns_database_exists(host):
    """Check if PowerDNS SQLite database exists"""
    db_file = host.file("/var/lib/powerdns/pdns.sqlite3")
    assert db_file.exists
    assert db_file.user == "pdns"
    assert db_file.group == "pdns"


def test_pdns_config_file(host):
    """Check if PowerDNS config file exists and is valid"""
    config = host.file("/etc/powerdns/pdns.conf")
    assert config.exists
    assert config.contains("gsqlite3")
    assert config.contains("local-port=5300")

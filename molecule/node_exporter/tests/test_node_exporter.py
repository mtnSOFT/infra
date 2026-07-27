SERVICE = "prometheus-node-exporter"
DEFAULTS_FILE = "/etc/default/prometheus-node-exporter"

# Must match molecule/node_exporter/converge.yml
BIND = "127.0.0.1"
PORT = 9100


def test_package_installed(host):
    assert host.package(SERVICE).is_installed


def test_service_running_and_enabled(host):
    service = host.service(SERVICE)
    assert service.is_enabled
    assert service.is_running


def test_arguments_rendered(host):
    defaults = host.file(DEFAULTS_FILE)
    assert defaults.exists
    assert defaults.user == "root"
    assert defaults.mode == 0o644
    # bind address and port from the role, plus the extra arg from converge.yml
    assert defaults.contains(f"--web.listen-address={BIND}:{PORT}")
    assert defaults.contains("--log.level=warn")


def test_listening_on_the_configured_address(host):
    assert host.socket(f"tcp://{BIND}:{PORT}").is_listening


def test_metrics_endpoint_serves_node_metrics(host):
    # The real end-to-end check: the exporter is up and actually exporting.
    result = host.run(f"curl -sf http://{BIND}:{PORT}/metrics")
    assert result.rc == 0
    assert "node_cpu_seconds_total" in result.stdout


def test_unit_reads_the_defaults_file(host):
    # The role configures ARGS instead of overriding the unit; if the packaging
    # ever stops sourcing this file, that assumption is silently broken.
    unit = host.run(f"systemctl cat {SERVICE}")
    assert unit.rc == 0
    assert DEFAULTS_FILE in unit.stdout
    assert "$ARGS" in unit.stdout

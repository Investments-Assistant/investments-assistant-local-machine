"""Offline Compose validation with synthetic interpolation values and no env-file secrets."""

import json
from pathlib import Path
import argparse
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fixture = root / ".qa" / "compose-validation.env"
    fixture.parent.mkdir(exist_ok=True, mode=0o700)

    def native(path):
        if args.docker.endswith(".exe"):
            return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
        return str(path)

    results = []
    for label, bind in [("default_loopback", None), ("explicit_fixture_lan", "192.168.50.10")]:
        fixture.write_text(
            "POSTGRES_PASSWORD=synthetic-compose-only\n"
            + (f"LOCAL_BIND_ADDRESS={bind}\n" if bind else "")
        )
        fixture.chmod(0o600)
        result = subprocess.run(
            [
                args.docker,
                "compose",
                "--env-file",
                native(fixture),
                "-f",
                native(root / "docker-compose.yml"),
                "config",
                "--no-env-resolution",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        model = json.loads(result.stdout)
        services = model["services"]
        ports = services["nginx"]["ports"]
        assert {p["host_ip"] for p in ports} == {bind or "127.0.0.1"}
        assert {str(p["published"]) for p in ports} == {"8080", "8443"}
        assert not services["postgres"].get("ports") and not services["app"].get("ports")
        peer = services["nginx"]["networks"]["internal"]["ipv4_address"]
        assert services["app"]["environment"]["TRUSTED_PROXY_IPS"] == peer + "/32"
        import ipaddress

        subnet = model["networks"]["internal"]["ipam"]["config"][0]["subnet"]
        assert ipaddress.ip_address(peer) in ipaddress.ip_network(subnet)
        for service in services.values():
            assert service["logging"]["options"] == {"max-file": "3", "max-size": "10m"}
        results.append(
            dict(
                profile=label,
                nginx_ports=ports,
                private_services_unpublished=True,
                trusted_proxy=peer,
                log_rotation="10m x 3 per service",
            )
        )
    payload = dict(
        status="PASS", tier="compose-config-only", daemon_started=False, profiles=results
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()

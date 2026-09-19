"""Trust forwarded headers only from explicitly configured proxy peers."""

import ipaddress


def trusted_proxy(request, settings) -> bool:
    if settings.trust_proxy_headers is not True or not request.client:
        return False
    configured = getattr(settings, "trusted_proxy_ips", "")
    if not isinstance(configured, str):
        return False
    try:
        peer = ipaddress.ip_address(request.client.host)
        networks = [
            ipaddress.ip_network(value.strip()) for value in configured.split(",") if value.strip()
        ]
        return any(peer in network for network in networks)
    except ValueError:
        return False

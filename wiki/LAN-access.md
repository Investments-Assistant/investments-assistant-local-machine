# LAN access

The local-machine deployment is LAN-only. Nginx is the ingress point, and the
Windows Defender Firewall is the host-level enforcement point. PostgreSQL and
FastAPI are not published to the host.

## Current network values

The detected Wi-Fi network is:

```text
Host IPv4: 192.168.1.242
LAN CIDR:  192.168.1.0/24
Hostname:  investmentsassistant.home.arpa
HTTPS:     https://investmentsassistant.home.arpa:8443
```

Reserve `192.168.1.242` for this computer in the router's DHCP settings. If the
network changes, regenerate the Nginx allow-list and update `.env`:

```bash
make LAN_CIDR=192.168.50.0/24 local-lan-config
# Change ALLOWED_IPS in .env to include the same LAN CIDR, then restart.
```

## Free local DNS

On the router's LAN/DHCP/DNS page, add this local DNS record:

```text
investmentsassistant.home.arpa -> 192.168.1.242
```

`home.arpa` is intended for home-network DNS. Make sure clients receive the
router as their DNS server through DHCP; devices manually configured to use
only public DNS will not see this private record. If the router cannot create
local records, add the same record to a Pi-hole or another DNS server already
used by all LAN clients.

## Apply the Windows firewall boundary

Open **PowerShell as Administrator** on the Windows host and run the script from
the checkout. It enables Windows Firewall, sets default inbound traffic to
`Block`, allows only TCP 8080/8443 from `192.168.1.0/24`, and narrows Docker
Desktop's broad backend rule if it exists:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_windows_firewall.ps1 `
  -LanCidr 192.168.1.0/24
```

Do not use `-SkipProfileEnforcement` unless a centrally managed firewall policy
already guarantees enabled profiles with default inbound blocking.

Do not forward ports 8080 or 8443 on the router, and keep UPnP port mapping
disabled for this host.

## Generate and trust the hostname certificate

Regenerate the local certificate with the hostname in its Subject Alternative
Name, then restart Nginx:

```bash
make LOCAL_HOSTNAME=investmentsassistant.home.arpa local-tls
make local-restart
```

Install `config/nginx/certs/selfsigned.crt` as a trusted root certificate on
each client device. The exact UI varies:

- Windows: import it into **Trusted Root Certification Authorities**.
- iOS/iPadOS: install the profile, then enable it under **Settings → General →
  About → Certificate Trust Settings**.
- Android: install it under the device's credential/security settings. Browser
  trust varies by Android version and browser.

This is a private self-signed certificate. It is suitable for this LAN-only
deployment only after every intended client explicitly trusts the certificate.

## Validate the boundary

From a LAN device, open:

```text
https://investmentsassistant.home.arpa:8443
```

From the host, check:

```bash
make local-ready
docker compose ps
docker compose logs --tail=100 nginx
```

Test from a device on cellular data or another network. It should time out at
the Windows firewall/router boundary. A request that reaches Nginx from a
non-allow-listed address must receive `403`; neither the app nor PostgreSQL is
directly reachable.

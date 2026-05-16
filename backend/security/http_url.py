"""Validate outbound HTTP URLs to reduce SSRF from flow ``http_url`` and integrations."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def _host_resolves_only_to_global_ips(host: str, port: int) -> str | None:
    """After literal IP checks, ensure DNS (or resolver) does not map host to loopback/private."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        return f"URL host does not resolve: {host} ({exc})"
    if not infos:
        return f"URL host has no resolved addresses: {host}"
    for _fam, _socktype, _proto, _canon, sockaddr in infos:
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if not ip.is_global:
            return f"URL resolves to non-global address {ip} for host {host!r}"
    return None


def validate_public_http_url(url: str) -> str | None:
    """Return an error message, or ``None`` if ``url`` is http(s) and host is safe (literal + DNS)."""
    u = (url or "").strip()
    if not u:
        return "URL is empty"
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        return f"URL scheme must be http or https, got: {parsed.scheme!r}"
    host = parsed.hostname
    if not host:
        return "URL has no host"
    hl = host.lower()
    if hl == "localhost" or hl.endswith(".localhost"):
        return "URL must not target localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        ip = ipaddress.ip_address(hl)
        if not ip.is_global:
            return f"URL must not target loopback, private, link-local, or reserved address: {host}"
        return None
    except ValueError:
        pass

    if hl.isdigit():
        try:
            ip = ipaddress.ip_address(int(hl))
        except (ValueError, OverflowError):
            pass
        else:
            if not ip.is_global:
                return f"URL must not target loopback, private, link-local, or reserved address: {host}"
            return None

    return _host_resolves_only_to_global_ips(hl, port)


def validate_jira_cloud_base_url(base_url: str) -> str | None:
    """Jira Cloud only: ``https://<tenant>.atlassian.net`` (no arbitrary hosts for credential exfil)."""
    pub = validate_public_http_url((base_url or "").strip().rstrip("/"))
    if pub:
        return pub
    parsed = urlparse((base_url or "").strip().rstrip("/"))
    if parsed.scheme != "https":
        return "Jira base_url must use https"
    host = (parsed.hostname or "").lower()
    labels = host.split(".")
    if len(labels) != 3 or labels[-2] != "atlassian" or labels[-1] != "net":
        return "Jira base_url must be Jira Cloud: https://<your-tenant>.atlassian.net"
    tenant = labels[0]
    if not tenant or len(tenant) > 63:
        return "Jira Cloud tenant label is missing or too long"
    if not tenant.replace("-", "").isalnum():
        return "Jira Cloud tenant label must be alphanumeric (hyphens allowed)"
    if tenant[0] == "-" or tenant[-1] == "-":
        return "Jira Cloud tenant label must not start or end with a hyphen"
    return None

"""Unit tests for outbound URL allowlists (SSRF mitigation)."""
from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from backend.security.http_url import validate_jira_cloud_base_url, validate_public_http_url


_GLOBAL_V4 = (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443))


class HttpUrlValidationTests(unittest.TestCase):
    def test_blocks_decimal_integer_loopback_host(self) -> None:
        self.assertIsNotNone(validate_public_http_url("http://2130706433/"))

    def test_blocks_loopback_literal(self) -> None:
        self.assertIsNotNone(validate_public_http_url("http://127.0.0.1/foo"))

    def test_blocks_private_ipv4(self) -> None:
        self.assertIsNotNone(validate_public_http_url("http://192.168.1.1/"))

    @patch("backend.security.http_url.socket.getaddrinfo", return_value=[_GLOBAL_V4])
    def test_allows_hostname_when_dns_returns_global(self, _mock: object) -> None:
        self.assertIsNone(validate_public_http_url("https://example.invalid/path"))

    @patch(
        "backend.security.http_url.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))],
    )
    def test_blocks_when_dns_yields_loopback(self, _mock: object) -> None:
        self.assertIsNotNone(validate_public_http_url("http://looks-public.example/path"))

    def test_blocks_non_http_scheme(self) -> None:
        self.assertIsNotNone(validate_public_http_url("file:///etc/passwd"))


class JiraCloudUrlValidationTests(unittest.TestCase):
    @patch("backend.security.http_url.socket.getaddrinfo", return_value=[_GLOBAL_V4])
    def test_allows_tenant_atlassian_net(self, _mock: object) -> None:
        self.assertIsNone(validate_jira_cloud_base_url("https://myteam.atlassian.net"))

    @patch("backend.security.http_url.socket.getaddrinfo", return_value=[_GLOBAL_V4])
    def test_rejects_non_atlassian_host(self, _mock: object) -> None:
        self.assertIsNotNone(validate_jira_cloud_base_url("https://evil.example.com"))

    @patch("backend.security.http_url.socket.getaddrinfo", return_value=[_GLOBAL_V4])
    def test_rejects_multi_label_tenant_host(self, _mock: object) -> None:
        self.assertIsNotNone(validate_jira_cloud_base_url("https://a.b.atlassian.net"))

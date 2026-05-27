import json
import ipaddress
import os
import socket
from typing import Mapping
from urllib.parse import urlparse
import dashscope

from dashscope.common.error import (
    AuthenticationError,
    InvalidParameter,
    RequestFailure,
    ServiceUnavailableError,
    UnsupportedHTTPMethod,
    UnsupportedModel,
)

from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

DEFAULT_HTTP_BASE_ADDRESS = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_WS_BASE_ADDRESS = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
INTL_HTTP_BASE_ADDRESS = "https://dashscope-intl.aliyuncs.com/api/v1"
INTL_WS_BASE_ADDRESS = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
TRUSTED_ENDPOINT_HOST_SUFFIXES = (
    "aliyun.com",
    "aliyuncs.com",
    "ey.net",
)
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
}
BLOCKED_IPS = {
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("169.254.169.254"),
}
ALLOWED_EXTRA_HEADERS = {
    "x-dashscope-euid",
}
MAX_EXTRA_HEADER_VALUE_LENGTH = 4096


def _clean_url(url: str | None) -> str:
    return str(url or "").strip().rstrip("/")


def _normalize_hostname(hostname: str) -> str:
    return hostname.strip().rstrip(".").lower()


def _get_additional_trusted_endpoint_suffixes() -> tuple[str, ...]:
    extra_suffixes = []
    for raw_item in os.getenv("TONGYI_ALLOWED_ENDPOINT_HOSTS", "").split(","):
        normalized_item = _normalize_hostname(raw_item)
        if normalized_item:
            extra_suffixes.append(normalized_item)
    return tuple(extra_suffixes)


def _is_trusted_endpoint_host(hostname: str) -> bool:
    trusted_suffixes = TRUSTED_ENDPOINT_HOST_SUFFIXES + _get_additional_trusted_endpoint_suffixes()
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in trusted_suffixes
    )


def _raise_if_forbidden_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address, field_name: str) -> None:
    if (
        ip_obj in BLOCKED_IPS
        or ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    ):
        raise ValueError(f"{field_name} must not point to a private, local, or metadata address")


def _resolve_hostname_ips(hostname: str, field_name: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        addr_infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as ex:
        raise ValueError(f"{field_name} host could not be resolved") from ex

    resolved_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for _, _, _, _, sockaddr in addr_infos:
        resolved_ips.add(ipaddress.ip_address(sockaddr[0]))

    if not resolved_ips:
        raise ValueError(f"{field_name} host could not be resolved")
    return resolved_ips


def _validate_network_location(
    hostname: str,
    field_name: str,
    *,
    require_trusted_endpoint_host: bool,
) -> None:
    normalized_host = _normalize_hostname(hostname)
    if not normalized_host:
        raise ValueError(f"{field_name} must include a host")

    if normalized_host in BLOCKED_HOSTNAMES:
        raise ValueError(f"{field_name} must not target local or metadata hosts")

    try:
        host_ip = ipaddress.ip_address(normalized_host)
    except ValueError:
        host_ip = None

    if host_ip is not None:
        if require_trusted_endpoint_host:
            raise ValueError(f"{field_name} must use a trusted gateway domain instead of a raw IP")
        _raise_if_forbidden_ip(host_ip, field_name)
        return

    if require_trusted_endpoint_host and not _is_trusted_endpoint_host(normalized_host):
        raise ValueError(
            f"{field_name} must use a trusted gateway host suffix such as aliyun.com, aliyuncs.com, or ey.net"
        )

    if not _is_trusted_endpoint_host(normalized_host):
        for resolved_ip in _resolve_hostname_ips(normalized_host, field_name):
            _raise_if_forbidden_ip(resolved_ip, field_name)


def _normalize_url(
    url: str | None,
    field_name: str,
    *,
    allowed_schemes: tuple[str, ...],
    require_trusted_endpoint_host: bool,
    allow_query: bool,
) -> str:
    normalized = _clean_url(url)
    if not normalized:
        raise ValueError(f"{field_name} is required")

    parsed = urlparse(normalized)
    if parsed.scheme not in allowed_schemes:
        raise ValueError(
            f"{field_name} must start with {', '.join(f'{scheme}://' for scheme in allowed_schemes)}"
        )
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not include user info")
    if parsed.fragment:
        raise ValueError(f"{field_name} must not include a URL fragment")
    if not allow_query and parsed.query:
        raise ValueError(f"{field_name} must not include query parameters")
    _validate_network_location(
        parsed.hostname or "",
        field_name,
        require_trusted_endpoint_host=require_trusted_endpoint_host,
    )
    return normalized


def _normalize_dashscope_endpoint_url(url: str | None, field_name: str) -> str:
    return _normalize_url(
        url,
        field_name,
        allowed_schemes=("http", "https", "ws", "wss"),
        require_trusted_endpoint_host=True,
        allow_query=False,
    )


def _normalize_http_url(url: str | None, field_name: str) -> str:
    return _normalize_url(
        url,
        field_name,
        allowed_schemes=("http", "https"),
        require_trusted_endpoint_host=True,
        allow_query=False,
    )


def normalize_external_file_url(url: str | None, field_name: str = "url") -> str:
    return _normalize_url(
        url,
        field_name,
        allowed_schemes=("http", "https"),
        require_trusted_endpoint_host=False,
        allow_query=True,
    )


def sanitize_extra_headers(headers: Mapping[str, object]) -> dict[str, str]:
    sanitized_headers: dict[str, str] = {}
    for raw_key, raw_value in headers.items():
        key = str(raw_key).strip().lower()
        if isinstance(raw_value, (dict, list)):
            value = json.dumps(raw_value, separators=(",", ":"))
        else:
            value = str(raw_value).strip()

        if key not in ALLOWED_EXTRA_HEADERS:
            raise ValueError(f"Unsupported extra header: {raw_key}")
        if not value:
            raise ValueError(f"Extra header {raw_key} must not be empty")

        value = value.replace("\r", "").replace("\n", "")
        if len(value) > MAX_EXTRA_HEADER_VALUE_LENGTH:
            raise ValueError(f"Extra header {raw_key} is too long")

        sanitized_headers[key] = value
    return sanitized_headers


def get_dashscope_base_address(credentials: Mapping[str, str]) -> str:
    return _normalize_dashscope_endpoint_url(
        credentials.get("dashscope_endpoint_url", ""),
        "dashscope_endpoint_url",
    )


def get_compatible_base_url(credentials: Mapping[str, str]) -> str:
    compatible_endpoint_url = _clean_url(credentials.get("compatible_endpoint_url"))
    if compatible_endpoint_url:
        return _normalize_http_url(compatible_endpoint_url, "compatible_endpoint_url")
    return _normalize_http_url(credentials.get("dashscope_endpoint_url"), "dashscope_endpoint_url")


def get_compatible_api_key(credentials: Mapping[str, str]) -> str:
    compatible_api_key = str(credentials.get("compatible_api_key") or "").strip()
    if compatible_api_key:
        return compatible_api_key
    return credentials["dashscope_api_key"]


def get_http_base_address(credentials: Mapping[str, str]) -> str:
    return get_dashscope_base_address(credentials)


def configure_dashscope_http_base_url(credentials: Mapping[str, str]) -> str:
    base_address = _normalize_http_url(
        credentials.get("dashscope_endpoint_url"),
        "dashscope_endpoint_url",
    )
    os.environ["DASHSCOPE_HTTP_BASE_URL"] = base_address
    dashscope.base_http_api_url = base_address
    return base_address


def get_ws_base_address(credentials: Mapping[str, str]) -> str:
    return get_dashscope_base_address(credentials)


class _CommonTongyi:
    @staticmethod
    def _to_credential_kwargs(credentials: dict) -> dict:
        credentials_kwargs = {
            "dashscope_api_key": credentials["dashscope_api_key"],
        }

        return credentials_kwargs

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: [
                RequestFailure,
            ],
            InvokeServerUnavailableError: [
                ServiceUnavailableError,
            ],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [
                AuthenticationError,
            ],
            InvokeBadRequestError: [
                InvalidParameter,
                UnsupportedModel,
                UnsupportedHTTPMethod,
            ],
        }

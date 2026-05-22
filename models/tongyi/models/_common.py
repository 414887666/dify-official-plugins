import os
from typing import Mapping

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


def _clean_url(url: str | None) -> str:
    return str(url or "").strip().rstrip("/")


def _normalize_dashscope_endpoint_url(url: str | None, field_name: str) -> str:
    normalized = _clean_url(url)
    if not normalized:
        raise ValueError(f"{field_name} is required")

    if not normalized.startswith(("http://", "https://", "ws://", "wss://")):
        raise ValueError(f"{field_name} must start with http://, https://, ws://, or wss://")
    return normalized


def _normalize_http_url(url: str | None, field_name: str) -> str:
    normalized = _clean_url(url)
    if not normalized:
        raise ValueError(f"{field_name} is required")

    if not normalized.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")
    return normalized


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

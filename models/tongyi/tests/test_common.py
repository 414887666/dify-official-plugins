import pytest

from models._common import (
    get_compatible_api_key,
    get_compatible_base_url,
    get_dashscope_base_address,
    get_ws_base_address,
)


def test_get_dashscope_base_address_requires_endpoint() -> None:
    with pytest.raises(ValueError, match="dashscope_endpoint_url is required"):
        get_dashscope_base_address({"dashscope_api_key": "key"})


def test_get_dashscope_base_address_normalizes_endpoint() -> None:
    assert (
        get_dashscope_base_address(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": " https://llmapi.example.com/base/v1/ ",
            }
        )
        == "https://llmapi.example.com/base/v1"
    )


def test_get_dashscope_base_address_accepts_websocket_endpoint() -> None:
    assert (
        get_dashscope_base_address(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": " wss://llmapi.example.com/base/v1/ ",
            }
        )
        == "wss://llmapi.example.com/base/v1"
    )


def test_get_dashscope_base_address_rejects_unsupported_protocol() -> None:
    with pytest.raises(ValueError, match="must start with http://, https://, ws://, or wss://"):
        get_dashscope_base_address(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": "ftp://llmapi.example.com/base/v1",
            }
        )


def test_get_compatible_base_url_defaults_to_dashscope_endpoint() -> None:
    assert (
        get_compatible_base_url(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": "https://llmapi.example.com/base/v1/",
            }
        )
        == "https://llmapi.example.com/base/v1"
    )


def test_get_compatible_base_url_treats_blank_value_as_missing() -> None:
    assert (
        get_compatible_base_url(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": "https://llmapi.example.com/base/v1",
                "compatible_endpoint_url": "   ",
            }
        )
        == "https://llmapi.example.com/base/v1"
    )


def test_get_compatible_base_url_uses_explicit_endpoint() -> None:
    assert (
        get_compatible_base_url(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": "https://dashscope.example.com/api/v1",
                "compatible_endpoint_url": " https://compatible.example.com/v1/ ",
            }
        )
        == "https://compatible.example.com/v1"
    )


def test_get_compatible_base_url_rejects_websocket_endpoint() -> None:
    with pytest.raises(ValueError, match="must start with http:// or https://"):
        get_compatible_base_url(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": "https://dashscope.example.com/api/v1",
                "compatible_endpoint_url": "wss://compatible.example.com/v1",
            }
        )


def test_get_compatible_base_url_rejects_websocket_dashscope_fallback() -> None:
    with pytest.raises(ValueError, match="must start with http:// or https://"):
        get_compatible_base_url(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": "wss://llmapi.example.com/asr/v1",
            }
        )


def test_get_ws_base_address_reuses_dashscope_endpoint() -> None:
    assert (
        get_ws_base_address(
            {
                "dashscope_api_key": "key",
                "dashscope_endpoint_url": "wss://llmapi.example.com/asr/v1/",
            }
        )
        == "wss://llmapi.example.com/asr/v1"
    )


def test_get_compatible_api_key_defaults_to_dashscope_api_key() -> None:
    assert get_compatible_api_key({"dashscope_api_key": "dashscope-key"}) == "dashscope-key"


def test_get_compatible_api_key_treats_blank_value_as_missing() -> None:
    assert (
        get_compatible_api_key(
            {
                "dashscope_api_key": "dashscope-key",
                "compatible_api_key": "   ",
            }
        )
        == "dashscope-key"
    )


def test_get_compatible_api_key_uses_explicit_key() -> None:
    assert (
        get_compatible_api_key(
            {
                "dashscope_api_key": "dashscope-key",
                "compatible_api_key": "compatible-key",
            }
        )
        == "compatible-key"
    )

from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.feature_flag import FeatureFlag
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    key: str,
    *,
    enabled: bool,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["enabled"] = enabled

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/admin/feature-flags/{key}/toggle".format(
            key=quote(str(key), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FeatureFlag | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FeatureFlag.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[FeatureFlag | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    key: str,
    *,
    client: AuthenticatedClient,
    enabled: bool,
) -> Response[FeatureFlag | HTTPValidationError]:
    """Toggle Feature Flag

    Args:
        key (str):
        enabled (bool):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeatureFlag | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        key=key,
        enabled=enabled,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    key: str,
    *,
    client: AuthenticatedClient,
    enabled: bool,
) -> FeatureFlag | HTTPValidationError | None:
    """Toggle Feature Flag

    Args:
        key (str):
        enabled (bool):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeatureFlag | HTTPValidationError
    """

    return sync_detailed(
        key=key,
        client=client,
        enabled=enabled,
    ).parsed


async def asyncio_detailed(
    key: str,
    *,
    client: AuthenticatedClient,
    enabled: bool,
) -> Response[FeatureFlag | HTTPValidationError]:
    """Toggle Feature Flag

    Args:
        key (str):
        enabled (bool):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeatureFlag | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        key=key,
        enabled=enabled,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    key: str,
    *,
    client: AuthenticatedClient,
    enabled: bool,
) -> FeatureFlag | HTTPValidationError | None:
    """Toggle Feature Flag

    Args:
        key (str):
        enabled (bool):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeatureFlag | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            key=key,
            client=client,
            enabled=enabled,
        )
    ).parsed

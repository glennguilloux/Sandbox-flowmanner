from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.usage_breakdown import UsageBreakdown
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    period: str | Unset = "30d",
    provider: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    params: dict[str, Any] = {}

    params["period"] = period

    json_provider: None | str | Unset
    if isinstance(provider, Unset):
        json_provider = UNSET
    else:
        json_provider = provider
    params["provider"] = json_provider

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/usage/breakdown",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[UsageBreakdown] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = UsageBreakdown.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[HTTPValidationError | list[UsageBreakdown]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    period: str | Unset = "30d",
    provider: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | list[UsageBreakdown]]:
    """Get Usage Breakdown

    Args:
        period (str | Unset): Time period: 7d, 30d, 90d Default: '30d'.
        provider (None | str | Unset): Filter by provider
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[UsageBreakdown]]
    """

    kwargs = _get_kwargs(
        period=period,
        provider=provider,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    period: str | Unset = "30d",
    provider: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | list[UsageBreakdown] | None:
    """Get Usage Breakdown

    Args:
        period (str | Unset): Time period: 7d, 30d, 90d Default: '30d'.
        provider (None | str | Unset): Filter by provider
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[UsageBreakdown]
    """

    return sync_detailed(
        client=client,
        period=period,
        provider=provider,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    period: str | Unset = "30d",
    provider: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | list[UsageBreakdown]]:
    """Get Usage Breakdown

    Args:
        period (str | Unset): Time period: 7d, 30d, 90d Default: '30d'.
        provider (None | str | Unset): Filter by provider
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[UsageBreakdown]]
    """

    kwargs = _get_kwargs(
        period=period,
        provider=provider,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    period: str | Unset = "30d",
    provider: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | list[UsageBreakdown] | None:
    """Get Usage Breakdown

    Args:
        period (str | Unset): Time period: 7d, 30d, 90d Default: '30d'.
        provider (None | str | Unset): Filter by provider
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[UsageBreakdown]
    """

    return (
        await asyncio_detailed(
            client=client,
            period=period,
            provider=provider,
            accept_version=accept_version,
        )
    ).parsed

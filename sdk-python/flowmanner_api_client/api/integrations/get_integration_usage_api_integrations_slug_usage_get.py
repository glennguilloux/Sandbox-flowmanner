from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    slug: str,
    *,
    period: str | Unset = "30d",
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["period"] = period

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/integrations/{slug}/usage".format(
            slug=quote(str(slug), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
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
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    slug: str,
    *,
    client: AuthenticatedClient,
    period: str | Unset = "30d",
) -> Response[Any | HTTPValidationError]:
    """Get Integration Usage

     Returns usage analytics for a user's connection to an integration.

    Includes call counts, success rate, latency stats, and top actions.
    Gated by the ``integration_usage_v1`` feature flag.

    Args:
        slug (str):
        period (str | Unset): Time period: 7d, 30d, 90d Default: '30d'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        slug=slug,
        period=period,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    slug: str,
    *,
    client: AuthenticatedClient,
    period: str | Unset = "30d",
) -> Any | HTTPValidationError | None:
    """Get Integration Usage

     Returns usage analytics for a user's connection to an integration.

    Includes call counts, success rate, latency stats, and top actions.
    Gated by the ``integration_usage_v1`` feature flag.

    Args:
        slug (str):
        period (str | Unset): Time period: 7d, 30d, 90d Default: '30d'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        slug=slug,
        client=client,
        period=period,
    ).parsed


async def asyncio_detailed(
    slug: str,
    *,
    client: AuthenticatedClient,
    period: str | Unset = "30d",
) -> Response[Any | HTTPValidationError]:
    """Get Integration Usage

     Returns usage analytics for a user's connection to an integration.

    Includes call counts, success rate, latency stats, and top actions.
    Gated by the ``integration_usage_v1`` feature flag.

    Args:
        slug (str):
        period (str | Unset): Time period: 7d, 30d, 90d Default: '30d'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        slug=slug,
        period=period,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    slug: str,
    *,
    client: AuthenticatedClient,
    period: str | Unset = "30d",
) -> Any | HTTPValidationError | None:
    """Get Integration Usage

     Returns usage analytics for a user's connection to an integration.

    Includes call counts, success rate, latency stats, and top actions.
    Gated by the ``integration_usage_v1`` feature flag.

    Args:
        slug (str):
        period (str | Unset): Time period: 7d, 30d, 90d Default: '30d'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            slug=slug,
            client=client,
            period=period,
        )
    ).parsed

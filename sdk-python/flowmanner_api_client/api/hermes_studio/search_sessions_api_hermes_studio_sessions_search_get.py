from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.search_sessions_api_hermes_studio_sessions_search_get_response_search_sessions_api_hermes_studio_sessions_search_get import (
    SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    q: str,
    limit: int | Unset = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["q"] = q

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/hermes-studio/sessions/search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet
    | None
):
    if response.status_code == 200:
        response_200 = SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet.from_dict(
            response.json()
        )

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
) -> Response[
    HTTPValidationError
    | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    q: str,
    limit: int | Unset = 50,
) -> Response[
    HTTPValidationError
    | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet
]:
    """Search Sessions

    Args:
        q (str): substring to search in messages
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet]
    """

    kwargs = _get_kwargs(
        q=q,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    q: str,
    limit: int | Unset = 50,
) -> (
    HTTPValidationError
    | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet
    | None
):
    """Search Sessions

    Args:
        q (str): substring to search in messages
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet
    """

    return sync_detailed(
        client=client,
        q=q,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    q: str,
    limit: int | Unset = 50,
) -> Response[
    HTTPValidationError
    | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet
]:
    """Search Sessions

    Args:
        q (str): substring to search in messages
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet]
    """

    kwargs = _get_kwargs(
        q=q,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    q: str,
    limit: int | Unset = 50,
) -> (
    HTTPValidationError
    | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet
    | None
):
    """Search Sessions

    Args:
        q (str): substring to search in messages
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SearchSessionsApiHermesStudioSessionsSearchGetResponseSearchSessionsApiHermesStudioSessionsSearchGet
    """

    return (
        await asyncio_detailed(
            client=client,
            q=q,
            limit=limit,
        )
    ).parsed

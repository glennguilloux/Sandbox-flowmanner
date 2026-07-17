from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    category: None | str | Unset = UNSET,
    tag: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_category: None | str | Unset
    if isinstance(category, Unset):
        json_category = UNSET
    else:
        json_category = category
    params["category"] = json_category

    json_tag: None | str | Unset
    if isinstance(tag, Unset):
        json_tag = UNSET
    else:
        json_tag = tag
    params["tag"] = json_tag

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/tools/discover",
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
    *,
    client: AuthenticatedClient,
    category: None | str | Unset = UNSET,
    tag: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Discover Tools

     Return the tools the calling user is authorized to invoke.

    Filters by:
    - ``required_scopes``: tools with no scopes are public; tools with
      scopes require the user to hold all listed scopes.
    - Optional ``category`` and ``tag`` narrowing.

    Args:
        category (None | str | Unset): Filter by tool category
        tag (None | str | Unset): Filter by tag

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        category=category,
        tag=tag,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    category: None | str | Unset = UNSET,
    tag: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Discover Tools

     Return the tools the calling user is authorized to invoke.

    Filters by:
    - ``required_scopes``: tools with no scopes are public; tools with
      scopes require the user to hold all listed scopes.
    - Optional ``category`` and ``tag`` narrowing.

    Args:
        category (None | str | Unset): Filter by tool category
        tag (None | str | Unset): Filter by tag

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        category=category,
        tag=tag,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    category: None | str | Unset = UNSET,
    tag: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Discover Tools

     Return the tools the calling user is authorized to invoke.

    Filters by:
    - ``required_scopes``: tools with no scopes are public; tools with
      scopes require the user to hold all listed scopes.
    - Optional ``category`` and ``tag`` narrowing.

    Args:
        category (None | str | Unset): Filter by tool category
        tag (None | str | Unset): Filter by tag

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        category=category,
        tag=tag,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    category: None | str | Unset = UNSET,
    tag: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Discover Tools

     Return the tools the calling user is authorized to invoke.

    Filters by:
    - ``required_scopes``: tools with no scopes are public; tools with
      scopes require the user to hold all listed scopes.
    - Optional ``category`` and ``tag`` narrowing.

    Args:
        category (None | str | Unset): Filter by tool category
        tag (None | str | Unset): Filter by tag

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            category=category,
            tag=tag,
        )
    ).parsed

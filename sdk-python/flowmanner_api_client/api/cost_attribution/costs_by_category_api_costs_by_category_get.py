from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    mission_id: None | str | Unset = UNSET,
    days: int | Unset = 30,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_mission_id: None | str | Unset
    if isinstance(mission_id, Unset):
        json_mission_id = UNSET
    else:
        json_mission_id = mission_id
    params["mission_id"] = json_mission_id

    params["days"] = days

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/costs/by-category",
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
    mission_id: None | str | Unset = UNSET,
    days: int | Unset = 30,
) -> Response[Any | HTTPValidationError]:
    """Costs By Category

     Cost breakdown grouped by cost category.

    Returns aggregate costs per category (llm_tokens, tool_execution,
    embedding, external_api, storage, browser) for the given filters.

    Args:
        mission_id (None | str | Unset):
        days (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        days=days,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    mission_id: None | str | Unset = UNSET,
    days: int | Unset = 30,
) -> Any | HTTPValidationError | None:
    """Costs By Category

     Cost breakdown grouped by cost category.

    Returns aggregate costs per category (llm_tokens, tool_execution,
    embedding, external_api, storage, browser) for the given filters.

    Args:
        mission_id (None | str | Unset):
        days (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        mission_id=mission_id,
        days=days,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    mission_id: None | str | Unset = UNSET,
    days: int | Unset = 30,
) -> Response[Any | HTTPValidationError]:
    """Costs By Category

     Cost breakdown grouped by cost category.

    Returns aggregate costs per category (llm_tokens, tool_execution,
    embedding, external_api, storage, browser) for the given filters.

    Args:
        mission_id (None | str | Unset):
        days (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        days=days,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    mission_id: None | str | Unset = UNSET,
    days: int | Unset = 30,
) -> Any | HTTPValidationError | None:
    """Costs By Category

     Cost breakdown grouped by cost category.

    Returns aggregate costs per category (llm_tokens, tool_execution,
    embedding, external_api, storage, browser) for the given filters.

    Args:
        mission_id (None | str | Unset):
        days (int | Unset):  Default: 30.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            mission_id=mission_id,
            days=days,
        )
    ).parsed

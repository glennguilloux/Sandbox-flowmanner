from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    mission_id: str,
    *,
    node_id: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_node_id: None | str | Unset
    if isinstance(node_id, Unset):
        json_node_id = UNSET
    else:
        json_node_id = node_id
    params["node_id"] = json_node_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/costs/mission/{mission_id}/steps".format(
            mission_id=quote(str(mission_id), safe=""),
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
    mission_id: str,
    *,
    client: AuthenticatedClient,
    node_id: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Mission Step Costs

     Per-step cost breakdown for a mission.

    Returns costs grouped by node_id and cost_category, enabling drill-down
    from mission → node → category.

    Args:
        mission_id (str):
        node_id (None | str | Unset): Filter to a specific node

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        node_id=node_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    node_id: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Mission Step Costs

     Per-step cost breakdown for a mission.

    Returns costs grouped by node_id and cost_category, enabling drill-down
    from mission → node → category.

    Args:
        mission_id (str):
        node_id (None | str | Unset): Filter to a specific node

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        node_id=node_id,
    ).parsed


async def asyncio_detailed(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    node_id: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Mission Step Costs

     Per-step cost breakdown for a mission.

    Returns costs grouped by node_id and cost_category, enabling drill-down
    from mission → node → category.

    Args:
        mission_id (str):
        node_id (None | str | Unset): Filter to a specific node

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        node_id=node_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    node_id: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Mission Step Costs

     Per-step cost breakdown for a mission.

    Returns costs grouped by node_id and cost_category, enabling drill-down
    from mission → node → category.

    Args:
        mission_id (str):
        node_id (None | str | Unset): Filter to a specific node

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
            node_id=node_id,
        )
    ).parsed

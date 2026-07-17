from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    critique_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/critiques/{critique_id}".format(
            critique_id=quote(str(critique_id), safe=""),
        ),
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
    critique_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Any | HTTPValidationError]:
    r"""Get Critique

     Get a single critique by id, scoped to (user_id, workspace_id).

    Returns 404 with code ``CRITIQUE_NOT_FOUND`` if the id does not
    exist OR if the row exists but belongs to another (user,
    workspace) tuple — the workspace-isolation guardrail surfaces a
    \"not found\" to the caller to avoid existence-disclosure.

    Args:
        critique_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        critique_id=critique_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    critique_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Any | HTTPValidationError | None:
    r"""Get Critique

     Get a single critique by id, scoped to (user_id, workspace_id).

    Returns 404 with code ``CRITIQUE_NOT_FOUND`` if the id does not
    exist OR if the row exists but belongs to another (user,
    workspace) tuple — the workspace-isolation guardrail surfaces a
    \"not found\" to the caller to avoid existence-disclosure.

    Args:
        critique_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        critique_id=critique_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    critique_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Any | HTTPValidationError]:
    r"""Get Critique

     Get a single critique by id, scoped to (user_id, workspace_id).

    Returns 404 with code ``CRITIQUE_NOT_FOUND`` if the id does not
    exist OR if the row exists but belongs to another (user,
    workspace) tuple — the workspace-isolation guardrail surfaces a
    \"not found\" to the caller to avoid existence-disclosure.

    Args:
        critique_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        critique_id=critique_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    critique_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Any | HTTPValidationError | None:
    r"""Get Critique

     Get a single critique by id, scoped to (user_id, workspace_id).

    Returns 404 with code ``CRITIQUE_NOT_FOUND`` if the id does not
    exist OR if the row exists but belongs to another (user,
    workspace) tuple — the workspace-isolation guardrail surfaces a
    \"not found\" to the caller to avoid existence-disclosure.

    Args:
        critique_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            critique_id=critique_id,
            client=client,
        )
    ).parsed

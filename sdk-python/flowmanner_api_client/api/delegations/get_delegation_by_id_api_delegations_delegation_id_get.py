from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.delegation_response import DelegationResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    delegation_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/delegations/{delegation_id}".format(
            delegation_id=quote(str(delegation_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DelegationResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DelegationResponse.from_dict(response.json())

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
) -> Response[DelegationResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    delegation_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[DelegationResponse | HTTPValidationError]:
    """Get Delegation By Id

     Get delegation details by ID.

    Args:
        delegation_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DelegationResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        delegation_id=delegation_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    delegation_id: str,
    *,
    client: AuthenticatedClient,
) -> DelegationResponse | HTTPValidationError | None:
    """Get Delegation By Id

     Get delegation details by ID.

    Args:
        delegation_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DelegationResponse | HTTPValidationError
    """

    return sync_detailed(
        delegation_id=delegation_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    delegation_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[DelegationResponse | HTTPValidationError]:
    """Get Delegation By Id

     Get delegation details by ID.

    Args:
        delegation_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DelegationResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        delegation_id=delegation_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    delegation_id: str,
    *,
    client: AuthenticatedClient,
) -> DelegationResponse | HTTPValidationError | None:
    """Get Delegation By Id

     Get delegation details by ID.

    Args:
        delegation_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DelegationResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            delegation_id=delegation_id,
            client=client,
        )
    ).parsed

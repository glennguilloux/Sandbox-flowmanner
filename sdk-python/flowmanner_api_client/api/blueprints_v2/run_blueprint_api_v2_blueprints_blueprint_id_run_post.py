from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.run_create import RunCreate
from ...types import UNSET, Response, Unset


def _get_kwargs(
    blueprint_id: str,
    *,
    body: None | RunCreate | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/blueprints/{blueprint_id}/run".format(
            blueprint_id=quote(str(blueprint_id), safe=""),
        ),
    }

    if isinstance(body, RunCreate):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = response.json()
        return response_201

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
    blueprint_id: str,
    *,
    client: AuthenticatedClient,
    body: None | RunCreate | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Run Blueprint

     Create and execute a run from this blueprint.

    Args:
        blueprint_id (str):
        body (None | RunCreate | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        blueprint_id=blueprint_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    blueprint_id: str,
    *,
    client: AuthenticatedClient,
    body: None | RunCreate | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Run Blueprint

     Create and execute a run from this blueprint.

    Args:
        blueprint_id (str):
        body (None | RunCreate | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        blueprint_id=blueprint_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    blueprint_id: str,
    *,
    client: AuthenticatedClient,
    body: None | RunCreate | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Run Blueprint

     Create and execute a run from this blueprint.

    Args:
        blueprint_id (str):
        body (None | RunCreate | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        blueprint_id=blueprint_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    blueprint_id: str,
    *,
    client: AuthenticatedClient,
    body: None | RunCreate | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Run Blueprint

     Create and execute a run from this blueprint.

    Args:
        blueprint_id (str):
        body (None | RunCreate | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            blueprint_id=blueprint_id,
            client=client,
            body=body,
        )
    ).parsed

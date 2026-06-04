from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.trigger_response import TriggerResponse
from ...models.trigger_update import TriggerUpdate
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    trigger_id: str,
    *,
    body: TriggerUpdate,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/triggers/{trigger_id}".format(trigger_id=quote(str(trigger_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()


    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | TriggerResponse | None:
    if response.status_code == 200:
        response_200 = TriggerResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | TriggerResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    trigger_id: str,
    *,
    client: AuthenticatedClient,
    body: TriggerUpdate,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | TriggerResponse]:
    """ Update Trigger

    Args:
        trigger_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (TriggerUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TriggerResponse]
     """


    kwargs = _get_kwargs(
        trigger_id=trigger_id,
body=body,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    trigger_id: str,
    *,
    client: AuthenticatedClient,
    body: TriggerUpdate,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | TriggerResponse | None:
    """ Update Trigger

    Args:
        trigger_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (TriggerUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TriggerResponse
     """


    return sync_detailed(
        trigger_id=trigger_id,
client=client,
body=body,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    trigger_id: str,
    *,
    client: AuthenticatedClient,
    body: TriggerUpdate,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | TriggerResponse]:
    """ Update Trigger

    Args:
        trigger_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (TriggerUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TriggerResponse]
     """


    kwargs = _get_kwargs(
        trigger_id=trigger_id,
body=body,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    trigger_id: str,
    *,
    client: AuthenticatedClient,
    body: TriggerUpdate,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | TriggerResponse | None:
    """ Update Trigger

    Args:
        trigger_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (TriggerUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TriggerResponse
     """


    return (await asyncio_detailed(
        trigger_id=trigger_id,
client=client,
body=body,
accept_version=accept_version,

    )).parsed

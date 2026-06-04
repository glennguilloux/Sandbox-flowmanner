from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.template_response import TemplateResponse
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID



def _get_kwargs(
    template_id: UUID,
    *,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/missions/advanced/templates/{template_id}".format(template_id=quote(str(template_id), safe=""),),
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | TemplateResponse | None:
    if response.status_code == 200:
        response_200 = TemplateResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | TemplateResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    template_id: UUID,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | TemplateResponse]:
    """ Get Template

    Args:
        template_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TemplateResponse]
     """


    kwargs = _get_kwargs(
        template_id=template_id,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    template_id: UUID,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | TemplateResponse | None:
    """ Get Template

    Args:
        template_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TemplateResponse
     """


    return sync_detailed(
        template_id=template_id,
client=client,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    template_id: UUID,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | TemplateResponse]:
    """ Get Template

    Args:
        template_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TemplateResponse]
     """


    kwargs = _get_kwargs(
        template_id=template_id,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    template_id: UUID,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | TemplateResponse | None:
    """ Get Template

    Args:
        template_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TemplateResponse
     """


    return (await asyncio_detailed(
        template_id=template_id,
client=client,
accept_version=accept_version,

    )).parsed

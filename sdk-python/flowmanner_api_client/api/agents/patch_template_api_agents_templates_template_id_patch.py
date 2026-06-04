from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.agent_template_response import AgentTemplateResponse
from ...models.agent_template_update import AgentTemplateUpdate
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID



def _get_kwargs(
    template_id: UUID,
    *,
    body: AgentTemplateUpdate,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/agents/templates/{template_id}".format(template_id=quote(str(template_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()


    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> AgentTemplateResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AgentTemplateResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[AgentTemplateResponse | HTTPValidationError]:
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
    body: AgentTemplateUpdate,
    accept_version: str | Unset = 'v1',

) -> Response[AgentTemplateResponse | HTTPValidationError]:
    """ Patch Template

    Args:
        template_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (AgentTemplateUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentTemplateResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        template_id=template_id,
body=body,
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
    body: AgentTemplateUpdate,
    accept_version: str | Unset = 'v1',

) -> AgentTemplateResponse | HTTPValidationError | None:
    """ Patch Template

    Args:
        template_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (AgentTemplateUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentTemplateResponse | HTTPValidationError
     """


    return sync_detailed(
        template_id=template_id,
client=client,
body=body,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    template_id: UUID,
    *,
    client: AuthenticatedClient,
    body: AgentTemplateUpdate,
    accept_version: str | Unset = 'v1',

) -> Response[AgentTemplateResponse | HTTPValidationError]:
    """ Patch Template

    Args:
        template_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (AgentTemplateUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AgentTemplateResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        template_id=template_id,
body=body,
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
    body: AgentTemplateUpdate,
    accept_version: str | Unset = 'v1',

) -> AgentTemplateResponse | HTTPValidationError | None:
    """ Patch Template

    Args:
        template_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (AgentTemplateUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AgentTemplateResponse | HTTPValidationError
     """


    return (await asyncio_detailed(
        template_id=template_id,
client=client,
body=body,
accept_version=accept_version,

    )).parsed

from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.execute_tool_api_tools_tool_id_execute_post_body import ExecuteToolApiToolsToolIdExecutePostBody
from ...models.http_validation_error import HTTPValidationError
from ...models.tool_execution_result import ToolExecutionResult
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    tool_id: str,
    *,
    body: ExecuteToolApiToolsToolIdExecutePostBody,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/tools/{tool_id}/execute".format(tool_id=quote(str(tool_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()


    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | ToolExecutionResult | None:
    if response.status_code == 200:
        response_200 = ToolExecutionResult.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | ToolExecutionResult]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    tool_id: str,
    *,
    client: AuthenticatedClient,
    body: ExecuteToolApiToolsToolIdExecutePostBody,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | ToolExecutionResult]:
    """ Execute Tool

     Execute a tool by ID with JSON input body.

    The body is passed to the tool's execute() method along with
    a 'context' dict containing the user_id.

    Args:
        tool_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (ExecuteToolApiToolsToolIdExecutePostBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolExecutionResult]
     """


    kwargs = _get_kwargs(
        tool_id=tool_id,
body=body,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    tool_id: str,
    *,
    client: AuthenticatedClient,
    body: ExecuteToolApiToolsToolIdExecutePostBody,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | ToolExecutionResult | None:
    """ Execute Tool

     Execute a tool by ID with JSON input body.

    The body is passed to the tool's execute() method along with
    a 'context' dict containing the user_id.

    Args:
        tool_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (ExecuteToolApiToolsToolIdExecutePostBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolExecutionResult
     """


    return sync_detailed(
        tool_id=tool_id,
client=client,
body=body,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    tool_id: str,
    *,
    client: AuthenticatedClient,
    body: ExecuteToolApiToolsToolIdExecutePostBody,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | ToolExecutionResult]:
    """ Execute Tool

     Execute a tool by ID with JSON input body.

    The body is passed to the tool's execute() method along with
    a 'context' dict containing the user_id.

    Args:
        tool_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (ExecuteToolApiToolsToolIdExecutePostBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ToolExecutionResult]
     """


    kwargs = _get_kwargs(
        tool_id=tool_id,
body=body,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    tool_id: str,
    *,
    client: AuthenticatedClient,
    body: ExecuteToolApiToolsToolIdExecutePostBody,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | ToolExecutionResult | None:
    """ Execute Tool

     Execute a tool by ID with JSON input body.

    The body is passed to the tool's execute() method along with
    a 'context' dict containing the user_id.

    Args:
        tool_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (ExecuteToolApiToolsToolIdExecutePostBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ToolExecutionResult
     """


    return (await asyncio_detailed(
        tool_id=tool_id,
client=client,
body=body,
accept_version=accept_version,

    )).parsed

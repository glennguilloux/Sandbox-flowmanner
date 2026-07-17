from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.code_execute_request import CodeExecuteRequest
from ...models.code_execute_response import CodeExecuteResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: CodeExecuteRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/chat/code/execute",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CodeExecuteResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CodeExecuteResponse.from_dict(response.json())

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
) -> Response[CodeExecuteResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: CodeExecuteRequest,
) -> Response[CodeExecuteResponse | HTTPValidationError]:
    """Code Execute

     Execute a code cell using the production sandbox tools (Python or Node.js).

    Uses PythonSandboxTool / NodeJsSandboxTool for proper resource limits,
    import denylists, and timeout handling (H5.4 production wiring).

    Args:
        body (CodeExecuteRequest): Request to execute a code cell.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CodeExecuteResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: CodeExecuteRequest,
) -> CodeExecuteResponse | HTTPValidationError | None:
    """Code Execute

     Execute a code cell using the production sandbox tools (Python or Node.js).

    Uses PythonSandboxTool / NodeJsSandboxTool for proper resource limits,
    import denylists, and timeout handling (H5.4 production wiring).

    Args:
        body (CodeExecuteRequest): Request to execute a code cell.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CodeExecuteResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: CodeExecuteRequest,
) -> Response[CodeExecuteResponse | HTTPValidationError]:
    """Code Execute

     Execute a code cell using the production sandbox tools (Python or Node.js).

    Uses PythonSandboxTool / NodeJsSandboxTool for proper resource limits,
    import denylists, and timeout handling (H5.4 production wiring).

    Args:
        body (CodeExecuteRequest): Request to execute a code cell.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CodeExecuteResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: CodeExecuteRequest,
) -> CodeExecuteResponse | HTTPValidationError | None:
    """Code Execute

     Execute a code cell using the production sandbox tools (Python or Node.js).

    Uses PythonSandboxTool / NodeJsSandboxTool for proper resource limits,
    import denylists, and timeout handling (H5.4 production wiring).

    Args:
        body (CodeExecuteRequest): Request to execute a code cell.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CodeExecuteResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed

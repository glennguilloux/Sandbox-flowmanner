# User-friendly error messages for Story 2.3 (FR18)
# Maps technical errors to user-friendly messages and recovery suggestions

EDGE_CASE_HANDLING = {
    # API Errors
    "timeout": {
        "message": "The request timed out. The external service may be experiencing high load.",
        "failure_type": "api_timeout",
        "suggestion": "Try again in a few minutes, or switch to a different API provider if available.",
        "retryable": True,
    },
    "rate_limit": {
        "message": "API rate limit exceeded. You've reached the maximum requests for this time period.",
        "failure_type": "api_rate_limit",
        "suggestion": "Upgrade to Pro for higher rate limits, or wait 15 minutes before retrying.",
        "retryable": True,
    },
    "api_error": {
        "message": "The external API returned an error. This may be due to invalid parameters or service issues.",
        "failure_type": "api_error",
        "suggestion": "Check your API key configuration in Settings, or try with different parameters.",
        "retryable": True,
    },
    # GPU Errors
    "gpu_unavailable": {
        "message": "GPU resources are currently unavailable. All GPUs may be in use.",
        "failure_type": "gpu_unavailable",
        "suggestion": "Try again later, or switch to CPU mode if supported by your mission type.",
        "retryable": True,
    },
    "gpu_out_of_memory": {
        "message": "GPU out of memory. The model or task requires more GPU memory than available.",
        "failure_type": "gpu_oom",
        "suggestion": "Try a smaller model, reduce batch size, or switch to a different GPU node.",
        "retryable": True,
    },
    # Network/Infrastructure Errors
    "connection_error": {
        "message": "Unable to connect to the required service. Please check your network connection.",
        "failure_type": "connection_error",
        "suggestion": "Check your internet connection and try again.",
        "retryable": True,
    },
    "service_unavailable": {
        "message": "The requested service is temporarily unavailable.",
        "failure_type": "service_unavailable",
        "suggestion": "This is usually temporary. Please try again in 5-10 minutes.",
        "retryable": True,
    },
    # Input/Validation Errors
    "invalid_input": {
        "message": "The provided input is invalid or unsupported.",
        "failure_type": "invalid_input",
        "suggestion": "Check the mission parameters and ensure all required fields are correctly formatted.",
        "retryable": False,
    },
    "unsupported_model": {
        "message": "The selected model is not supported for this mission type.",
        "failure_type": "unsupported_model",
        "suggestion": "Choose a supported model from the dropdown menu.",
        "retryable": False,
    },
    # Generic fallback
    "unknown": {
        "message": "An unexpected error occurred during mission execution.",
        "failure_type": "unknown_error",
        "suggestion": "Try again. If the problem persists, contact support with the Mission ID.",
        "retryable": True,
    },
}


def get_user_friendly_error(error: Exception, context: dict | None = None) -> dict:
    """
    Convert a technical exception to a user-friendly error message.
    Returns dict with keys: message, failure_type, suggestion, retryable
    """
    error_type = type(error).__name__
    error_msg = str(error).lower()

    # Check for specific error patterns
    if "timeout" in error_msg or error_type == "TimeoutError":
        return EDGE_CASE_HANDLING["timeout"]
    elif "rate limit" in error_msg or "429" in error_msg:
        return EDGE_CASE_HANDLING["rate_limit"]
    elif "gpu" in error_msg and ("unavailable" in error_msg or "not found" in error_msg):
        return EDGE_CASE_HANDLING["gpu_unavailable"]
    elif "out of memory" in error_msg or "oom" in error_msg:
        return EDGE_CASE_HANDLING["gpu_out_of_memory"]
    elif "connection" in error_msg or error_type == "ConnectionError":
        return EDGE_CASE_HANDLING["connection_error"]
    elif "unavailable" in error_msg or "503" in error_msg:
        return EDGE_CASE_HANDLING["service_unavailable"]
    elif "invalid" in error_msg or "validation" in error_msg:
        return EDGE_CASE_HANDLING["invalid_input"]
    elif "model" in error_msg and "not found" in error_msg:
        return EDGE_CASE_HANDLING["unsupported_model"]
    elif "api" in error_msg or "401" in error_msg or "403" in error_msg:
        return EDGE_CASE_HANDLING["api_error"]
    else:
        return EDGE_CASE_HANDLING["unknown"]

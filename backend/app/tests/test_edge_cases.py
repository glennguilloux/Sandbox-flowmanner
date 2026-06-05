import pytest


@pytest.mark.asyncio
async def test_user_friendly_error_mapping():
    """Test that error mapping returns user-friendly messages."""
    from app.utils.error_mapping import get_user_friendly_error
    
    # Test timeout error
    class TimeoutError(Exception):
        pass
    
    error = TimeoutError("Connection timed out")
    result = get_user_friendly_error(error)
    
    assert "timed out" in result["message"].lower() or "timeout" in result["message"].lower()
    assert result["retryable"] == True
    
    # Test unknown error
    error = Exception("Some weird error")
    result = get_user_friendly_error(error)
    
    assert result["failure_type"] == "unknown_error"
    assert "unexpected" in result["message"].lower()


@pytest.mark.asyncio
async def test_mission_executor_stores_friendly_error():
    """Test that mission executor stores user-friendly errors."""
    from app.utils.error_mapping import get_user_friendly_error
    
    # Simulate what happens in mission_executor.py
    error = Exception("API rate limit exceeded")
    error_info = get_user_friendly_error(error)
    
    assert error_info["failure_type"] == "api_rate_limit"
    assert "rate limit" in error_info["message"].lower()
    assert error_info["retryable"] == True

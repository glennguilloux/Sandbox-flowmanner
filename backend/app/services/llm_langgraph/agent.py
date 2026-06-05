"""LangGraph Agent integration with LLM support."""
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class LLMConfig:
    """Configuration for LLM used in LangGraph agents."""
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096
    api_key: str | None = None
    base_url: str | None = None
    provider: str = "openai"
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "provider": self.provider,
        }


class LangGraphAgent:
    """LangGraph agent with LLM integration."""
    
    def __init__(self, llm_config: LLMConfig | None = None, llm=None):
        self.llm_config = llm_config or LLMConfig()
        self.llm = llm
        self._initialized = False
        
    async def initialize(self):
        """Initialize the agent."""
        self._initialized = True
        logger.info(f"LangGraphAgent initialized with model: {self.llm_config.model}")
        
    async def run(self, messages: list[dict[str, Any]], **kwargs):
        """Run the agent with messages."""
        if not self._initialized:
            await self.initialize()
        
        if self.llm:
            # Use provided LLM instance
            return await self._run_with_llm(messages, **kwargs)
        else:
            # Use config-based LLM
            return await self._run_with_config(messages, **kwargs)

    async def _run_with_llm(self, messages: list[dict[str, Any]], **kwargs):
        """Run using provided LLM instance."""
        try:
            if hasattr(self.llm, "ainvoke"):
                response = await self.llm.ainvoke(messages, **kwargs)
                content = (
                    response.content
                    if hasattr(response, "content")
                    else str(response)
                )
                return {
                    "messages": [*messages, {"role": "assistant", "content": content}],
                    "status": "completed",
                    "response": content,
                }
        except Exception as e:
            logger.error("LLM invocation failed: %s", e)
            return {
                "messages": messages,
                "status": "error",
                "error": str(e),
            }

        logger.warning("LLM instance lacks ainvoke method, falling back to model router")
        return await self._run_with_config(messages, **kwargs)

    async def _run_with_config(self, messages: list[dict[str, Any]], **kwargs):
        """Run using LLM config via LLMManager."""
        try:
            from app.services.model_router import get_model_router

            router = get_model_router()
            result = await router.route_request(
                messages=messages,
                model_id=self.llm_config.model,
                **kwargs,
            )

            if result.get("success"):
                return {
                    "messages": [*messages, {"role": "assistant", "content": result["response"]}],
                    "status": "completed",
                    "response": result["response"],
                    "model_id": result.get("model_id"),
                    "usage": result.get("usage"),
                }
            else:
                return {
                    "messages": messages,
                    "status": "error",
                    "error": result.get("error", "Unknown error"),
                }

        except ImportError:
            logger.warning("Model router not available for LangGraph agent, sending graceful error to user")
            graceful_error = "I'm sorry, but the AI service is currently unavailable. The model router could not be loaded. Please try again later."
        except Exception as e:
            logger.error("LangGraph agent config run failed: %s", e)
            graceful_error = f"I'm sorry, but something went wrong while processing your request: {type(e).__name__}. Please try again."

        # Return a graceful response rather than echoing the user's input
        return {
            "messages": [*messages, {"role": "assistant", "content": graceful_error}],
            "status": "error",
            "error": graceful_error,
            "response": graceful_error,
        }


# Global agent instance
_agent_instance: LangGraphAgent | None = None


def get_agent(llm=None, llm_config: LLMConfig | None = None) -> LangGraphAgent:
    """Get or create a LangGraph agent instance.
    
    Args:
        llm: Optional LLM instance to use
        llm_config: Optional LLM configuration
        
    Returns:
        LangGraphAgent instance
    """
    global _agent_instance
    
    if _agent_instance is None:
        _agent_instance = LangGraphAgent(llm_config=llm_config, llm=llm)
    elif llm is not None:
        _agent_instance.llm = llm
    
    return _agent_instance

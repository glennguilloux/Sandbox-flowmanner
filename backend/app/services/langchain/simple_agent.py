"""
Simplified LangChain Agent - Production Ready
"""

import logging
import os
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentResponse(BaseModel):
    """Structured response"""

    response: str
    tools_used: list[str]
    success: bool = True
    metadata: dict[str, Any] | None = None


class SimpleWorkflowAgent:
    """Routes requests to appropriate tools"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.getenv("LLAMACPP_MODEL", "Qwen3.6-27B-Q5_K_M-mtp.gguf"),
            base_url=os.getenv("LLAMACPP_URL", "http://10.0.4.1:11434") + "/v1",
            api_key="not-needed",
            temperature=0.7,
        )

    def invoke(self, message: str) -> AgentResponse:
        """Route message to appropriate tool"""
        try:
            # Import production tools
            from app.services.langchain.tools.comfyui_agent_tool_prod import (
                generate_3d_model,
                generate_hero_background,
                generate_product_shot,
            )
            from app.services.langchain.tools.n8n_agent_tool_prod import (
                execute_n8n_workflow,
                list_n8n_workflows,
            )
            from app.services.langchain.tools.workflow_catalog_tool_prod import (
                recommend_workflows,
                search_workflows,
            )
            from app.services.langchain.unified_agent import IntentClassifier

            logger.info('Agent invoked with message: %s...', message[:50])
            intent = IntentClassifier.classify(message)
            logger.debug('Intent classified: %s', intent)

            if intent["intent"] == "comfyui":
                if intent["details"]["type"] == "hero-background":
                    result = generate_hero_background(
                        prompt=intent["details"]["prompt"],
                        style=intent["details"]["style"],
                    )
                    return AgentResponse(
                        response=result, tools_used=["generate_hero_background"]
                    )
                elif intent["details"]["type"] == "product-shot":
                    result = generate_product_shot(
                        product=intent["details"]["prompt"],
                        style=intent["details"]["style"],
                    )
                    return AgentResponse(
                        response=result, tools_used=["generate_product_shot"]
                    )
                elif intent["details"]["type"] == "3d-model":
                    result = generate_3d_model(
                        description=intent["details"]["prompt"],
                        style=intent["details"]["style"],
                    )
                    return AgentResponse(
                        response=result, tools_used=["generate_3d_model"]
                    )

            elif intent["intent"] == "n8n":
                workflow_id = intent["details"]["workflow_id"]
                if workflow_id:
                    result = execute_n8n_workflow(
                        workflow_id=workflow_id,
                        parameters=intent["details"]["parameters"],
                    )
                    return AgentResponse(
                        response=result, tools_used=["execute_n8n_workflow"]
                    )
                else:
                    result = list_n8n_workflows()
                    return AgentResponse(
                        response=result, tools_used=["list_n8n_workflows"]
                    )

            elif intent["intent"] == "catalog":
                if intent["details"]["type"] == "recommend":
                    result = recommend_workflows(intent=intent["details"]["query"])
                    return AgentResponse(
                        response=result, tools_used=["recommend_workflows"]
                    )
                else:
                    result = search_workflows(query=intent["details"]["query"])
                    return AgentResponse(
                        response=result, tools_used=["search_workflows"]
                    )

            else:
                logger.info('No specific intent found, using LLM for: %s...', message[:50])
                response = self.llm.invoke(message)
                return AgentResponse(
                    response=str(response), tools_used=[], metadata={"type": "llm_chat"}
                )

        except Exception as e:
            logger.error('Agent invocation error: %s', e, exc_info=True)
            return AgentResponse(
                response=f"I encountered an error processing your request. Please try again.",
                tools_used=[],
                success=False,
                metadata={"error": str(e)},
            )

        except Exception as e:
            return AgentResponse(
                response=f"I encountered an error: {e!s}",
                tools_used=[],
                success=False,
                metadata={"error": str(e)},
            )


def create_simple_agent():
    return SimpleWorkflowAgent()

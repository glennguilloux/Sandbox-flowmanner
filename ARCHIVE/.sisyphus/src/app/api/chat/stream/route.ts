import { NextRequest } from "next/server";

// SSE event types for the hybrid platform
type SSEEventType =
  | "text_delta"
  | "tool_call_start"
  | "tool_call_delta"
  | "tool_call_result"
  | "agent_step_start"
  | "agent_step_end"
  | "reasoning_delta"
  | "citation"
  | "permission_request"
  | "canvas_update"
  | "sandbox_event"
  | "handoff"
  | "error"
  | "done";

interface SSEEvent {
  type: SSEEventType;
  data: Record<string, unknown>;
}

function formatSSE(event: SSEEvent): string {
  return `event: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`;
}

// Demo tool definitions that would come from the tool registry
const DEMO_TOOLS = [
  {
    name: "web_search",
    description: "Search the web for current information",
    parameters: { query: "string", depth: "number" },
  },
  {
    name: "code_execute",
    description: "Execute code in a sandbox environment",
    parameters: { language: "string", code: "string" },
  },
  {
    name: "file_read",
    description: "Read the contents of a file",
    parameters: { path: "string" },
  },
  {
    name: "browser_navigate",
    description: "Navigate a browser to a URL",
    parameters: { url: "string" },
  },
  {
    name: "memory_search",
    description: "Search long-term memory / RAG",
    parameters: { query: "string", topK: "number" },
  },
  {
    name: "sandbox_preview",
    description: "Generate a live preview of code output",
    parameters: { html: "string", css: "string", js: "string" },
  },
];

// Simulated agent responses per character
const AGENT_RESPONSES: Record<string, string[]> = {
  default: [
    "I'll help you with that. Let me think through this step by step.\n\n",
    "First, let me search for the relevant information...\n\n",
    "I found some results. Let me analyze them.\n\n",
    "Based on my analysis, here's what I recommend:\n\n",
    "Let me also execute some code to validate this.\n\n",
    "The code execution confirms the approach. Here's a summary:\n\n",
    "I've completed the task. Let me know if you need anything else!",
  ],
  code: [
    "Let me write some code to solve this.\n\n",
    "```python\nimport numpy as np\n\ndef solve(input_data):\n    result = np.array(input_data) * 2\n    return result.tolist()\n\n# Example usage\nprint(solve([1, 2, 3]))\n```\n\n",
    "Now let me run this in the sandbox to verify...\n\n",
  ],
};

export async function POST(req: NextRequest) {
  const body = await req.json();
  const userMessage: string = body.content || "";
  const _threadId: string = body.threadId || "";
  const model: string = body.model || "gpt-4o";
  const _includeTools: boolean = body.includeTools !== false;

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: SSEEvent) => {
        controller.enqueue(encoder.encode(formatSSE(event)));
      };

      try {
        // Send initial tool definitions
        send({
          type: "canvas_update",
          data: {
            tools: DEMO_TOOLS.map((t) => ({
              name: t.name,
              description: t.description,
              parameters: t.parameters,
            })),
            model,
            timestamp: Date.now(),
          },
        });

        // Determine response style based on user message
        const isCodeRequest =
          /code|python|javascript|function|script|program/i.test(userMessage);
        const responses = isCodeRequest
          ? AGENT_RESPONSES.code
          : AGENT_RESPONSES.default;

        // Simulate tool calls
        if (/search|find|look|what is|who is|how|when/i.test(userMessage)) {
          // Tool call: web_search
          send({
            type: "tool_call_start",
            data: {
              toolCallId: "call_1",
              toolName: "web_search",
              args: { query: userMessage, depth: 2 },
              timestamp: Date.now(),
            },
          });

          // Simulate some thinking time
          await new Promise((r) => setTimeout(r, 600));

          send({
            type: "tool_call_result",
            data: {
              toolCallId: "call_1",
              toolName: "web_search",
              result: {
                matches: [
                  {
                    title: "Relevant article about your query",
                    url: "https://example.com/article",
                    snippet:
                      "This article discusses the topic you asked about in detail, covering key aspects and recent developments.",
                  },
                  {
                    title: "Documentation reference",
                    url: "https://docs.example.com/reference",
                    snippet:
                      "Official documentation covering the technical specifications and implementation details.",
                  },
                ],
              },
              status: "completed",
              timestamp: Date.now(),
            },
          });
        }

        if (/code|python|javascript|run|execute|script/i.test(userMessage)) {
          // Tool call: code_execute
          send({
            type: "tool_call_start",
            data: {
              toolCallId: "call_2",
              toolName: "code_execute",
              args: {
                language: "python",
                code: 'print("Hello from sandbox!")\nresult = 2 + 2\nprint(f"Result: {result}")',
              },
              timestamp: Date.now(),
            },
          });

          await new Promise((r) => setTimeout(r, 800));

          send({
            type: "tool_call_result",
            data: {
              toolCallId: "call_2",
              toolName: "code_execute",
              result: {
                stdout: "Hello from sandbox!\nResult: 4\n",
                stderr: "",
                exitCode: 0,
              },
              status: "completed",
              timestamp: Date.now(),
            },
          });

          // Also send a sandbox event
          send({
            type: "sandbox_event",
            data: {
              sandboxId: "sbx_demo_001",
              status: "running",
              previewUrl: "/sandbox-preview/demo",
              language: "python",
              timestamp: Date.now(),
            },
          });
        }

        // Agent step indicators
        send({
          type: "agent_step_start",
          data: {
            stepId: "step_1",
            stepType: "reasoning",
            agentName: "assistant",
            name: "analyze_query",
            displayName: "Analyzing your query",
            timestamp: Date.now(),
          },
        });

        // Stream text chunks with delays
        for (let i = 0; i < responses.length; i++) {
          const chunk = responses[i];
          // Send in smaller chunks for realism
          const words = chunk.split(" ");
          for (let w = 0; w < words.length; w += 3) {
            const wordChunk = words.slice(w, w + 3).join(" ") + " ";
            send({
              type: "text_delta",
              data: {
                content: w === 0 && i > 0 ? wordChunk : wordChunk,
                timestamp: Date.now(),
              },
            });
            await new Promise((r) => setTimeout(r, 30 + Math.random() * 40));
          }
        }

        // Mark agent step complete
        send({
          type: "agent_step_end",
          data: {
            stepId: "step_1",
            stepType: "reasoning",
            status: "completed",
            agentName: "assistant",
            timestamp: Date.now(),
          },
        });

        // If it was a code request, show canvas update for sandbox
        if (/code|python|javascript|run|execute|script/i.test(userMessage)) {
          send({
            type: "canvas_update",
            data: {
              action: "open_tile",
              tileKind: "code_sandbox",
              config: {
                language: "python",
                code: 'print("Hello from sandbox!")\nresult = 2 + 2\nprint(f"Result: {result}")',
              },
              timestamp: Date.now(),
            },
          });
        }

        // Send citations
        send({
          type: "citation",
          data: {
            sources: [
              {
                source: "Documentation v2.4",
                excerpt:
                  "The system uses a hybrid architecture combining chat, tools, agents, and sandboxes.",
                score: 0.94,
              },
            ],
            timestamp: Date.now(),
          },
        });

        // Done
        send({
          type: "done",
          data: {
            messageId: crypto.randomUUID(),
            tokenCount: 342,
            cost: 420,
            timestamp: Date.now(),
          },
        });
      } catch (e) {
        send({
          type: "error",
          data: {
            message:
              e instanceof Error ? e.message : "An unknown error occurred",
            timestamp: Date.now(),
          },
        });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

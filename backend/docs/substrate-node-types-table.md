# Substrate Node Type Config Table

This table is generated automatically from the substrate source.


**Legend:** `(R)` = required, `(O)` = optional, `(Ralt)` = one of a group of alternatives must be provided. A `—` means the node is a passthrough with no handler or no config keys read by the handler.

| Node type | Handler | Config keys |
|-----------|---------|-------------|
| `llm_call` | `_handle_llm` | `context_query` (O), `context_token_budget` (O), `long_context` (O), `max_tokens` (O), `prompt` (R), `system_prompt` (O), `temperature` (O) |
| `tool_call` | `_handle_tool` | `params` (O), `tool_id` (O), `tool_name` (O) |
| `code_execution` | `_handle_code` | `code` (O) |
| `rag_query` | `_handle_rag` | `collection` (O), `query` (O) |
| `web_search` | `_handle_web_search` | `query` (O) |
| `file_operation` | `_handle_file` | `file_id` (O), `operation` (O) |
| `human_review` | `_handle_hitl_interrupt` | `approval_prompt` (O), `description` (O) |
| `browser_navigate` | `_handle_browser` | `params` (R) |
| `browser_snapshot` | `_handle_browser` | `params` (O) |
| `browser_click` | `_handle_browser` | `params` (R) |
| `browser_type` | `_handle_browser` | `params` (R) |
| `browser_scroll` | `_handle_browser` | `params` (R) |
| `browser_screenshot` | `_handle_browser` | `params` (O) |
| `browser_close` | `_handle_browser` | `params` (O) |
| `approval` | `_handle_hitl_interrupt` | `approval_prompt` (O), `description` (O) |
| `guardrail` | `_handle_guardrail` | `classifierPrompt` (O), `guardrailMode` (O), `max_tokens` (O), `onViolation` (O), `patterns` (O), `redactWith` (O), `temperature` (O), `useClassifier` (O) |
| `sub_workflow` | `_handle_sub_workflow` | `workflow_id` (O) |
| `phase_gate` | `—` | — |
| `fan_out` | `—` | — |
| `fan_in` | `—` | — |
| `sandbox` | `_handle_sandbox_node` | — |
| `transform` | `_handle_transform` | `transformExpression` (R), `transformType` (R) |
| `filter` | `_handle_transform` | `transformExpression` (R), `transformType` (R) |
| `condition` | `_handle_condition` | `expression` (R) |
| `template_render` | `_handle_template_render` | `template` (O) |
| `split` | `_handle_split` | `mode` (O), `splitOn` (R) |
| `log` | `_handle_log` | `level` (R), `message` (R) |
| `loop` | `_handle_loop` | `loop_var` (O), `max_iterations` (O), `stop_condition` (O) |
| `webhook` | `_handle_webhook` | `headers` (O), `method` (O), `url` (R) |
| `retry` | `_handle_retry` | `backoffMs` (O), `maxRetries` (R) |
| `cache_get` | `_handle_cache_get` | `key` (R), `modelId` (O), `params` (O), `prompt` (O), `promptTemplate` (O) |
| `validate_schema` | `_handle_validate_schema` | `payload_key` (O), `schema` (R) |
| `router` | `_handle_router` | — |
| `delay` | `_handle_delay` | `delayMs` (R) |
| `merge` | `_handle_merge` | — |
| `memory_write` | `_handle_memory_write` | `text` (O) |
| `variable_set` | `_handle_variable_set` | `prefix` (O), `varExpr` (Ralt), `varName` (R), `varValue` (Ralt) |
| `llm_eval` | `_handle_llm` | `context_query` (O), `context_token_budget` (O), `long_context` (O), `max_tokens` (O), `prompt` (R), `system_prompt` (O), `temperature` (O) |
| `memory_read` | `_handle_memory_read` | `collection` (O), `query` (R), `scoreThreshold` (O), `topK` (O) |
| `timeout` | `_handle_timeout` | `timeoutMs` (O), `wrapped_node_id` (O) |

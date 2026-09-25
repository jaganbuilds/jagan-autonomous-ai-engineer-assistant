# LLM Migration Architecture - Gemini to OpenRouter/Ollama

## 1. Analysis of Current Workspace

Currently, the `Jagan AI` runtime heavily depends on `google-genai`. The dependency surfaces in the following ways:
- **Configuration:** `app/config.py` holds Gemini-specific keys, timeouts, and max retries.
- **Client Initialization:** `app/llm_client.py` defines `get_llm_client` and `get_llm_client_or_raise` which return a `google.genai.Client`.
- **Agents and Services:**
  - `app/agents/manager.py`: Uses `client.chats.create()` to manage conversational state, `chat.send_message()`, and parses `response.function_calls`. It constructs Gemini-specific `types.Part.from_function_response()` when tools are executed or confirmed.
  - `app/agents/planner.py`: Uses `client.models.generate_content()` with `response_mime_type="application/json"` to generate agent plans.
  - `app/matching/semantic_matcher.py`, `app/resume/profile_extractor.py`, `app/services/code_fix_proposer.py`, `app/services/git_commit_proposer.py`, `app/tools/hr_email_tool.py`: All use `generate_content()` with Pydantic schemas or standard JSON.
- **Tests:** A significant number of tests rely on `patch('app.llm_client.get_llm_client')` and mock out the Gemini client interface (e.g., `tests/test_manager.py`, `tests/test_llm_resilience.py`).

## 2. Proposed Architecture (`app/llm/`)

We will create a centralized LLM abstraction in `app/llm/`. The existing `app/llm_client.py` will be removed or refactored out.

### `app/llm/models.py`
Defines standardized data structures and normalized exceptions:
- **Exceptions:** `LLMError`, `LLMProviderError`, `LLMRateLimitError`, `LLMTimeoutError`, `LLMUnavailableError`, `LLMInvalidResponseError`.
- **Tool Structures:** `ToolCall` (name, arguments, id)
- **Chat Structures:** `ChatMessage` (role, content, tool_calls, tool_call_id, etc.)

### `app/llm/providers.py`
Implements the connection to OpenAI-compatible endpoints using the `openai` Python package.
- **OpenRouterProvider:** Connects to `https://openrouter.ai/api/v1`
- **OllamaProvider:** Connects to `http://localhost:11434/v1`

### `app/llm/gateway.py`
The orchestrator for LLM calls that handles the sequential fallback logic.
- **Methods:**
  - `generate_text(prompt: str, ...) -> str`
  - `generate_json(prompt: str, schema: BaseModel = None, ...) -> dict / BaseModel`
  - `chat(messages: List[Dict], tools: List[Dict] = None, ...) -> LLMChatResponse`
- **Fallback Logic:**
  1. Iterate sequentially through `OPENROUTER_MODELS`:
     `qwen/qwen3.8-27b:free` → `nvidia/nemotron-3-ultra-550b-a55b:free` → `inclusionai/ling-3.0-flash-sante:free` → `poolside/laguna-s-2.1:free` → `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
  2. If an OpenRouter model fails (HTTP 429, 50x, timeout, empty response), log the failure and try the next.
  3. If all OpenRouter models fail, fall back to `OllamaProvider` using `qwen3:4b`.
  4. If Ollama fails, raise a normalized `LLMUnavailableError`.

## 3. Affected Components and Refactoring Plan

- **ManagerAgent (`app/agents/manager.py`):**
  - Drop `client.chats.create`.
  - Maintain conversation history as a list of dictionaries (`self._chats[session_id] = [...]`) internally.
  - Map `registry.get_all_tools()` to OpenAI function schemas.
  - Use `gateway.chat(messages, tools)` instead of `chat.send_message()`.
  - Handle Jagan AI `ToolCall` and append tool responses as `{"role": "tool", "tool_call_id": ..., "content": ...}`.
  - Maintain the existing security boundary (intercepting unconfirmed tool calls).

- **PlannerAgent (`app/agents/planner.py`) & Services:**
  - Replace `client.models.generate_content(..., response_mime_type="application/json")` with `gateway.generate_json(...)`.
  - Handle Jagan AI normalized exceptions instead of `google.genai.errors.APIError`.

- **Configuration (`app/config.py`):**
  - Remove all `gemini_*` fields.
  - Ensure OpenRouter and Ollama fields exist.
  - Delete `google-genai` from dependencies.

- **Tests:**
  - Rewrite `test_llm_resilience.py` to test the sequential 5-model OpenRouter fallback and the Ollama fallback.
  - Update `test_manager.py` and others to mock `app.llm.gateway` instead of `get_llm_client`.

## 4. Execution Steps (Next Phases)
1. Proceed with creating the `app/llm` abstraction (`models.py`, `providers.py`, `gateway.py`).
2. Migrate `ManagerAgent` and test state management.
3. Migrate `PlannerAgent` and secondary services (Code Fix, Git Commit, Semantic Matcher, Profile Extractor).
4. Remove `app/llm_client.py` and Gemini configurations.
5. Fix all broken tests, ensuring 100% test pass rate with no regressions.

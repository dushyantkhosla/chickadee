# LLM Chain — `FallbackModel` + Restored `RunContext` Deps

**Date:** 2026-06-03
**Branch:** `feat/unified-llm-chain`
**Status:** Design (approved); implementation plan to follow via `writing-plans` skill
**Replaces:** prior user-prompt string-injection of `TalkMetadata` in `src/agent.py:144-153`

## Goal

Adopt PydanticAI's built-in `FallbackModel` for the provider chain, and restore the typed `RunContext[TalkMetadata]` dependency flow that was lost in the previous `chain.py` refactor. The two changes are coupled: `FallbackModel` is the framework's idiomatic fallback mechanism, and `RunContext` is the framework's idiomatic deps mechanism — replacing the hand-rolled chain with `FallbackModel` clears the path to restoring `RunContext` cleanly.

## Non-goals

- No new provider integrations. (Ollama, Groq, Cerebras, OpenRouter, Vercel, LM Studio remain the full set.)
- No changes to note schemas, routing, vault writing, or rendering.
- No migration to a new PydanticAI major version.
- No per-model retry tuning (the `retries=3` default is preserved; see "Open questions").
- No `Hooks` capability for per-model failure logging (future enhancement, not this scope).

## Context — the regression being fixed

The `feat/unified-llm-chain` branch replaced a single-LM-Studio agent with a 3-tier fallback chain (LM Studio → Vercel → free pool). As a side effect, `agent.py:144-153` lost the typed deps flow and began injecting `TalkMetadata` into the user prompt as a string block.

**Why this matters:** PydanticAI treats `instructions=` and `@agent.instructions` callbacks as **system-channel** content (rules, authoritative state), and the `user_prompt` as **user-channel** content (data). Moving `TalkMetadata` (title, speaker, categories, upload date) from system to user channel weakens the model's adherence — particularly on smaller free-tier models where the LLM is more likely to re-derive or override injected values.

The old `RunContext[TalkMetadata]` pattern via `@agent.instructions` was idiomatic; the refactor traded it for a generic chain abstraction. This design gets the abstraction back without losing deps.

## Architecture

### Before
```
agent.py ──→ call_with_fallback() ──→ for entry in ModelEntry: Agent(model, ...)
                                          (custom retry + custom exception swallow)
             resolve_full_chain()   ──→ probes LM Studio, builds ModelEntry list
             providers.py          ──→ ModelEntry, ProviderConfig, resolve_provider (iterator)
```

### After
```
agent.py ──→ call_with_fallback() ──→ Agent(FallbackModel(*resolve_models()), deps_type=..., ...)
                                          (try/except → None; ~10-line shim)
             resolve_models()      ──→ probes LM Studio, returns flat list[Model]
             providers.py          ──→ ProviderConfig, PROVIDERS, build_models(config) → list[Model]
                                       (ModelEntry deleted; resolve_provider iterator deleted)
```

### Key shifts
1. **Custom retry/exception loop deleted** — `FallbackModel` handles it natively.
2. **`ModelEntry` dataclass deleted** — `FallbackModel` accepts plain `Model` instances.
3. **`resolve_provider()` iterator replaced by `build_models()` flat-list builder** — `FallbackModel` wants a flat list.
4. **`call_with_fallback` becomes a thin shim** that constructs the `Agent` with `FallbackModel`, sets `deps_type`/`deps` if provided, accepts an optional `setup` callback for per-call decorator attachment, and wraps `agent.run()` in `try/except → None`.
5. **Deps flow restored via `RunContext[TalkMetadata]`** — `summarise()` passes deps through to the shim, which builds the `Agent` with `deps_type=TalkMetadata`, and `summarise()` provides a `setup` callback that registers `@agent.instructions` to inject the metadata into the system channel.

## Components

### `src/providers.py` (slimmed)

```python
@dataclass
class ProviderConfig:
    name: str
    api_key_env: str
    provider_type: str            # "openai" | "vercel"
    base_url: str | None = None
    models_env: str | None = None
    models_default: str = ""

    def get_models(self) -> list[str]: ...


def build_models(config: ProviderConfig, shuffle: bool = True) -> list[Model]:
    """Build PydanticAI Model instances for this provider.
    Returns [] if API key missing. Shuffles models for load distribution.
    """
    api_key = os.getenv(config.api_key_env, "")
    if not api_key:
        return []
    models = config.get_models()
    if shuffle:
        random.shuffle(models)
    return [
        OpenAIChatModel(name, provider=_build_provider(config, api_key))
        for name in models
    ]


PROVIDERS: dict[str, ProviderConfig] = { ... }   # unchanged content
```

- **Delete** `ModelEntry` dataclass — `FallbackModel` takes plain `Model`s.
- **Delete** `resolve_provider()` (the iterator) — replaced by `build_models()` returning a flat list.
- **Keep** `ProviderConfig`, `PROVIDERS`, `_build_provider`, `get_models` — unchanged.

### `src/chain.py` (slimmed to shim + list builder)

```python
def _lm_studio_reachable() -> bool:
    """Sync HTTP probe, 3s timeout. False on any error."""
    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    try:
        with httpx.Client(timeout=3.0) as probe:
            probe.get(f"{base_url.rstrip('/')}/models").raise_for_status()
        return True
    except (httpx.HTTPError, httpx.TimeoutException):
        return False


def _build_lm_studio_model() -> Model:
    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    model_name = os.getenv("LM_STUDIO_MODEL", "gemma-4-e4b-it")
    api_key = os.getenv("LM_STUDIO_API_KEY", "") or "x"
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )


def resolve_models() -> list[Model]:
    """Return the ordered model list. LM Studio first if reachable."""
    models: list[Model] = []
    if _lm_studio_reachable():
        models.append(_build_lm_studio_model())
        logger.info("LM Studio reachable — added as primary")

    cloud_providers = ["vercel:paid", "ollama", "groq", "cerebras", "openrouter:free"]
    for name in cloud_providers:
        if config := PROVIDERS.get(name):
            models.extend(build_models(config))
    return models


async def call_with_fallback(
    system_prompt: str,
    user_prompt: str,
    output_type: type[T],
    *,
    deps: Any = None,
    deps_type: type | None = None,
    setup: Callable[[Agent], None] | None = None,
    max_retries: int = 3,
) -> T | None:
    """Run via FallbackModel. Returns first success or None. Never raises."""
    if deps is not None and deps_type is None:
        raise ValueError("deps provided without deps_type")
    if deps_type is not None and deps is None:
        raise ValueError("deps_type provided without deps")

    models = resolve_models()
    if not models:
        logger.error("No providers available")
        return None

    agent_kwargs: dict = {
        "model": FallbackModel(*models),
        "output_type": output_type,
        "instructions": system_prompt,
        "retries": max_retries,
    }
    if deps_type is not None:
        agent_kwargs["deps_type"] = deps_type

    agent = Agent(**agent_kwargs)

    if setup is not None:
        setup(agent)

    run_kwargs: dict = {}
    if deps is not None:
        run_kwargs["deps"] = deps

    try:
        result = await agent.run(user_prompt, **run_kwargs)
        logger.info("Success on fallback chain")
        return result.output
    except Exception as exc:
        logger.error("All providers exhausted: %s", exc)
        return None
```

- **Delete** `_lm_studio_entry()` (returned `ModelEntry`) — replaced by `_build_lm_studio_model()` returning `Model`.
- **Delete** `resolve_full_chain()` and `resolve_cloud_chain()` (returned `list[ModelEntry]`) — replaced by `resolve_models()` returning `list[Model]`.
- **Delete** the `for entry in chain: try/except` loop in `call_with_fallback` — `FallbackModel` handles fallback natively.
- **Keep** the LM Studio reachability probe and per-provider model shuffling.

### `src/agent.py` (deps restored)

The talk branch in `summarise()` reverts to the `RunContext` pattern via the `setup` callback:

```python
def _inject_talk_metadata(ctx: RunContext[TalkMetadata]) -> str:
    d = ctx.deps
    cats = ", ".join(d.categories) if d.categories else "none"
    return (
        f"Title: {d.title}\n"
        f"Speaker: {d.speaker}\n"
        f"Categories: {cats}\n"
        f"Upload date: {d.upload_date.isoformat() if d.upload_date else 'unknown'}"
    )


def _setup_talk_metadata(agent: Agent) -> None:
    agent.instructions(_inject_talk_metadata)


async def summarise(
    text: str,
    content_type: ContentType,
    vault_titles: list[str],
    url: str,
    deps: TalkMetadata | None = None,
) -> AnyNote:
    note_type = _CONTENT_TYPE_TO_MODEL[content_type]

    if content_type == ContentType.talk and deps is not None:
        prompt = _build_talk_prompt(vault_titles, url)
    else:
        prompt = _build_summariser_prompt(content_type, vault_titles, url)

    user_prompt = text[:8000]
    use_deps = content_type == ContentType.talk and deps is not None

    result = await call_with_fallback(
        system_prompt=prompt,
        user_prompt=user_prompt,
        output_type=note_type,
        deps=deps if use_deps else None,
        deps_type=TalkMetadata if use_deps else None,
        setup=_setup_talk_metadata if use_deps else None,
        max_retries=3,
    )
    if result is None:
        raise RuntimeError(f"Summarisation failed — all providers exhausted for {url}")
    return result
```

- `deps_type=TalkMetadata` is set only when `deps is not None`, matching the `call_with_fallback` validation.
- The `setup` callback is only provided in the talk+deps branch; non-talk calls get no `deps_type` and no `setup`.
- `deps` is plumbed all the way through; the LLM sees `TalkMetadata` in the system channel via `RunContext`.

## Data flow (talk URL example)

```
main.py:run_pipeline(url)
    │
    ├── fetch(url)                         → text, yt_metadata
    ├── resolve_content_type(url, text)    → ContentType.talk (unambiguous domain)
    ├── get_titles()                       → vault_titles
    ├── TalkMetadata(...)                  → talk_deps
    │
    └── summarise(text, talk, titles, url, deps=talk_deps)
            │
            ├── prompt     = _build_talk_prompt(titles, url)  # static rules
            ├── user_data  = text[:8000]                      # transcript
            ├── setup      = _setup_talk_metadata (attaches _inject_talk_metadata)
            │
            └── call_with_fallback(prompt, user_data, TalkNote,
                                    deps=talk_deps, deps_type=TalkMetadata,
                                    setup=_setup_talk_metadata)
                    │
                    ├── resolve_models()
                    │     ├── _lm_studio_reachable() → True
                    │     ├── _build_lm_studio_model() → [lmstudio]
                    │     ├── build_models(vercel:paid)        → [...]
                    │     ├── build_models(ollama)             → [...]
                    │     ├── build_models(groq)               → [...]
                    │     ├── build_models(cerebras)           → [...]
                    │     └── build_models(openrouter:free)    → [...]
                    │
                    ├── Agent(
                    │     model=FallbackModel(*models),
                    │     deps_type=TalkMetadata,
                    │     output_type=TalkNote,
                    │     instructions=prompt,
                    │     retries=3,
                    │ )
                    │
                    ├── setup(agent)  # attaches @agent.instructions
                    │
                    └── try: await agent.run(user_data, deps=talk_deps)
                            except Exception: return None
                    ↓
                    FallbackModel tries models in order; on exception tries the next
                    ↓
                    return result.output (TalkNote)
```

What the LLM sees, in order:
1. **`instructions=` (system)** — static rules from `_build_talk_prompt()`: schema name, meta fields, vault titles for grounding, reflection rules.
2. **`@agent.instructions` callback (system)** — dynamic block from `inject_talk_metadata`: `Title: …`, `Speaker: …`, `Categories: …`, `Upload date: …`. PydanticAI concatenates these with the static `instructions` and sends them as the system message.
3. **`user_prompt` (user)** — `text[:8000]` (the transcript).

Title, speaker, and categories are now in the **system channel**, which is the correct location for authoritative data the model must not override.

For non-talk notes, `deps` is `None`, so `deps_type` and `setup` are omitted; the flow collapses to the same shape minus the deps branch.

### Structured output (explicit)

`output_type=note_type` (e.g. `TalkNote`) is set on every call. PydanticAI's default output mode is **`ToolOutput`**: the model is told to call a tool whose argument schema matches the Pydantic class, the response is parsed, and Pydantic validates it. On validation failure, PydanticAI retries up to `retries=3` with the error in the feedback message.

`ToolOutput` is the right choice because it works with all providers in the chain (LM Studio, Vercel, Ollama, Groq, Cerebras, OpenRouter), unlike `NativeOutput` which is restricted to OpenAI/Anthropic/Google. `output_type` is never `str` or a union containing `str` — see the PydanticAI common-gotchas note in the testing section.

## Error handling

Five error categories, each with a different contract.

### 1. LM Studio unreachable
- **Where:** `_lm_studio_reachable()` in `chain.py`.
- **Behavior:** `httpx` raises → caught → return `False` → `resolve_models()` skips LM Studio, proceeds to cloud. Silent by design.
- **Logging:** `logger.info("LM Studio reachable — added as primary")` only fires when reachable; absence = laptop off. No error log.
- **User-visible:** None.

### 2. Single provider fails mid-call
- **Where:** Inside `FallbackModel`. Catches the exception and tries the next model.
- **Behavior:** Transparent to caller.
- **Logging:** `FallbackModel` does not log per-model failures by default. Acceptable for this scope; future enhancement: `Hooks` capability with `on.model_request_error`. Out of scope here.
- **User-visible:** None.

### 3. All providers exhausted
- **Where:** `call_with_fallback` shim — `try/except Exception` around `agent.run()`.
- **Behavior:** Returns `None`.
- **Logging:** `logger.error("All providers exhausted: %s", exc)`.
- **Call-site handling:**
  - `classify()`: returns `ContentType.article` as safe default (existing behavior).
  - `summarise()`: raises `RuntimeError("Summarisation failed — all providers exhausted for {url}")`.
  - `main.py:95` top-level `except Exception` catches, prints, exits 1.
  - `bot.py`: same shape — catches and replies to user with error.

### 4. Deps contract violations
The `call_with_fallback` shim validates deps consistency before constructing the Agent:

| Case | Detection | Behavior |
|---|---|---|
| `deps` set without `deps_type` | `raise ValueError` before Agent construction | Programming error → propagates → bot replies with error. |
| `deps_type` set without `deps` | `raise ValueError` before Agent construction | Same. |
| `setup` callback raises | Caught by `try/except` → returns `None` → "all providers exhausted" path. **Mitigation:** `logger.exception("setup callback failed")` makes the actual error visible in logs. Re-raising as a separate exception type is a future enhancement. | Logged loudly, not silently lost. |

### 5. Pydantic validation failures
- **Where:** Inside `ToolOutput` mode.
- **Behavior:** PydanticAI retries up to `retries=3` per model attempt. If all retries fail, the underlying exception is raised.
- **Where it lands:** Caught by `call_with_fallback`'s `try/except` → `None` → "all providers exhausted".
- **Known caveat:** Retries happen *per model*, not *per chain*. A consistently-malforming model burns all 3 retries before `FallbackModel` moves on. Out of scope to change here, but flagged as a future enhancement.

## Testing

### `tests/test_providers.py`
- `TestProviderConfig.test_get_models_from_env` — unchanged.
- `TestProviderConfig.test_get_models_from_default` — unchanged.
- `TestProviderConfig.test_returns_empty_when_no_key` — update to call `build_models(config)` instead of the deleted `resolve_provider(config)`.
- `TestBuildModels.test_yields_model_instances_for_valid_config` (renamed) — assert return is `list[Model]`.
- `TestBuildModels.test_vercel_provider_type` (renamed) — same.

### `tests/test_chain.py`
- `TestResolveModels.test_includes_lm_studio_when_reachable` — unchanged behavior, rename from `TestResolveFullChain`.
- `TestResolveModels.test_skips_lm_studio_when_unreachable` — unchanged.
- DELETE `TestResolveCloudChain` — no separate cloud chain anymore.
- `TestCallWithFallback`:
  - `test_returns_first_success` — patch `resolve_models` to return `[FunctionModel(...)]`, assert shim returns `.output`.
  - `test_returns_none_when_all_fail` — same patching, `FunctionModel` raises on every call.
  - NEW `test_setup_callback_attaches_instructions` — use `FunctionModel` to capture messages; assert the `inject_talk_metadata` block appears in the system instructions.
  - NEW `test_deps_passed_to_agent_run` — assert `agent.run` awaited with `deps=talk_deps`.
  - NEW `test_no_deps_kwarg_when_deps_is_none` — assert `agent.run` awaited without `deps`.
  - NEW `test_raises_when_deps_set_without_deps_type` — assert `ValueError`.
  - NEW `test_raises_when_deps_type_set_without_deps` — assert `ValueError`.

### `tests/test_summariser.py`
- All existing tests that mock `call_with_fallback` keep working unchanged (the shim signature is backward-compatible: `system_prompt`, `user_prompt`, `output_type`).
- **REWRITE** `test_summarise_talk_with_deps_injects_metadata` (currently `tests/test_summariser.py:179-204`): the test codifies the old buggy behavior (asserts metadata in `user_prompt`). New behavior: assert `call_with_fallback` is called with `deps=talk_deps`, `deps_type=TalkMetadata`, and a non-None `setup` callable.
- The behavior the test was protecting — *"metadata reaches the LLM"* — is now covered by `test_chain.py::test_setup_callback_attaches_instructions` using `FunctionModel` to inspect the system message.

### `tests/test_integration.py`
- No changes required. The `summarise` mock's signature is unchanged.

### PydanticAI common-gotcha audit
Per the skill: *"if your union includes `str` (or no `output_type` is set), the model can return plain text instead of structured output"*. Our `output_type` is always one of the 6 `*Note` classes, never `str`, never a union with `str`. Add an inline comment in `call_with_fallback` noting this constraint so future contributors don't loosen it.

### Test totals (target)
Current branch: 95 tests passing. Target after this refactor: ~105 tests (6 new in `test_chain`, 1 rewrite in `test_summariser`, 2 net additions from the rename in `test_providers`).

### End-to-end manual verification
- `uv run python -c "from src.chain import resolve_models; print(resolve_models())"` — should print a list of PydanticAI `Model` instances.
- `uv run python -m src.main <youtube_url> --dry-run` — verify the rendered Markdown uses the yt-dlp title verbatim (not a re-summarised title).
- `uv run python -m src.main <article_url> --dry-run` — verify the no-deps path still works.

## Open questions / deferred decisions

1. **Per-model failure logging via `Hooks` capability.** The skill's `ARCHITECTURE.md` capability decision tree recommends `Hooks` with `on.model_request_error` for per-model failure visibility. Not in this scope; can be added later without touching the design.
2. **Retry scope (per-model vs per-chain).** `retries=3` currently applies to each model attempt. A future enhancement could move retries to the chain level, but requires custom retry logic. Flagged, not addressed.
3. **Setup callback exception handling.** Currently caught and routed through the "all providers exhausted" path with `logger.exception`. A future enhancement could define a `SetupError` exception type and re-raise it, distinguishing programming errors from provider errors. Flagged, not addressed.
4. **Caching `resolve_models()`.** Currently resolved per call. `FallbackModel` construction is cheap and per-call re-evaluation picks up env var changes and LM Studio reachability changes. Acceptable; revisit if profiling shows a bottleneck.

## File-level change summary

| File | Action | Notes |
|---|---|---|
| `src/providers.py` | Modify | Delete `ModelEntry`; delete `resolve_provider`; rename to `build_models` returning `list[Model]`. |
| `src/chain.py` | Modify | Delete `_lm_studio_entry`, `resolve_full_chain`, `resolve_cloud_chain`, custom retry loop. Add `setup` parameter to `call_with_fallback`. Add deps consistency validation. |
| `src/agent.py` | Modify | Restore `RunContext` deps flow via `setup` callback in `summarise()`. Remove user-prompt string injection of `TalkMetadata`. |
| `tests/test_providers.py` | Modify | Rename test class, update to call `build_models`. |
| `tests/test_chain.py` | Modify | Restructure around `resolve_models`. Add 6 new tests for deps + setup + validation. |
| `tests/test_summariser.py` | Modify | Rewrite `test_summarise_talk_with_deps_injects_metadata` to assert new behavior. |
| `tests/test_integration.py` | No change | Mocks signature is unchanged. |
| `AGENTS.md` | Modify | Note the `FallbackModel` adoption and `RunContext` deps restoration. (Optional; can be done as docs follow-up.) |

## References

- PydanticAI skill: `building-pydantic-ai-agents`
  - `AGENTS-CORE.md` — `RunContext`, `@agent.instructions`, `FallbackModel` patterns
  - `ARCHITECTURE.md` — output-mode comparison, capability decision tree
  - Common gotchas: `output_type` unions with `str`; model-string prefixes
- Prior implementation plan: `plans/2026-06-03-unified-llm-chain.md` (the implementation that introduced the regression)
- Branch: `feat/unified-llm-chain`
- Regression site: `src/agent.py:144-153` (old) → restored in this design

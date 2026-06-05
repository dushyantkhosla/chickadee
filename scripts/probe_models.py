"""Probe every reachable (provider, model) pair in the chickadee provider
chain using the same Pydantic AI structured-output calls chickadee makes in
production. Reports which combinations fail with the
``finish_reason='tool-calls'`` validation error (or any other failure mode)
so the culprit model can be isolated without touching the live bot.

Runs the same two call types chickadee uses against each model:
  1. classify   — Agent(output_type=ContentType)           ← small enum output
  2. summarise  — Agent(output_type=ArticleNote)           ← nested BaseModel

Pydantic AI's Agent ``retries`` is forced to 0 so the first failure surfaces
immediately rather than being masked by internal schema-validation retries
(the production chain sets ``retries=3`` which obscures the source).

Run:
    uv run python -m scripts.probe_models
    # or, inside the running container (the env is already loaded):
    docker compose exec chickadee python -m scripts.probe_models

To exercise more Vercel models than the single default, set:
    export VERCEL_PAID_MODEL='anthropic/claude-3-5-haiku,openai/gpt-oss-20b,google/gemini-2.5-flash'
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import date

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

# Make `src.*` importable when the script is invoked directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.chain import _build_lm_studio_model, _lm_studio_reachable  # noqa: E402
from src.models import ArticleNote, ContentType  # noqa: E402
from src.providers import PROVIDERS, build_models  # noqa: E402


# ── Synthetic inputs (deterministic, no network) ──────────────────────────
# A short article-style paragraph so classification has something to chew on
# and the summariser call exercises a realistic nested-BaseModel output.
SYNTHETIC_TEXT = (
    "Anthropic's Institute published an essay on recursive self-improvement "
    "in frontier AI systems. The author argues that safety evaluations must "
    "evolve alongside model capabilities and proposes a three-tier oversight "
    "framework covering pre-deployment testing, runtime monitoring, and "
    "external audits. Concrete data points include references to scaling "
    "laws and capability-elicitation benchmarks from recent papers."
)

# Mirrors the shape of _CLASSIFIER_SYSTEM_PROMPT in src/agent.py
CLASSIFIER_SYSTEM = (
    "You are a content classifier. Classify the text into exactly one of: "
    "talk, article, paper, essay, repo, field. Default to 'article' if uncertain."
)

# Mirrors the shape of _build_summariser_prompt for ContentType.article in
# src/agent.py — full schema guidance and nested-meta instructions, so the
# model has the same context it gets in production.
SUMMARISER_SYSTEM = (
    f'You are a research assistant. Summarise the provided content into a structured article note.\n\n'
    f'Output must conform exactly to this Pydantic schema: ArticleNote\n\n'
    f'The output has a nested "meta" object. It MUST include:\n'
    f'- meta.tags: list of kebab-case topic tags\n'
    f'- meta.source_url: the URL provided below\n'
    f'- meta.source_type: "article"\n'
    f'- meta.ingested_on: today\'s date\n'
    f'- meta.builds_on, meta.see_also, meta.contradicts: leave as empty lists []\n\n'
    f'Rules:\n'
    f'- meta.source_url must be "https://example.com/test"\n'
    f'- meta.source_type must be "article"\n'
    f'- meta.ingested_on must be "{date.today().isoformat()}"\n'
    f'- Reflection: always include a reflection object with individual fields set to null unless there is genuine insight. Do not set the entire reflection to null. Do not pad with generic text.\n'
)


# ── Probe runner ──────────────────────────────────────────────────────────

async def probe(
    model: OpenAIChatModel,
    output_type: type,
    system: str,
    user: str,
) -> tuple[str, str]:
    """Run a single Pydantic AI structured-output call. Returns (status, detail)."""
    try:
        agent = Agent(
            model=model,
            output_type=output_type,
            instructions=system,
            retries=0,  # surface the first failure
        )
        result = await agent.run(user)
        return "PASS", repr(result.output)[:120]
    except Exception as exc:
        msg = str(exc)
        # The specific bug we are hunting: Pydantic AI rejecting the
        # non-canonical 'tool-calls' finish_reason string from the wire.
        if "tool-calls" in msg or "literal_error" in msg:
            kind = "tool-calls"
        elif "401" in msg or "Unauthorized" in msg or "API key" in msg or "api_key" in msg.lower():
            kind = "auth"
        elif "404" in msg:
            kind = "404"
        elif "429" in msg or "rate" in msg.lower():
            kind = "rate-limit"
        else:
            kind = type(exc).__name__
        # Pull the most informative single line (the offending value, not the
        # full Pydantic traceback) so the report stays scannable. For HTTP
        # errors we want the status code, body, or URL fragment instead.
        if "ModelHTTPError" in kind or "HTTP" in kind:
            for ln in msg.splitlines():
                if any(s in ln for s in ("status_code", "model_name", "body:", "URL:", "Error message:")):
                    return f"FAIL ({kind})", ln.strip()[:200]
        detail = next(
            (ln.strip() for ln in msg.splitlines() if "input_value" in ln or "Input should be" in ln),
            msg.splitlines()[0],
        )
        return f"FAIL ({kind})", detail[:200]


def _candidates() -> list[tuple[str, OpenAIChatModel]]:
    """Enumerate the exact (provider_key, model) list chain.resolve_models()
    would build — minus FallbackModel — so each is probed in isolation."""
    out: list[tuple[str, OpenAIChatModel]] = []
    if _lm_studio_reachable():
        out.append(("lmstudio", _build_lm_studio_model()))
    for key, cfg in PROVIDERS.items():
        for m in build_models(cfg, shuffle=False):
            out.append((key, m))
    return out


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    print("=" * 78)
    print("chickadee — provider/model probe")
    print("=" * 78)

    candidates = _candidates()
    if not candidates:
        print("No providers reachable.")
        print("  - Start LM Studio (LM_STUDIO_BASE_URL), OR")
        print("  - Set VERCEL_AI_GATEWAY_API_KEY / OPENROUTER_API_KEY / GROQ_API_KEY / etc.")
        return

    for label, model in candidates:
        print(f"  + {label:18s} {model.model_name}")
    print()
    print(f"Probing {len(candidates)} (provider, model) pairs x 2 call types each")
    print("-" * 78)
    print(f"{'provider':18s} {'model':42s} {'classify':22s} {'summarise':22s}")
    print("-" * 78)

    rows: list[tuple[str, str, str, str, str, str]] = []
    for label, model in candidates:
        c_status, c_detail = await probe(model, ContentType, CLASSIFIER_SYSTEM, SYNTHETIC_TEXT)
        s_status, s_detail = await probe(model, ArticleNote, SUMMARISER_SYSTEM, SYNTHETIC_TEXT)
        rows.append((label, model.model_name, c_status, s_status, c_detail, s_detail))
        print(f"{label:18s} {model.model_name:42s} {c_status:22s} {s_status:22s}")

    print("-" * 78)

    # ── Verdict ───────────────────────────────────────────────────────────
    tool_calls = [r for r in rows if "tool-calls" in r[2] or "tool-calls" in r[3]]
    validation = [
        r for r in rows
        if "UnexpectedModelBehavior" in r[2] or "UnexpectedModelBehavior" in r[3]
        or "ValidationError" in r[2] or "ValidationError" in r[3]
    ]
    rate_limited = [r for r in rows if "rate-limit" in r[2] or "rate-limit" in r[3]]
    fails = [r for r in rows if "FAIL" in r[2] or "FAIL" in r[3]]
    passes = [r for r in rows if r[2] == "PASS" and r[3] == "PASS"]

    print()
    print("Verdict")
    print("-" * 78)
    if tool_calls:
        print(f"  {len(tool_calls)} (provider, model) emitted finish_reason='tool-calls':")
        for label, name, c, s, cdet, sdet in tool_calls:
            print(f"    - {label}/{name}")
            print(f"        classify  : {cdet}")
            print(f"        summarise : {sdet}")
    if validation:
        print(f"  {len(validation)} structured-output validation failure(s) (model returned output that did not match the Pydantic schema):")
        for label, name, c, s, cdet, sdet in validation:
            print(f"    - {label}/{name}")
            if "FAIL" in c:
                print(f"        classify  : {cdet}")
            if "FAIL" in s:
                print(f"        summarise : {sdet}")
    if rate_limited:
        print(f"  {len(rate_limited)} rate-limited (try again later or with a different model):")
        for label, name, c, s, cdet, sdet in rate_limited:
            print(f"    - {label}/{name}")
    other = [r for r in fails if r not in tool_calls and r not in validation and r not in rate_limited]
    if other:
        print(f"  {len(other)} other failure(s) (auth/404/etc.):")
        for label, name, c, s, cdet, sdet in other:
            print(f"    - {label}/{name}")
            if "FAIL" in c:
                print(f"        classify  : {cdet}")
            if "FAIL" in s:
                print(f"        summarise : {sdet}")
    if passes:
        print(f"  {len(passes)} clean pass(es): {[f'{l}/{n}' for l, n, *_ in passes]}")
    if not fails and not tool_calls:
        print("  All probed combinations passed. The original failure may be transient.")

    print()
    print("To test more Vercel models, set a comma-separated list, e.g.:")
    print("  export VERCEL_PAID_MODEL='anthropic/claude-3-5-haiku,openai/gpt-oss-20b,google/gemini-2.5-flash'")


if __name__ == "__main__":
    asyncio.run(main())

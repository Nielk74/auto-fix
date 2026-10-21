"""Optional OpenTelemetry export of workflow runs to a self-hosted Arize Phoenix.

Without configuration every helper is a no-op, so the core workflow needs no tracing packages.
LangGraph node spans come from the OpenInference LangChain instrumentor; model calls use plain
HTTP, so they get explicit OpenInference LLM spans here.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

ENDPOINT_ENV = "AUTO_FIX_TRACE_ENDPOINT"
PROJECT_ENV = "AUTO_FIX_TRACE_PROJECT"

_provider: Any = None
_tracer: Any = None


def configure(endpoint: str | None = None, project: str | None = None) -> bool:
    """Start exporting spans; the environment fills in values missing from configuration."""
    global _provider, _tracer
    endpoint = endpoint or os.environ.get(ENDPOINT_ENV)
    if not endpoint:
        return False
    if _provider is not None:
        return True
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from phoenix.otel import register
    except ImportError as exc:
        raise RuntimeError(
            "Tracing needs the optional packages: uv sync --locked --extra trace"
        ) from exc
    # A batch processor exports on a background thread, so an unreachable collector never
    # delays builds or model calls.
    _provider = register(
        endpoint=endpoint,
        project_name=project or os.environ.get(PROJECT_ENV) or "auto-fix",
        batch=True,
        set_global_tracer_provider=False,
        verbose=False,
    )
    LangChainInstrumentor().instrument(tracer_provider=_provider)
    _tracer = _provider.get_tracer("auto_fix")
    return True


def shutdown() -> None:
    global _provider, _tracer
    if _provider is None:
        return
    from openinference.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().uninstrument()
    _provider.force_flush(timeout_millis=10000)
    _provider.shutdown()
    _provider = _tracer = None


def session(run_id: str):
    """Group every span of one graph run as a Phoenix session."""
    if _tracer is None:
        return nullcontext()
    from openinference.instrumentation import using_session

    return using_session(run_id)


@contextmanager
def model_span(kind: str, model: str, context: dict[str, Any]) -> Iterator[Any]:
    """Yield ``finish(response, usage, error)`` to record one model call as an LLM span."""
    if _tracer is None:
        yield lambda *_args, **_kwargs: None
        return
    from openinference.instrumentation.langchain import get_current_span
    from opentelemetry.trace import Status, StatusCode, set_span_in_context

    from auto_fix.workflow import redact

    # The instrumentor does not make node spans current, so parent the call on its node explicitly.
    node = get_current_span()
    parent = set_span_in_context(node) if node is not None else None
    with _tracer.start_as_current_span(f"model.{kind}", context=parent) as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("llm.model_name", model)
        span.set_attribute("input.mime_type", "application/json")
        span.set_attribute("input.value", redact(json.dumps(context, ensure_ascii=False)))

        def finish(response: Any, usage: dict[str, Any], error: str | None) -> None:
            if response is not None:
                span.set_attribute("output.mime_type", "application/json")
                span.set_attribute("output.value", redact(json.dumps(response, ensure_ascii=False)))
            for name, keys in {
                "prompt": ("prompt_tokens", "input_tokens"),
                "completion": ("completion_tokens", "output_tokens"),
                "total": ("total_tokens",),
            }.items():
                value = next((usage[key] for key in keys if isinstance(usage.get(key), int)), None)
                if value is not None:
                    span.set_attribute(f"llm.token_count.{name}", value)
            if error:
                span.set_status(Status(StatusCode.ERROR, error))

        yield finish

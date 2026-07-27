"""
Telemetry Module — centralized Mistral observability + local trace logging.

Provides:
- configure_telemetry() on the shared Mistral client (redaction=True, provider="dedicated")
- get_telemetry_tracer() for manual span instrumentation across services
- Custom span attributes (credit_dossier.*) for filtering on the Mistral dashboard

Mistral SDK API (v2.7+):
- configure_telemetry(client, provider="dedicated", redaction=True)
- get_telemetry_tracer(client, "service-name") → OpenTelemetry Tracer
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mistralai.client import Mistral

logger = logging.getLogger(__name__)

# ── Module State ─────────────────────────────────────────────────────
_telemetry_configured = False
_tracer = None


def setup_telemetry(client: "Mistral") -> None:
    """
    Configure Mistral's built-in telemetry on the given client.

    Called once when the Mistral client is first created.
    Uses redaction=True to protect sensitive financial data in traces.
    Sends traces to Mistral's dedicated telemetry backend.
    """
    global _telemetry_configured, _tracer

    if _telemetry_configured:
        return

    try:
        from mistralai.extra.observability import configure_telemetry, get_telemetry_tracer

        # Configure with redaction=True for production safety (financial data)
        configure_telemetry(client, provider="dedicated", redaction=True)

        # Get the tracer for manual span instrumentation
        _tracer = get_telemetry_tracer(client, "credit-dossier-api")

        _telemetry_configured = True
        logger.info(
            "✓ Mistral telemetry configured (provider=dedicated, redaction=True, "
            "tracer=credit-dossier-api)"
        )

    except ImportError as e:
        logger.warning(
            f"Mistral observability extras not available: {e}. "
            f"Install with: pip install 'mistralai[telemetry]'"
        )
    except Exception as e:
        logger.error(f"Failed to configure Mistral telemetry: {e}", exc_info=True)


def init_phoenix_telemetry(project_name: str = "credit-dossier-api") -> None:
    """
    Initializes OpenTelemetry tracing globally for Arize Phoenix.
    Automatically reads PHOENIX_API_KEY and PHOENIX_COLLECTOR_ENDPOINT from env.
    Uses OpenInference to instrument the Mistral client and send LLM traces to Phoenix.
    This runs alongside Mistral's native dedicated telemetry.
    """
    try:
        from phoenix.otel import register
        from openinference.instrumentation.mistralai import MistralAIInstrumentor

        # 1. Register Phoenix as the global OpenTelemetry provider
        tracer_provider = register(
            project_name=project_name,
            set_global_tracer_provider=True,
            batch=False  # Good for local development/immediate visibility
        )

        # 2. Enable Auto-Instrumentation for LLM SDKs
        MistralAIInstrumentor().instrument(tracer_provider=tracer_provider)
        
        logger.info(f"✓ Phoenix OpenInference telemetry configured (project={project_name})")

    except ImportError as e:
        logger.warning(
            f"Phoenix instrumentation not available: {e}. "
            f"Install with: pip install arize-phoenix-otel openinference-instrumentation-mistralai"
        )
    except Exception as e:
        logger.error(f"Failed to configure Phoenix telemetry: {e}", exc_info=True)


def get_tracer():
    """
    Return the OpenTelemetry tracer for manual span creation.

    Usage:
        tracer = get_tracer()
        if tracer:
            with tracer.start_as_current_span("my_operation") as span:
                span.set_attribute("credit_dossier.section_key", "executive_summary")
                ...

    Returns None if telemetry is not configured.
    """
    return _tracer


@contextmanager
def trace_span(name: str, **attributes):
    """
    Convenience context manager for creating traced spans with custom attributes.

    Automatically handles the case where telemetry is not configured.

    Usage:
        with trace_span("generate_section", section_key="exec_summary", deal_id="123"):
            # ... do work ...

    Args:
        name: The span name
        **attributes: Custom attributes to set (auto-prefixed with credit_dossier.)
    """
    tracer = get_tracer()
    if tracer:
        with tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                span.set_attribute(f"credit_dossier.{key}", str(value))
            yield span
    else:
        yield None


def is_telemetry_enabled() -> bool:
    """Check if telemetry has been successfully configured."""
    return _telemetry_configured


# ── Custom Attribute Helpers ─────────────────────────────────────────
# These helpers ensure consistent attribute naming across all services.
# All custom attributes use the "credit_dossier." prefix for Mistral dashboard filtering.


def set_span_attributes(span, **kwargs) -> None:
    """
    Set custom span attributes with the `credit_dossier.` prefix.

    Provides consistent naming for filtering on the Mistral dashboard.

    Args:
        span: The OpenTelemetry span to annotate
        **kwargs: Key-value pairs to set as attributes.
                  Keys are automatically prefixed with "credit_dossier."

    Example:
        set_span_attributes(span,
            deal_id="deal-123",
            section_key="executive_summary",
            operation="generate",
        )
        # Sets:
        #   credit_dossier.deal_id = "deal-123"
        #   credit_dossier.section_key = "executive_summary"
        #   credit_dossier.operation = "generate"
    """
    if span is None:
        return
    for key, value in kwargs.items():
        span.set_attribute(f"credit_dossier.{key}", str(value))


def set_gen_ai_attributes(span, **kwargs) -> None:
    """
    Set standard gen_ai.* attributes on a span (OpenTelemetry semantic conventions).

    Args:
        span: The OpenTelemetry span
        **kwargs: Key-value pairs (keys use gen_ai.* naming)
    """
    if span is None:
        return
    for key, value in kwargs.items():
        span.set_attribute(f"gen_ai.{key}", str(value))

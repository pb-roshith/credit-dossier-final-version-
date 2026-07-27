"""
Telemetry Module — centralized Mistral observability + local trace logging.

Provides:
- configure_telemetry() on the shared Mistral client (redaction=True, provider="dedicated")
- get_telemetry_tracer() for manual span instrumentation across services
- Optional MLflow integration when installed
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

        # Set up additional trace logging (MLflow if available)
        _setup_trace_logging()

    except ImportError as e:
        logger.warning(
            f"Mistral observability extras not available: {e}. "
            f"Install with: pip install 'mistralai[telemetry]'"
        )
    except Exception as e:
        logger.error(f"Failed to configure Mistral telemetry: {e}", exc_info=True)


def _setup_trace_logging() -> None:
    """
    Configure optional MLflow trace logging alongside Mistral's backend.

    Traces always flow to Mistral's dedicated dashboard regardless.
    MLflow adds a local trace UI for deeper analysis.
    """
    try:
        import mlflow

        mlflow.set_experiment("credit-dossier-telemetry")
        mlflow.opentelemetry.autolog()

        logger.info(
            "MLflow trace logging enabled (experiment=credit-dossier-telemetry). "
            "View traces at: mlflow ui --port 5000"
        )
    except ImportError:
        logger.info(
            "MLflow not installed — traces flow to Mistral's dashboard only. "
            "Install mlflow for local trace UI: pip install mlflow"
        )
    except Exception as e:
        logger.warning(f"MLflow setup failed ({e}) — traces flow to Mistral only")


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

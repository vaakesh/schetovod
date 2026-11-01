import logging

import pytest
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import Decision, ParentBased
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    SpanKind,
    TraceFlags,
)

from core.config import settings
from core.telemetry import (
    SkipOrphanClients,
    is_health_check,
    not_from_exporter,
    setup_telemetry,
)

TRACE_ID = 1


def sampled_parent() -> Context:
    return trace.set_span_in_context(
        span=NonRecordingSpan(
            context=SpanContext(
                trace_id=TRACE_ID,
                span_id=1,
                is_remote=False,
                trace_flags=TraceFlags(
                    TraceFlags.SAMPLED,
                ),
            ),
        ),
    )


def decision(
    kind: SpanKind,
    parent: Context | None,
) -> Decision:
    return (
        ParentBased(
            root=SkipOrphanClients(),
        )
        .should_sample(
            parent_context=parent,
            trace_id=TRACE_ID,
            name="SELECT",
            kind=kind,
        )
        .decision
    )


def test_a_query_without_a_request_makes_no_trace() -> None:
    assert (
        decision(
            kind=SpanKind.CLIENT,
            parent=None,
        )
        is Decision.DROP
    )


def test_a_query_inside_a_request_is_kept() -> None:
    assert (
        decision(
            kind=SpanKind.CLIENT,
            parent=sampled_parent(),
        )
        is Decision.RECORD_AND_SAMPLE
    )


@pytest.mark.parametrize(
    argnames="kind",
    argvalues=[
        SpanKind.SERVER,
        SpanKind.CONSUMER,
        SpanKind.PRODUCER,
    ],
)
def test_requests_and_tasks_start_a_trace(
    kind: SpanKind,
) -> None:
    assert (
        decision(
            kind=kind,
            parent=None,
        )
        is Decision.RECORD_AND_SAMPLE
    )


def test_only_the_health_path_is_excluded() -> None:
    assert is_health_check(
        scope={"path": "/health"},
    )
    assert not is_health_check(
        scope={"path": "/invoices"},
    )


def test_exporter_records_are_not_shipped() -> None:
    def record(
        name: str,
    ) -> logging.LogRecord:
        return logging.LogRecord(
            name=name,
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="",
            args=None,
            exc_info=None,
        )

    assert not not_from_exporter(
        record=record(
            name="opentelemetry.exporter.otlp",
        ),
    )
    assert not_from_exporter(
        record=record(
            name="traffic.tasks",
        ),
    )


def test_no_endpoint_means_no_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        target=settings,
        name="otel_exporter_otlp_traces_endpoint",
        value="",
    )

    assert (
        setup_telemetry(
            serve_metrics=True,
        )
        is None
    )


def test_the_sdk_switch_turns_telemetry_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        target=settings,
        name="otel_exporter_otlp_traces_endpoint",
        value="http://otel-collector:4318/v1/traces",
    )
    monkeypatch.setattr(
        target=settings,
        name="otel_sdk_disabled",
        value=True,
    )

    assert (
        setup_telemetry(
            serve_metrics=True,
        )
        is None
    )

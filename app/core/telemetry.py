"""logs and traces go to the shared otel-collector, Prometheus scrapes the metrics itself"""

import logging
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any
from wsgiref.simple_server import WSGIServer

from opentelemetry import _logs, metrics, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import DropAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    Decision,
    ParentBased,
    Sampler,
    SamplingResult,
)
from opentelemetry.trace import Link, SpanKind, TraceState
from opentelemetry.util.types import Attributes
from prometheus_client import start_http_server

from core.config import settings
from core.db import get_engine

# the port inside the container: nginx proxies only 8000, so it never faces the internet
METRICS_PORT = 9000
# seconds, a stopped collector must not hold a request or a deploy
EXPORT_TIMEOUT = 5
# uvicorn keeps its own records away from the root logger, and the app writes there too
SHIPPED_LOGGERS = (None, "uvicorn")
# a line for every call to aQsi or OpenAI, the spans carry the same,
# and a line every minute from the schedule polling
QUIET_LOGGERS = ("httpx", "httpx2", "taskiq.redis_schedule_source")
# taskiq reads the process of the parent, process_* metrics show the real one
DROPPED_METRICS = ("worker_cpu_utilization", "worker_memory_utilization")
HEALTH_PATH = "/health"

logger = logging.getLogger(
    name=__name__,
)


class SkipOrphanClients(Sampler):
    """a query without a request or a task above it, /health alone repeats them every few seconds"""

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        return SamplingResult(
            decision=Decision.DROP
            if kind is SpanKind.CLIENT
            else Decision.RECORD_AND_SAMPLE,
            attributes=attributes,
        )

    def get_description(self) -> str:
        return "SkipOrphanClients"


@dataclass(
    kw_only=True,
    slots=True,
)
class Telemetry:
    tracer_provider: TracerProvider
    logger_provider: LoggerProvider
    meter_provider: MeterProvider
    log_handler: LoggingHandler
    metrics_server: WSGIServer | None


def is_health_check(
    scope: MutableMapping[str, Any],
) -> bool:
    """the probes of compose would be nearly all the traces and metrics"""
    return scope.get("path") == HEALTH_PATH


def not_from_exporter(
    record: logging.LogRecord,
) -> bool:
    """a failed export writes a record, shipping it would feed the same failure"""
    return not record.name.startswith("opentelemetry")


def setup_tracing(
    resource: Resource,
) -> TracerProvider:
    provider = TracerProvider(
        sampler=ParentBased(
            root=SkipOrphanClients(),
        ),
        resource=resource,
        shutdown_on_exit=False,
    )
    provider.add_span_processor(
        span_processor=BatchSpanProcessor(
            span_exporter=OTLPSpanExporter(
                timeout=EXPORT_TIMEOUT,
            ),
        ),
    )
    trace.set_tracer_provider(
        tracer_provider=provider,
    )
    # the package allows sqlalchemy below 2.1 and silently does nothing on a newer one,
    # the events it listens to work on 2.1
    SQLAlchemyInstrumentor().instrument(
        engine=get_engine().sync_engine,
        tracer_provider=provider,
        skip_dep_check=True,
    )
    # covers httpx of aQsi and httpx2 of OpenAI
    HTTPXClientInstrumentor().instrument(
        tracer_provider=provider,
    )
    return provider


def setup_logs(
    resource: Resource,
) -> tuple[LoggerProvider, LoggingHandler]:
    provider = LoggerProvider(
        resource=resource,
        shutdown_on_exit=False,
    )
    provider.add_log_record_processor(
        log_record_processor=BatchLogRecordProcessor(
            exporter=OTLPLogExporter(
                timeout=EXPORT_TIMEOUT,
            ),
        ),
    )
    _logs.set_logger_provider(
        logger_provider=provider,
    )
    handler = LoggingHandler(
        level=logging.INFO,
        logger_provider=provider,
    )
    handler.addFilter(
        filter=not_from_exporter,
    )
    logging.getLogger().setLevel(
        level=logging.INFO,
    )
    for name in SHIPPED_LOGGERS:
        logging.getLogger(
            name=name,
        ).addHandler(
            hdlr=handler,
        )
    for name in QUIET_LOGGERS:
        logging.getLogger(
            name=name,
        ).setLevel(
            level=logging.WARNING,
        )
    return provider, handler


def setup_metrics(
    resource: Resource,
) -> MeterProvider:
    provider = MeterProvider(
        resource=resource,
        shutdown_on_exit=False,
        metric_readers=[
            PrometheusMetricReader(
                prefix="schetovod",
                disable_target_info=True,
                scope_info_enabled=False,
            ),
        ],
        views=[
            View(
                instrument_name=name,
                aggregation=DropAggregation(),
            )
            for name in DROPPED_METRICS
        ],
    )
    metrics.set_meter_provider(
        meter_provider=provider,
    )
    return provider


def setup_telemetry(
    serve_metrics: bool,
) -> Telemetry | None:
    """called inside the final process: the export threads do not survive a fork"""
    if settings.otel_sdk_disabled or not settings.otel_exporter_otlp_traces_endpoint:
        return None
    resource = Resource.create()
    logger_provider, log_handler = setup_logs(
        resource=resource,
    )
    telemetry = Telemetry(
        tracer_provider=setup_tracing(
            resource=resource,
        ),
        logger_provider=logger_provider,
        meter_provider=setup_metrics(
            resource=resource,
        ),
        log_handler=log_handler,
        metrics_server=None,
    )
    if serve_metrics:
        telemetry.metrics_server, _ = start_http_server(
            port=METRICS_PORT,
        )
    # the deploy looks for this line to see that the release reaches Loki
    logger.info(
        "telemetry is ready",
    )
    return telemetry


def shutdown_telemetry(
    telemetry: Telemetry | None,
) -> None:
    """sends what is still in the queues, blocks for up to a few seconds"""
    if telemetry is None:
        return
    if telemetry.metrics_server is not None:
        telemetry.metrics_server.shutdown()
        telemetry.metrics_server.server_close()
    for name in SHIPPED_LOGGERS:
        logging.getLogger(
            name=name,
        ).removeHandler(
            hdlr=telemetry.log_handler,
        )
    telemetry.tracer_provider.shutdown()
    telemetry.logger_provider.shutdown()
    telemetry.meter_provider.shutdown()

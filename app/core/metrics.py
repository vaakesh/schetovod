"""business metrics, they do nothing until setup_telemetry sets the meter provider"""

from opentelemetry import metrics

meter = metrics.get_meter(
    name="schetovod",
)

recognition_duration = meter.create_histogram(
    name="recognition.duration",
    unit="s",
    description="Time of one invoice recognition by its outcome",
    # a long reasoning takes minutes, the default buckets end at 10 seconds
    explicit_bucket_boundaries_advisory=[5, 15, 30, 60, 120, 180, 300, 450, 600],
)
recognition_tokens = meter.create_counter(
    name="recognition.tokens",
    description="OpenAI tokens spent on recognition by type",
)
receipts_loaded = meter.create_counter(
    name="receipts.loaded",
    description="New receipts saved from aQsi",
)
receipts_last_success = meter.create_gauge(
    name="receipts.last_success",
    unit="s",
    description="Unix time of the last finished import of receipts",
)

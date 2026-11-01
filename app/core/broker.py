import logging

from fastapi.concurrency import run_in_threadpool
from taskiq import (
    SmartRetryMiddleware,
    TaskiqEvents,
    TaskiqMessage,
    TaskiqResult,
    TaskiqScheduler,
    TaskiqState,
)
from taskiq.middlewares.opentelemetry_middleware import OpenTelemetryMiddleware
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListRedisScheduleSource, RedisStreamBroker

from core.config import settings
from core.telemetry import setup_telemetry, shutdown_telemetry

# taskiq sets up the logs only for spawned workers, forked ones would lose the failures
logging.basicConfig(
    level=logging.INFO,
)

# seconds, the wait grows by this much with every attempt: 15 minutes, 30, 45
RETRY_STEP = 15 * 60
MAX_RETRY_DELAY = 2 * 60 * 60
# about 7 hours of waiting in all, the next run goes on from where this one stopped
ATTEMPTS = 8
QUEUE_TIME_LABEL = "_taskiq_queue_time"


class TaskTelemetryMiddleware(OpenTelemetryMiddleware):
    """a delayed attempt brings the queue time back as a string, the parent subtracts it
    from a float and fails before the ack, so the stream would repeat the task forever"""

    def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult,
    ) -> None:
        queue_time = message.labels.get(QUEUE_TIME_LABEL)
        if queue_time is not None:
            message.labels[QUEUE_TIME_LABEL] = float(
                queue_time,
            )
        super().post_execute(
            message=message,
            result=result,
        )


# holds the delayed attempts, without it a Redis broker repeats a task at once
delayed_tasks = ListRedisScheduleSource(
    url=settings.redis_url,
)

# a stream keeps a task until the worker confirms it, a killed worker loses nothing
broker = RedisStreamBroker(
    url=settings.redis_url,
).with_middlewares(
    SmartRetryMiddleware(
        default_retry_count=ATTEMPTS,
        default_delay=RETRY_STEP,
        use_delay_exponent=True,
        max_delay_exponent=MAX_RETRY_DELAY,
        schedule_source=delayed_tasks,
    ),
    # carries the trace through the task labels from the sender to the worker
    TaskTelemetryMiddleware(),
)

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[
        LabelScheduleSource(
            broker=broker,
        ),
        delayed_tasks,
    ],
)


# this handler comes first: it is registered before the tasks are imported
@broker.on_event(
    TaskiqEvents.WORKER_STARTUP,
)
async def start_worker_telemetry(
    state: TaskiqState,
) -> None:
    state.telemetry = setup_telemetry(
        serve_metrics=True,
    )


# only the scheduler starts the broker as a client, the api never does
@broker.on_event(
    TaskiqEvents.CLIENT_STARTUP,
)
async def start_scheduler_telemetry(
    state: TaskiqState,
) -> None:
    state.telemetry = setup_telemetry(
        serve_metrics=False,
    )


@broker.on_event(
    TaskiqEvents.WORKER_SHUTDOWN,
    TaskiqEvents.CLIENT_SHUTDOWN,
)
async def stop_telemetry(
    state: TaskiqState,
) -> None:
    await run_in_threadpool(
        func=shutdown_telemetry,
        telemetry=state.telemetry,
    )

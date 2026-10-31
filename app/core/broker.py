import logging

from taskiq import SmartRetryMiddleware, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListRedisScheduleSource, RedisStreamBroker

from core.config import settings

# taskiq sets up the logs only for spawned workers, forked ones would lose the failures
logging.basicConfig(
    level=logging.INFO,
)

# seconds, the wait grows by this much with every attempt: 15 minutes, 30, 45
RETRY_STEP = 15 * 60
MAX_RETRY_DELAY = 2 * 60 * 60
# about 7 hours of waiting in all, the next run goes on from where this one stopped
ATTEMPTS = 8

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

from taskiq import TaskiqMessage, TaskiqResult

from core.broker import QUEUE_TIME_LABEL, TaskTelemetryMiddleware


def finish(
    queue_time: str | float,
) -> None:
    middleware = TaskTelemetryMiddleware()
    message = middleware.pre_execute(
        message=TaskiqMessage(
            task_id="1",
            task_name="traffic.tasks:import_receipts",
            labels={QUEUE_TIME_LABEL: queue_time},
            args=[],
            kwargs={},
        ),
    )
    middleware.post_execute(
        message=message,
        result=TaskiqResult(
            is_err=False,
            return_value=None,
            execution_time=0.1,
        ),
    )


def test_a_delayed_attempt_with_the_queue_time_as_a_string_finishes() -> None:
    finish(
        queue_time="1793542310.5",
    )


def test_a_first_attempt_finishes() -> None:
    finish(
        queue_time=1793542310.5,
    )

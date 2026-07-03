import logging
import os
import sys

from celery import Celery
from celery.signals import beat_init, celeryd_init

# Configure logging for Celery module
logger = logging.getLogger(__name__)

# Disable Celery startup logging during tests
if "test" in sys.argv:
    logger.setLevel(logging.CRITICAL)

# Set the default Django settings module for the 'celery' program.
# Use production settings by default in production, local otherwise
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "grey_lit_project.settings.local"),
)

# Ensure UTC timezone is set
os.environ.setdefault("TZ", "UTC")

app = Celery("grey_lit_project")

# celery-types (#208) ships PEP 561 stubs so pyright stops flagging
# @shared_task functions and their .delay()/.apply_async() calls. The stubs
# make Task & friends generic; this patch lets that subscripting work at
# runtime too. Type-only effect on the codebase (no Task[...] used at runtime).
from celery import Signature  # noqa: E402
from celery.app.task import Task  # noqa: E402
from celery.contrib.django.task import DjangoTask  # noqa: E402
from celery.result import AsyncResult  # noqa: E402

for _cls in (Celery, Task, DjangoTask, AsyncResult, Signature):
    setattr(  # noqa: B010
        _cls,
        "__class_getitem__",
        classmethod(lambda cls, *args, **kwargs: cls),
    )


# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Explicitly set timezone to UTC to prevent drift warnings
app.conf.timezone = "UTC"
app.conf.enable_utc = True

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


def ensure_tasks_registered():
    """
    Ensure all task modules are imported and registered with Celery.

    This function must be called after Django is fully configured.
    It's automatically called by the celeryd_init and beat_init signals,
    but can also be called manually for verification scripts.
    """
    logger.info("Registering Celery tasks...")

    # Import all task modules (individual imports silenced to reduce log noise)
    import apps.core.tasks.dynamic_scheduler  # noqa: F401
    import apps.core.tasks.metric_updates  # noqa: F401
    import apps.reporting.tasks  # noqa: F401
    import apps.results_manager.tasks.monitoring  # noqa: F401
    import apps.results_manager.tasks.orchestration  # noqa: F401
    import apps.results_manager.tasks.processing  # noqa: F401
    import apps.review_manager.tasks.cache  # noqa: F401
    import apps.review_manager.tasks.maintenance  # noqa: F401
    import apps.review_manager.tasks.monitoring  # noqa: F401
    import apps.review_results.tasks  # noqa: F401
    import apps.serp_execution.tasks.execution  # noqa: F401
    import apps.serp_execution.tasks.monitoring  # noqa: F401
    import apps.feedback.tasks  # noqa: F401
    import apps.serp_execution.tasks.simple_tasks  # noqa: F401

    logger.info("Celery task registration complete (14 modules)")


@app.task(bind=True)
def debug_task(self):
    """Debug task to test Celery configuration"""
    print(f"Request: {self.request!r}")


from celery.signals import task_failure  # noqa: E402


# Initialize Sentry for Celery workers
@celeryd_init.connect
def init_sentry_celery(**kwargs):
    """Initialize Sentry when Celery worker starts."""
    logger.info("init_sentry_celery signal handler called")

    # Register all tasks with Celery
    ensure_tasks_registered()

    logger.info("Loading environment config...")
    from apps.core.env_config import get_env, get_env_float

    sentry_dsn = get_env("SENTRY_DSN", default="")

    if sentry_dsn and not sentry_dsn.startswith(("http://", "https://")):
        logger.warning(
            "Sentry disabled for Celery: Invalid DSN format "
            "(must start with http:// or https://)"
        )
        sentry_dsn = ""

    logger.info(f"Sentry DSN configured: {bool(sentry_dsn)}")

    if sentry_dsn:
        logger.info("Initializing Sentry SDK...")
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        logging_integration = LoggingIntegration(
            level=logging.INFO, event_level=logging.ERROR
        )

        logger.info("Calling sentry_sdk.init()...")
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                DjangoIntegration(),
                CeleryIntegration(
                    monitor_beat_tasks=True,
                    propagate_traces=True,
                ),
                RedisIntegration(),
                logging_integration,
            ],
            traces_sample_rate=get_env_float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
            profiles_sample_rate=get_env_float(
                "SENTRY_PROFILES_SAMPLE_RATE", default=0.05
            ),
            environment=get_env("SENTRY_ENVIRONMENT", default="production"),
            release=get_env("SENTRY_RELEASE", default="1.0.0"),
        )
        logger.info("Sentry initialized successfully")
        logger.info("Sentry initialized for Celery worker")


# Initialize Sentry for Celery Beat
@beat_init.connect
def init_sentry_beat(**kwargs):
    """Initialize Sentry when Celery Beat starts."""
    # Register all tasks with Celery
    ensure_tasks_registered()

    from apps.core.env_config import get_env, get_env_float

    sentry_dsn = get_env("SENTRY_DSN", default="")

    if sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        logging_integration = LoggingIntegration(
            level=logging.INFO, event_level=logging.ERROR
        )

        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[
                DjangoIntegration(),
                CeleryIntegration(
                    monitor_beat_tasks=True,
                    propagate_traces=True,
                ),
                RedisIntegration(),
                logging_integration,
            ],
            traces_sample_rate=get_env_float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
            profiles_sample_rate=get_env_float(
                "SENTRY_PROFILES_SAMPLE_RATE", default=0.05
            ),
            environment=get_env("SENTRY_ENVIRONMENT", default="production"),
            release=get_env("SENTRY_RELEASE", default="1.0.0"),
        )
        logger.info("Sentry initialized for Celery Beat")


@task_failure.connect
def handle_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **kw,
):
    """Global error handler for all Celery task failures."""
    logger.error(
        f"Task {sender.name} [{task_id}] failed: {exception}\n"
        f"Args: {args}\nKwargs: {kwargs}"
    )

    # Send to Sentry if configured
    try:
        import sentry_sdk

        if sentry_sdk.is_initialized():
            with sentry_sdk.new_scope() as scope:
                scope.set_tag("task_name", sender.name)
                scope.set_tag("task_id", task_id)
                scope.set_context(
                    "task_details",
                    {
                        "args": args,
                        "kwargs": kwargs,
                    },
                )
                sentry_sdk.capture_exception(exception)
    except ImportError:
        pass  # Sentry not configured

    # For critical tasks, log to database
    critical_tasks = [
        "apps.serp_execution.tasks.perform_serp_query_task",
        "apps.serp_execution.tasks.initiate_search_session_execution_task",
        "apps.results_manager.tasks.process_search_results_task",
    ]

    if sender.name in critical_tasks:
        # Extract session_id from args/kwargs
        session_id = kwargs.get("session_id") or (args[0] if args else None)
        if session_id:
            from apps.review_manager.models import SessionActivity

            try:
                SessionActivity.objects.create(
                    session_id=session_id,
                    activity_type="error",
                    description=f"Task {sender.name} failed",
                    user=None,
                    metadata={
                        "task": sender.name,
                        "task_id": task_id,
                        "error": str(exception),
                        "error_type": type(exception).__name__,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to log task failure activity: {e}")


# Initialize Celery logging with structured logging
logger.info("Importing celery_logging...")
from apps.core.celery_logging import *  # noqa: E402, F401, F403 - Signal handlers

logger.info("celery_logging imported successfully")

# Configure Celery to propagate correlation IDs
app.conf.task_protocol = 2  # Use protocol 2 for header support
app.conf.task_track_started = True
app.conf.task_send_sent_event = True

# NOTE: Celery Beat Schedule is defined in grey_lit_project/settings/base.py
# as CELERY_BEAT_SCHEDULE and loaded via app.config_from_object() above.
# Do not redefine app.conf.beat_schedule here as it will override settings.

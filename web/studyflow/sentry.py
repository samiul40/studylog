import logging

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration


def init_sentry(dsn: str, environment: str, traces_sample_rate: float) -> None:
    """Send unhandled exceptions and logger.error+ calls to Sentry."""
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[
            DjangoIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        send_default_pii=True,
        traces_sample_rate=traces_sample_rate,
    )

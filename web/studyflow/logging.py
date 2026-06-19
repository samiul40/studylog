def get_logging_config(debug: bool, log_level: str, django_log_level: str) -> dict:
    """Container runtime (Docker) captures stdout/stderr, log to console only."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "{asctime} {levelname} {name} {message}",
                "style": "{",
            },
            "simple": {
                "format": "{levelname} {name} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "simple" if debug else "verbose",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": django_log_level,
                "propagate": False,
            },
        },
    }

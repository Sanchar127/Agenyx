import logging
import sys


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "service=agenyx-agent "
            "message=%(message)s"
        ),
        stream=sys.stdout,
        force=True,
    )


logger = logging.getLogger("agenyx")

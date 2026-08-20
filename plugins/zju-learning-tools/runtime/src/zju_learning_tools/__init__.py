"""ZJU Learning Tools local runtime."""

import logging
import warnings

# httpx's INFO log includes full URLs. CAS redirects can carry one-time tickets, so the runtime
# suppresses dependency request logging and emits only its own allowlisted, body-free diagnostics.
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("httpcore").setLevel(logging.CRITICAL)
warnings.filterwarnings(
    "ignore",
    message="Field 'lifespan' has an incomplete definition.*",
    module="pydantic_settings.sources.utils",
)

__version__ = "0.3.0"

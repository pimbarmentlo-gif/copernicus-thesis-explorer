"""Central application logging for the Copernicus Thesis Explorer.

Garrett asked for plain Python `logging` (NOT `print`, which does not surface as
real container logs) so we can see which functions run during startup and where
the time goes.  Import the shared ``logger`` from this module and add
``logger.debug(...)`` calls throughout the app::

    from app_logging import logger
    logger.debug("entering my_function")

Why this file is called ``app_logging.py`` and not ``logging.py``
-----------------------------------------------------------------
Streamlit runs the app with ``streamlit run dashboard/dashboard.py``, which puts
the ``dashboard/`` folder on ``sys.path``.  A module literally named
``logging.py`` sitting in that folder would *shadow* Python's standard-library
``logging`` module, breaking ``import logging`` everywhere in the app (including
inside this very file).  Naming it ``app_logging`` keeps Garrett's pattern --- a
small dedicated module exposing a ready-to-use ``logger`` --- without the
name-collision footgun.
"""

import logging
import sys

# The shared application logger.  Use this everywhere via `from app_logging import logger`.
logger = logging.getLogger("thesis_explorer")

# Configure once.  The module is imported a single time (cached in sys.modules),
# but the `if not logger.handlers` guard also protects against Streamlit's
# top-to-bottom re-execution ever adding duplicate handlers.
if not logger.handlers:
    logger.setLevel(logging.DEBUG)

    # Stream to stdout so messages land in the container / uvicorn logs alongside
    # the Streamlit output Garrett already sees.
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(_handler)

    # Don't also bubble up to the root logger (avoids duplicate lines if Streamlit
    # or uvicorn has configured the root handler).
    logger.propagate = False

    logger.debug("app_logging initialised (level=DEBUG, handler=stdout)")

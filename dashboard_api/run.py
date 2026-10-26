"""Standalone runner for the KYOKA 3.0 Dashboard API.

Usage:
    python -m dashboard_api.run
"""
import logging
import os
import sys
from aiohttp import web

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dashboard_api.config import DashboardConfig
from dashboard_api.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Kyoka.Dashboard")


def main() -> None:
    config = DashboardConfig.from_env()
    logger.info(f"Starting KYOKA 3.0 Dashboard API on {config.host}:{config.port}")
    app = create_app(config)
    web.run_app(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()

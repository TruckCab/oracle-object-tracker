import logging
import os
import sys

import click
from dotenv import load_dotenv

from . import __version__ as app_version

# Setup logging
logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger()

# Load our environment file if it is present
load_dotenv(dotenv_path=".env")


@click.command()
@click.option(
    "--version/--no-version",
    type=bool,
    default=False,
    show_default=False,
    required=True,
    help="Prints the Oracle Object Tracker version and exits."
)
@click.option(
    "--username",
    type=str,
    default=os.getenv("DATABASE_USERNAME"),
    show_default=True,
    required=True,
    help="The Oracle database username to connect with."
)
@click.option(
    "--password",
    type=str,
    default=os.getenv("DATABASE_PASSWORD"),
    show_default=False,
    required=True,
    help="The Oracle database password to connect with."
)
@click.option(
    "--hostname",
    type=str,
    default=os.getenv("DATABASE_HOSTNAME"),
    show_default=True,
    required=True,
    help="The Oracle database hostname to connect to."
)
@click.option(
    "--service-name",
    type=str,
    default=os.getenv("DATABASE_SERVICE_NAME"),
    show_default=True,
    required=True,
    help="The Oracle database service name to connect to."
)
@click.option(
    "--port",
    type=int,
    default=os.getenv("DATABASE_PORT"),
    show_default=True,
    required=True,
    help="The Oracle database port to connect to."
)
@click.option(
    "--log-level",
    type=str,
    default=os.getenv("LOGGING_LEVEL", "INFO"),
    show_default=True,
    required=True,
    help="The logging level to use for the application."
)
def main(version: bool,
         username: str,
         password: str,
         hostname: str,
         service_name: str,
         port: int,
         log_level: str
         ):
    if version:
        print(f"Oracle Database Tracker - version: {app_version}")
        return

    logger.setLevel(level=getattr(logging, log_level))

    logger.info(msg="Starting Oracle Object Tracker application.")


if __name__ == "__main__":
    main()

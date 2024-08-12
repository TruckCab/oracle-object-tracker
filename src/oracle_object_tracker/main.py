import logging
import os
import sys


import click
from dotenv import load_dotenv
from typing import List
from pathlib import Path
import oracledb

from . import __version__ as app_version

# Setup logging
logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger()

# Load our environment file if it is present
load_dotenv(dotenv_path=".env")


class OracleDatabaseTracker:
    def __init__(self,
                 username: str,
                 password: str,
                 hostname: str,
                 service_name: str,
                 port: int,
                 schema_names: List[str],
                 output_directory: str,
                 logger: logging.Logger
                 ):
        self._username = username
        self._password = password
        self._hostname = hostname
        self._service_name = service_name
        self._port = port

        self.con = self._connect_to_database()

        with self.con.cursor() as cursor:
            cursor.execute("SELECT * FROM all_tables")
            for row in cursor:
                print(row)

    def _connect_to_database(self):
        oracledb.init_oracle_client(lib_dir=os.getenv("ORACLE_HOME"))
        dsn = oracledb.makedsn(host=self._hostname,
                               port=self._port,
                               service_name=self._service_name
                               )
        con = oracledb.connect(user=self._username,
                               password=self._password,
                               dsn=dsn
                               )
        return con


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
    "--schema-name",
    type=str,
    default=[os.getenv("DATABASE_USERNAME")],
    show_default=True,
    required=True,
    multiple=True,
    help="The schema name to export objects for, may be specified more than once.  Defaults to the database username."
)
@click.option(
    "--output-directory",
    type=str,
    default=Path("output").as_posix(),
    show_default=True,
    required=True,
    help="The path to the output directory - may be relative or absolute."
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
         schema_name: List[str],
         output_directory: str,
         log_level: str,
         ):
    if version:
        print(f"Oracle Database Tracker - version: {app_version}")
        return

    logger.setLevel(level=getattr(logging, log_level))

    logger.info(msg=f"Starting Oracle Object Tracker application - version: {app_version}")
    arg_dict = locals()
    arg_dict.update({"password": "(redacted)"})
    logger.info(msg=f"Called with arguments: {arg_dict}")

    oracle_database_tracker = OracleDatabaseTracker(username=username,
                                                    password=password,
                                                    hostname=hostname,
                                                    service_name=service_name,
                                                    port=port,
                                                    schema_names=schema_name,
                                                    output_directory=output_directory,
                                                    logger=logger
                                                    )


if __name__ == "__main__":
    main()

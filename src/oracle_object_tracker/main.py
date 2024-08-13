import logging
import os
import sys
from contextlib import contextmanager
import shutil

import click
from dotenv import load_dotenv
from typing import List
from pathlib import Path
import oracledb
from codetiming import Timer
import sqlglot

from . import __version__ as app_version

# Constants
TIMER_TEXT = "{name}: Elapsed time: {:.4f} seconds"

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
                 schemas: List[str],
                 object_types: List[str],
                 output_directory: str,
                 overwrite: bool,
                 logger: logging.Logger
                 ):
        self._username = username
        self._password = password
        self._dsn = oracledb.makedsn(host=hostname,
                                     port=port,
                                     service_name=service_name
                                     )

        self.schemas = schemas
        self.object_types = object_types
        self.output_directory = output_directory
        self.overwrite = overwrite
        self.logger = logger

        oracledb.init_oracle_client(lib_dir=os.getenv("ORACLE_HOME"))

    @contextmanager
    def get_db_connection(self) -> oracledb.Connection:
        con = oracledb.connect(user=self._username,
                               password=self._password,
                               dsn=self._dsn
                               )
        try:
            yield con
        finally:
            con.close()

    def set_dbms_metadata_preferences(self,
                                      connection: oracledb.Connection
                                      ):
        with connection.cursor() as cursor:
            cursor.execute(statement=f"""
            BEGIN
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'CONSTRAINTS', value => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'REF_CONSTRAINTS', value => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'CONSTRAINT_USE_DEFAULT_INDEX', value => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'CONSTRAINTS_AS_ALTER', value => FALSE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'PRETTY', value => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'SQLTERMINATOR', value => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'SIZE_BYTE_KEYWORD', value => FALSE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'SEGMENT_ATTRIBUTES', value => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'STORAGE', value => FALSE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, name => 'TABLESPACE', value => TRUE);
            END;
            """)

    def get_object_ddl(self,
                       connection: oracledb.Connection,
                       schema: str,
                       object_type: str,
                       object_name: str
                       ):
        with connection.cursor() as cursor:
            sql = f"""SELECT dbms_metadata.get_ddl (
                                 object_type => :object_type
                               , name        => :object_name
                               , schema      => :schema
                                )
                        FROM dual
                   """
            cursor.execute(statement=sql,
                           object_type=object_type,
                           object_name=object_name,
                           schema=schema
                           )
            object_ddl = str(cursor.fetchone()[0]) + "\n"

        return object_ddl

    def get_objects(self,
                    connection: oracledb.Connection,
                    schema: str,
                    object_type: str
                    ):
        with connection.cursor() as cursor:
            sql = f"""SELECT object_name
                        FROM all_objects
                       WHERE owner = :schema
                         AND object_type = :object_type
                       ORDER BY object_name ASC
                  """
            cursor.execute(statement=sql,
                           schema=schema,
                           object_type=object_type
                           )
            object_list = [row[0] for row in cursor]

        return object_list

    def export_objects(self):
        with self.get_db_connection() as connection:
            self.set_dbms_metadata_preferences(connection=connection)

            with Timer(name=f"Exporting objects - for schemas: {self.schemas}",
                       text=TIMER_TEXT,
                       initial_text=True,
                       logger=self.logger.info
                       ):
                for schema in self.schemas:
                    with Timer(name=f"Exporting objects - for schema: {schema}",
                               text=TIMER_TEXT,
                               initial_text=True,
                               logger=self.logger.info
                               ):
                        schema_output_path_prefix = Path(f"{self.output_directory}/{schema}")
                        if schema_output_path_prefix.exists():
                            if self.overwrite:
                                shutil.rmtree(path=schema_output_path_prefix.as_posix())
                            else:
                                raise RuntimeError(f"Directory: {schema_output_path_prefix.as_posix()} exists, aborting.")

                        for object_type in self.object_types:
                            with Timer(name=f"Exporting object type: {object_type} - for schema: {schema}",
                                       text=TIMER_TEXT,
                                       initial_text=True,
                                       logger=self.logger.info
                                       ):
                                object_output_path_prefix = schema_output_path_prefix / object_type
                                if not object_output_path_prefix.exists():
                                    object_output_path_prefix.mkdir(parents=True)

                                object_list = self.get_objects(connection=connection,
                                                               schema=schema,
                                                               object_type=object_type
                                                               )
                                for object_name in object_list:
                                    with Timer(name=f"Exporting object: {object_type} - {schema}.{object_name}",
                                               text=TIMER_TEXT,
                                               initial_text=True,
                                               logger=self.logger.info
                                               ):
                                        object_ddl = self.get_object_ddl(connection=connection,
                                                                         schema=schema,
                                                                         object_type=object_type,
                                                                         object_name=object_name
                                                                         )
                                        object_output_path = object_output_path_prefix / f"{object_name}.sql"
                                        with object_output_path.open(mode="w") as f:
                                            f.write(object_ddl)


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
    "--schema",
    type=str,
    default=[os.getenv("DATABASE_USERNAME").upper()],
    show_default=True,
    required=True,
    multiple=True,
    help="The schema to export objects for, may be specified more than once.  Defaults to the database username."
)
@click.option(
    "--object-type",
    type=str,
    default=["TABLE", "VIEW"],
    show_default=True,
    required=True,
    multiple=True,
    help="The object types to export."
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
    "--overwrite",
    type=bool,
    default=False,
    show_default=True,
    required=True,
    help="Controls whether to overwrite any existing DDL export files in the output path."
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
         schema: List[str],
         object_type: List[str],
         output_directory: str,
         overwrite: bool,
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
                                                    schemas=schema,
                                                    object_types=object_type,
                                                    output_directory=output_directory,
                                                    overwrite=overwrite,
                                                    logger=logger
                                                    )

    oracle_database_tracker.export_objects()


if __name__ == "__main__":
    main()

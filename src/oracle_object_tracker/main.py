import logging
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List

import click
import git
import oracledb
from codetiming import Timer
from dotenv import load_dotenv
from git import Repo

from . import __version__ as app_version

# Constants
TIMER_TEXT = "{name}: Elapsed time: {:.4f} seconds"
OBJECT_TYPE_DBMS_METADATA_DICT = {
    "CLUSTER": {"short_name": "CLUSTER"},
    "DATABASE LINK": {"short_name": "DB_LINK"},
    "FUNCTION": {"short_name": "FUNCTION"},
    "INDEX": {"short_name": "INDEX"},
    "JAVA SOURCE": {"short_name": "JAVA_SOURCE"},
    "JOB": {"short_name": "PROCOBJ"},
    "MATERIALIZED VIEW": {"short_name": "MATERIALIZED_VIEW"},
    "MATERIALIZED VIEW LOG": {"short_name": "MATERIALIZED_VIEW_LOG"},
    "PACKAGE": {"short_name": "PACKAGE_SPEC"},
    "PACKAGE BODY": {"short_name": "PACKAGE_BODY"},
    "PROCEDURE": {"short_name": "PROCEDURE"},
    "SEQUENCE": {"short_name": "SEQUENCE"},
    "SYNONYM": {"short_name": "SYNONYM"},
    "TABLE": {"short_name": "TABLE"},
    "TRIGGER": {"short_name": "TRIGGER"},
    "TYPE": {"short_name": "TYPE_SPEC"},
    "TYPE BODY": {"short_name": "TYPE_BODY"},
    "VIEW": {"short_name": "VIEW"}
}

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
                 object_name_include_pattern: str,
                 object_name_exclude_pattern: str,
                 output_directory: str,
                 overwrite: bool,
                 git_repo: str,
                 git_branch: str,
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
        self.object_name_include_pattern = object_name_include_pattern
        self.object_name_exclude_pattern = object_name_exclude_pattern
        self.output_directory = output_directory
        self.overwrite = overwrite
        self.git_repo = git_repo
        self.git_branch = git_branch
        self.logger = logger

        try:
            oracledb.init_oracle_client()
        except Exception as e:
            oracledb.init_oracle_client(lib_dir=os.getenv("ORACLE_LIB_DIR", os.environ["ORACLE_HOME"] + "/lib"))

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
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'CONSTRAINTS', VALUE => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'REF_CONSTRAINTS', VALUE => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'CONSTRAINT_USE_DEFAULT_INDEX', VALUE => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'CONSTRAINTS_AS_ALTER', VALUE => FALSE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'PRETTY', VALUE => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'SQLTERMINATOR', VALUE => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'SIZE_BYTE_KEYWORD', VALUE => FALSE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'SEGMENT_ATTRIBUTES', VALUE => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'STORAGE', VALUE => FALSE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'TABLESPACE', VALUE => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'PARTITIONING', VALUE => TRUE);
               dbms_metadata.set_transform_param(transform_handle => dbms_metadata.session_transform, NAME => 'BODY', VALUE => FALSE);
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
        sql = f"""SELECT object_name
                    FROM all_objects
                   WHERE owner = :schema
                     AND object_type = :object_type
                     AND generated = 'N'
                     AND REGEXP_LIKE(object_name, :object_name_include_pattern)
              """

        additional_bind_vars = {}
        if self.object_name_exclude_pattern:
            sql += f"AND NOT REGEXP_LIKE(object_name, :object_name_exclude_pattern)\n"
            additional_bind_vars["object_name_exclude_pattern"] = self.object_name_exclude_pattern

        with connection.cursor() as cursor:
            cursor.execute(statement=sql,
                           schema=schema,
                           object_type=object_type,
                           object_name_include_pattern=self.object_name_include_pattern,
                           **additional_bind_vars
                           )
            object_list = [row[0] for row in cursor]

        return object_list

    def export_objects(self):
        with self.get_db_connection() as connection:
            self.set_dbms_metadata_preferences(connection=connection)

            output_path = Path(self.output_directory)
            if output_path.exists():
                if self.overwrite:
                    shutil.rmtree(path=output_path.as_posix())
                    output_path.mkdir(parents=True)
                else:
                    raise RuntimeError(
                        f"Directory: {output_path.as_posix()} exists, aborting.")

            repo = None
            if self.git_repo and self.git_branch:
                with Timer(name=f"Cloning git repository: {self.git_repo}",
                           text=TIMER_TEXT,
                           initial_text=True,
                           logger=self.logger.info
                           ):
                    repo = Repo.clone_from(url=self.git_repo, to_path=output_path)
                try:
                    repo.git.checkout(self.git_branch)
                except git.GitCommandError:
                    repo.git.checkout(b=self.git_branch)

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

                        for object_type in self.object_types:
                            with Timer(name=f"Exporting object type: {object_type} - for schema: {schema}",
                                       text=TIMER_TEXT,
                                       initial_text=True,
                                       logger=self.logger.info
                                       ):
                                object_type_short_name = OBJECT_TYPE_DBMS_METADATA_DICT.get(object_type).get("short_name")
                                object_output_path_prefix = schema_output_path_prefix / object_type_short_name
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
                                                                         object_type=object_type_short_name,
                                                                         object_name=object_name
                                                                         )
                                        object_output_path = object_output_path_prefix / f"{object_name}.sql"
                                        with object_output_path.open(mode="w") as f:
                                            f.write(object_ddl)

            if repo:
                commit_message = f"Oracle Object Tracker - DDL export - {datetime.now()}."
                with Timer(name=(f"Pushing changes to git repository: {self.git_repo} - branch: {self.git_branch}"
                                 f"\n- with commit message: '{commit_message}'"
                                 ),
                           text=TIMER_TEXT,
                           initial_text=True,
                           logger=self.logger.info
                           ):
                    repo.git.add(all=True)
                    repo.index.commit(message=f"Oracle Object Tracker - DDL export - {datetime.now()}.")
                    origin = repo.remote(name="origin")
                    origin.push(refspec=self.git_branch)


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
    show_default=False,
    required=True,
    help="The Oracle database username to connect with.  Defaults to environment variable DATABASE_USERNAME if set."
)
@click.option(
    "--password",
    type=str,
    default=os.getenv("DATABASE_PASSWORD"),
    show_default=False,
    required=True,
    help="The Oracle database password to connect with.  Defaults to environment variable DATABASE_PASSWORD if set."
)
@click.option(
    "--hostname",
    type=str,
    default=os.getenv("DATABASE_HOSTNAME"),
    show_default=False,
    required=True,
    help="The Oracle database hostname to connect to.  Defaults to environment variable DATABASE_HOSTNAME if set."
)
@click.option(
    "--service-name",
    type=str,
    default=os.getenv("DATABASE_SERVICE_NAME"),
    show_default=False,
    required=True,
    help="The Oracle database service name to connect to.  Defaults to environment variable DATABASE_SERVICE_NAME if set."
)
@click.option(
    "--port",
    type=int,
    default=os.getenv("DATABASE_PORT", 1521),
    show_default=True,
    required=True,
    help="The Oracle database port to connect to.  Defaults to environment variable DATABASE_PORT if set, or 1521 if not set."
)
@click.option(
    "--schema",
    type=str,
    default=[os.getenv("DATABASE_USERNAME", "").upper()],
    show_default=False,
    required=True,
    multiple=True,
    help="The schema to export objects for, may be specified more than once.  Defaults to the database username."
)
@click.option(
    "--object-type",
    type=str,
    default=[key for key in OBJECT_TYPE_DBMS_METADATA_DICT.keys()],
    show_default=True,
    required=True,
    multiple=True,
    help="The object types to export."
)
@click.option(
    "--object-name-include-pattern",
    type=str,
    default=".*",
    show_default=True,
    required=True,
    help="The regexp pattern to use to filter object names to include in the export."
)
@click.option(
    "--object-name-exclude-pattern",
    type=str,
    default=None,
    required=False,
    help="The regexp pattern to use to filter object names to exclude in the export."
)
@click.option(
    "--output-directory",
    type=str,
    default=(Path(tempfile.gettempdir()) / "output").as_posix(),
    show_default=False,
    required=True,
    help="The path to the output directory - may be relative or absolute."
)
@click.option(
    "--overwrite/--no-overwrite",
    type=bool,
    default=False,
    show_default=True,
    required=True,
    help="Controls whether to overwrite any existing DDL export files in the output path."
)
@click.option(
    "--git-repo",
    type=str,
    required=False,
    help=("Allows you to specify a git repository to push the output files to.  The repository must be accessible via SSH.\n"
          "Example: git@github.com:some-org/some-repo.git\n"
          "See: https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account "
          "for more information on setting up SSH keys for GitHub."
          )
)
@click.option(
    "--git-branch",
    type=str,
    default="main",
    show_default=True,
    required=False,
    help="Specify the git branch to push to - if the --git-repo arg is used."
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
         object_name_include_pattern: str,
         object_name_exclude_pattern: str,
         output_directory: str,
         overwrite: bool,
         git_repo: str,
         git_branch: str,
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
                                                    object_name_include_pattern=object_name_include_pattern,
                                                    object_name_exclude_pattern=object_name_exclude_pattern,
                                                    output_directory=output_directory,
                                                    overwrite=overwrite,
                                                    git_repo=git_repo,
                                                    git_branch=git_branch,
                                                    logger=logger
                                                    )

    oracle_database_tracker.export_objects()


if __name__ == "__main__":
    main()

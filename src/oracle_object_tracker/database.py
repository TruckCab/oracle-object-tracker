import os
from config import database_username, database_password, database_hostname, database_port, database_service_name
import oracledb
import sqlalchemy
from sqlalchemy.orm import sessionmaker


def get_database_engine():
    oracle_connection_string = f"oracle+oracledb://{database_username}:{database_password}@{database_hostname}:{database_port}?service_name={database_service_name}"

    engine = sqlalchemy.create_engine(url=oracle_connection_string,
                                      arraysize=1000,
                                      thick_mode=True
                                      )

    return engine

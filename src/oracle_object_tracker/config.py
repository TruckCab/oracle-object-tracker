from dotenv import load_dotenv
import os

# Constants
DEFAULT_DATABASE_PORT = 1521


load_dotenv()  # take environment variables from .env.

database_username = os.environ["DATABASE_USERNAME"]
database_password = os.environ["DATABASE_PASSWORD"]
database_hostname = os.environ["DATABASE_HOSTNAME"]
database_service_name = os.environ["DATABASE_SERVICE_NAME"]
database_port = os.getenv("DATABASE_PORT", DEFAULT_DATABASE_PORT)

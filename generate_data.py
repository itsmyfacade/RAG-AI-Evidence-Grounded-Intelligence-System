"""Generate the deterministic local operational database."""

from src.dataset import generate_database, validate_database
from src.settings import get_settings


if __name__ == "__main__":
    configuration = get_settings()
    print(generate_database(configuration.database_path))
    print(validate_database(configuration.database_path))

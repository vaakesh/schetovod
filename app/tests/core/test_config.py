import pytest
from pydantic import ValidationError

from core.config import Settings


@pytest.fixture
def postgres_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_password",
        "POSTGRES_DB": "gastronom",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "JWT_SECRET": "test_jwt_secret_for_settings_1234567890",
    }
    for name, value in values.items():
        monkeypatch.setenv(
            name=name,
            value=value,
        )


@pytest.mark.usefixtures(
    "postgres_environment",
)
class TestSettings:
    @pytest.mark.parametrize(
        argnames="database",
        argvalues=["postgres", "template0", "template1"],
    )
    def test_rejects_system_database_for_meat(self, database: str) -> None:
        with pytest.raises(
            expected_exception=ValidationError,
            match="POSTGRES_MEAT_DB не может указывать на служебную базу PostgreSQL",
        ):
            Settings(
                postgres_meat_db=database,
            )

    @pytest.mark.parametrize(
        argnames="database",
        argvalues=["", "meat\0store", "m" * 64, "м" * 32],
    )
    def test_rejects_invalid_meat_database_name(self, database: str) -> None:
        with pytest.raises(
            expected_exception=ValidationError,
            match="Некорректное имя POSTGRES_MEAT_DB",
        ):
            Settings(
                postgres_meat_db=database,
            )

    def test_rejects_primary_database_for_meat(self) -> None:
        with pytest.raises(
            expected_exception=ValidationError,
            match="POSTGRES_DB и POSTGRES_MEAT_DB должны указывать на разные базы данных",
        ):
            Settings(
                postgres_meat_db="gastronom",
            )

    def test_rejects_primary_database_name_with_overlong_meat_name_prefix(self) -> None:
        database = "м" * 31 + "m"

        with pytest.raises(
            expected_exception=ValidationError,
            match="Некорректное имя POSTGRES_DB",
        ):
            Settings(
                postgres_db=database + "different",
                postgres_meat_db=database,
            )

    def test_invalid_database_error_hides_settings_secrets(self) -> None:
        postgres_password = "settings-test-postgres-password"
        jwt_secret_suffix = "12345678901234567890"
        jwt_secret = f"settings-test-jwt-secret-{jwt_secret_suffix}"

        with pytest.raises(
            expected_exception=ValidationError,
            match="POSTGRES_MEAT_DB не может указывать на служебную базу PostgreSQL",
        ) as error:
            Settings(
                postgres_password=postgres_password,
                postgres_meat_db="template1",
                jwt_secret=jwt_secret,
            )

        message = str(
            error.value,
        )
        assert jwt_secret_suffix not in message
        assert postgres_password not in message
        assert "input_value=" not in message

    @pytest.mark.parametrize(
        argnames="database",
        argvalues=[
            'Мясо "на углу"',
            "Template1",
            "dbname=gastronom",
            "meat\n",
            "м" * 31 + "m",
        ],
    )
    def test_preserves_valid_custom_meat_database_name(self, database: str) -> None:
        settings = Settings(
            postgres_meat_db=database,
        )

        assert settings.meat_database_url.database == database

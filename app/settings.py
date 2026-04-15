from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ECUFlash API"
    app_version: str = "1.0.0"
    app_env: str = "prod"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "ecuflash"
    mysql_charset: str = "utf8mb4"

    auth_password_salt: str = "ecuflash_auth_salt"
    allow_passwordless_register: bool = False
    registration_requires_approval: bool = True
    admin_phone: str = "admin"
    admin_name: str = "系统管理员"
    admin_password: str = "admin1234"

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "ecuflash-wiring"
    minio_secure: bool = False
    minio_public_base_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@"
            f"{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset={self.mysql_charset}"
        )


settings = Settings()

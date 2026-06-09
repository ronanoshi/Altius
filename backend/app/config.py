from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    portal_url: str = "https://fo1.altius.finance"
    portal_username: str = ""
    portal_password: str = ""

    data_dir: str = "./data"
    database_url: str = "sqlite:///./data/altius.db"


settings = Settings()

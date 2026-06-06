from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PHOENIX_")

    app_name: str = "Phoenix-Light"
    api_v1_prefix: str = "/api/v1"

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_topic_telemetry: str = "phoenix/cabinets/+/telemetry"
    mqtt_topic_status: str = "phoenix/cabinets/+/status"
    mqtt_topic_alarms: str = "phoenix/alarms"

    alarm_zero_current_threshold_a: float = 0.05
    alarm_overvoltage_threshold_v: float = 253.0
    alarm_undervoltage_threshold_v: float = 207.0

    dimming_interval_s: int = 60
    communication_loss_timeout_s: int = 300

    cors_origins: list[str] = ["*"]

    # --- Identity / access control ---
    database_url: str = "sqlite:///./phoenix.db"
    jwt_secret: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 480

    # Progression: if enabled, users auto-promote one step when eligible,
    # but never above auto_promote_max_rank. Disabled by default so promotions
    # are an explicit admin action.
    auto_promote_enabled: bool = False
    auto_promote_max_rank: str = "tecnico"


settings = Settings()

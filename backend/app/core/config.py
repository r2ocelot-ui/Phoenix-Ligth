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
    # Auto-logout the web panel after this many minutes with no user activity.
    session_idle_minutes: int = 10

    # Brute-force guard: lock an account after this many consecutive failed
    # login/unlock attempts, for this many minutes (the lockout auto-clears).
    auth_max_failed_attempts: int = 5
    auth_lockout_minutes: int = 5

    # Network-level guard (fail2ban-style). An IP is auto-banned after this many
    # failed logins inside the window, for this many minutes.
    ip_ban_failed_threshold: int = 10
    ip_ban_window_minutes: int = 10
    ip_ban_duration_minutes: int = 30

    # Siege / lockdown mode — when on, only whitelisted IPs may connect.
    # Toggled from the panel by an Owner. Default off in env; runtime state
    # lives in the IpBan table via a sentinel row, see services/ip_guard.
    siege_mode_default: bool = False

    # Device-id cookie used by the "known devices" tracker. The cookie value is
    # opaque (a UUID); identity is validated against the user_devices table.
    device_cookie_name: str = "phoenix_device"
    device_cookie_max_age_days: int = 365

    # Hardware binding: when ON, telemetry without device_serial (or with a
    # wrong one) is rejected. Off by default so the demo loop still works;
    # turn on once every cabinet has a registered controller.
    require_device_serial: bool = False

    # Progression: if enabled, users auto-promote one step when eligible,
    # but never above auto_promote_max_rank. Disabled by default so promotions
    # are an explicit admin action.
    auto_promote_enabled: bool = False
    auto_promote_max_rank: str = "tecnico"

    # Demo mode injects synthetic telemetry so the web panel shows live data
    # without a broker. Disable in production.
    demo_mode: bool = True
    demo_interval_s: int = 3
    # Demo-only owner account, seeded on startup so you can log in immediately.
    # Disable by setting PHOENIX_DEMO_MODE=false in production.
    demo_admin_username: str = "admin"
    demo_admin_password: str = "phoenix123"


settings = Settings()

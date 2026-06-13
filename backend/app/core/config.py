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
    alarm_overcurrent_threshold_a: float = 30.0
    alarm_cabinet_temp_c: float = 55.0  # umbral de "exceso de temperatura"
    # Detección por desviación de consumo (matriz §6.6).
    # Si lo medido es < load_drop_ratio × esperado → CIRCUIT_LOAD_DROP.
    # Si > overload_ratio × esperado → CIRCUIT_OVERLOAD.
    # Si el cuadro está OFF y se mide más de stuck_min_w → CONTACTOR_STUCK.
    alarm_load_drop_ratio: float = 0.5     # cae a la mitad o menos
    alarm_overload_ratio: float = 1.30     # supera el 130 % del nominal
    alarm_contactor_stuck_min_w: float = 10.0

    dimming_interval_s: int = 60
    communication_loss_timeout_s: int = 300

    cors_origins: list[str] = ["*"]

    # --- Identity / access control ---
    database_url: str = "sqlite:///./phoenix.db"
    jwt_secret: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 480
    # Auto-logout the web panel after this many minutes with no user activity.
    session_idle_minutes: int = 10

    # Interruptor maestro del anti-fuerza-bruta (bloqueo de cuenta + auto-ban
    # por IP). Se puede apagar para pruebas con PHOENIX_LOCKOUT_ENABLED=false.
    # ⚠️ TEMPORALMENTE EN False PARA PRUEBAS — reactivar (True) antes de producción.
    lockout_enabled: bool = False

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
    demo_admin_username: str = "phoenix"
    demo_admin_password: str = "phoenix123"

    # Dimming consciente del coste eléctrico (tarifa por tramos). Off por
    # defecto: es una política opcional. ``tariff_floor_level`` es el mínimo
    # de seguridad vial: nunca se baja de ahí aunque la luz esté cara. Los
    # tramos y topes viven en services/tariff.py.
    tariff_enabled: bool = False
    tariff_floor_level: int = 40
    # Zona horaria del despliegue para los tramos de tarifa. Los periodos
    # punta/valle son en hora CIVIL local, no en la del servidor (que suele
    # ir en UTC). Sin esto, en un server UTC los tramos salían 2 h corridos.
    tariff_timezone: str = "Europe/Madrid"
    # Zona horaria de DISPLAY (reloj y tiempos del panel). "auto" la deduce de
    # la ubicación de los cuadros (Canarias vs península). Distinta de la de
    # tarifa: el reloj es hora local, la tarifa es peninsular por ley.
    display_timezone: str = "auto"
    # Topes de dimming por periodo (consciente del coste), configurables para
    # encajar el contrato real. Los TRAMOS horarios siguen en services/tariff.py
    # (pendiente: hacerlos configurables por proyecto).
    tariff_cap_punta: int = 75   # P1
    tariff_cap_llano: int = 90   # P2
    tariff_cap_valle: int = 100  # P3

    # Licenciamiento anti-copia (on-premise), Ed25519. La clave PRIVADA la
    # guardamos nosotros y firma licencias con tools/make_license.py; el
    # cliente solo lleva la PÚBLICA, así no se puede falsificar aunque tenga
    # el binario. Off por defecto: no bloquea nada hasta activarlo.
    license_required: bool = False
    license_public_key: str = ""   # Ed25519 pública (base64 raw, 32 bytes)
    license_key: str = ""          # la licencia firmada del cliente


settings = Settings()

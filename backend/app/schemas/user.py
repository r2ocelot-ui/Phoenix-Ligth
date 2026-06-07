from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    email: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    rank: str
    activity_points: int
    is_active: bool
    created_at: datetime


class UserDetail(UserRead):
    permissions: list[str]
    rank_level: int
    progression: dict
    has_pin: bool = False
    has_pattern: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rank: str


class UserCreateAdmin(BaseModel):
    """Admin issues the whole credential set at creation time. PIN and pattern
    are optional here so the admin can leave them blank and let the user
    define them in the first login if preferred."""
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    email: str | None = None
    rank: str = "visualizador"
    pin: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    pattern: str | None = Field(default=None, pattern=r"^[0-8]{4,9}$")


class PasswordSet(BaseModel):
    """Self-service password change: requires the current password. This is the
    anti-keylogger guardrail — even if every keystroke is captured, rotating a
    credential still needs the *current* one as proof of presence."""
    current_password: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)


class PasswordReset(BaseModel):
    """Admin-driven password reset — no ``current_password`` because the admin
    is acting on behalf of the user (e.g. forgotten password)."""
    password: str = Field(..., min_length=6)


class PinSet(BaseModel):
    """Self-service PIN change: requires the current PIN if one is already set."""
    pin: str = Field(..., pattern=r"^\d{4,8}$")
    current_pin: str | None = Field(default=None, pattern=r"^\d{4,8}$")


class PatternSet(BaseModel):
    """Self-service pattern change: requires the current pattern if one is set."""
    pattern: str = Field(..., pattern=r"^[0-8]{4,9}$")
    current_pattern: str | None = Field(default=None, pattern=r"^[0-8]{4,9}$")


class Unlock(BaseModel):
    """Unlock the locked session with whichever credential the user set."""
    pin: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    pattern: str | None = Field(default=None, pattern=r"^[0-8]{4,9}$")


# --- Multi-step login ------------------------------------------------------
class LoginStep1Result(BaseModel):
    """Outcome of step 1. If ``access_token`` is present the login is finished
    (account had no pattern). Otherwise the caller must complete step 2 with
    the ``challenge_token`` and the pattern."""
    step: int
    access_token: str | None = None
    challenge_token: str | None = None
    token_type: str = "bearer"
    rank: str
    expires_in: int | None = None


class LoginStep2(BaseModel):
    challenge_token: str
    pattern: str = Field(..., pattern=r"^[0-8]{4,9}$")


class RankChange(BaseModel):
    rank: str


class PermissionOverride(BaseModel):
    extra_permissions: list[str] = []
    denied_permissions: list[str] = []


class ActiveToggle(BaseModel):
    is_active: bool

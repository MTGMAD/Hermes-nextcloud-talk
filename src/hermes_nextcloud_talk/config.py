"""Safe configuration for a single-profile Nextcloud Talk bot instance."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


class TalkSettings(BaseModel):
    """Validated non-secret and secret settings for one Talk bot endpoint."""

    base_url: str
    bot_secret: str = Field(min_length=40, max_length=128)
    profile: str = Field(min_length=1)
    allowed_users: list[str] = Field(default_factory=list)
    allowed_rooms: list[str] = Field(default_factory=list)
    allow_all_users: bool = False
    development_mode: bool = False
    require_mention: bool = True
    mention_patterns: list[str] = Field(default_factory=list)

    @field_validator("base_url")
    @classmethod
    def require_https_origin(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be a canonical HTTPS origin")
        return f"https://{parsed.netloc}"

    @field_validator("profile")
    @classmethod
    def normalize_profile(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("profile cannot be blank")
        return normalized

    @field_validator("allowed_users", "allowed_rooms")
    @classmethod
    def normalize_allowlist(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("allowlist identifiers cannot be empty")
        return normalized

    @model_validator(mode="after")
    def require_safe_authorization_policy(self) -> TalkSettings:
        if self.allow_all_users and not self.development_mode:
            raise ValueError("allow_all_users requires development_mode")
        if not self.allow_all_users and not (self.allowed_users or self.allowed_rooms):
            raise ValueError("at least one allowlist must be configured")
        return self

from pydantic import BaseModel, Field


class SettingIn(BaseModel):
    key: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.\-]+$")
    value: str = Field(max_length=10000)
    is_secret: bool = False


class SettingOut(BaseModel):
    key: str
    value: str | None  # None для секретів
    is_secret: bool

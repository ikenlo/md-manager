from datetime import datetime

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    # не EmailStr: він відкидає службові домени на кшталт .local
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    uuid: str
    email: str
    display_name: str
    role: str


class LoginOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut


class RefreshOut(BaseModel):
    token: str = Field(description="Новий токен; попередній більше не діє")
    expires_at: datetime = Field(description="Коли завершиться нова сесія (UTC)")

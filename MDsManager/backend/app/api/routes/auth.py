from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_token
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginIn, LoginOut, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(u: User) -> UserOut:
    return UserOut(uuid=u.uuid, email=u.email, display_name=u.display_name, role=u.role)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    user = auth_service.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Невірний email або пароль")
    token, sess = auth_service.create_session(
        db,
        user,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    return LoginOut(token=token, expires_at=sess.expires_at, user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.post("/logout", status_code=204)
def logout(token: str = Depends(get_token), db: Session = Depends(get_db)) -> None:
    auth_service.revoke_session(db, token)

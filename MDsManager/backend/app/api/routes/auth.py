from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_token
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginIn, LoginOut, RefreshOut, UserOut
from app.services import auth as auth_service
from app.services.net import client_ip
from app.services.rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(u: User) -> UserOut:
    return UserOut(uuid=u.uuid, email=u.email, display_name=u.display_name, role=u.role)


@router.post("/login", response_model=LoginOut)
@limiter.limit(lambda: get_settings().login_rate_limit)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    user = auth_service.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Невірний email або пароль")
    token, sess = auth_service.create_session(
        db,
        user,
        client_ip(request),
        request.headers.get("user-agent"),
    )
    return LoginOut(token=token, expires_at=sess.expires_at, user=user_out(user))


@router.post(
    "/refresh",
    response_model=RefreshOut,
    summary="Оновити токен сесії",
    description=(
        "Видає новий токен із терміном дії SESSION_TTL_DAYS (типово 7 днів) від цього моменту. "
        "Попередній токен одразу перестає діяти. Протухлий або невідомий токен → 401."
    ),
    responses={401: {"description": "Сесія недійсна або завершилась"}},
)
def refresh(
    request: Request, token: str = Depends(get_token), db: Session = Depends(get_db)
) -> RefreshOut:
    rotated = auth_service.rotate_session(
        db, token, client_ip(request), request.headers.get("user-agent")
    )
    if rotated is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сесія недійсна або завершилась")
    new_token, sess = rotated
    return RefreshOut(token=new_token, expires_at=sess.expires_at)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.post("/logout", status_code=204)
def logout(token: str = Depends(get_token), db: Session = Depends(get_db)) -> None:
    auth_service.revoke_session(db, token)

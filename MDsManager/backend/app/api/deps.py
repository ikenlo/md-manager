from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import user_by_token

bearer = HTTPBearer(auto_error=False)


def get_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Потрібна авторизація")
    return creds.credentials


def current_user(token: str = Depends(get_token), db: Session = Depends(get_db)) -> User:
    user = user_by_token(db, token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сесія недійсна або завершилась")
    return user

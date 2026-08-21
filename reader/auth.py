import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

from database import create_user, get_user_by_username

# Конфигурация безопасности (с запасным ключом на случай отсутствия в .env)
SECRET_KEY = os.getenv("SECRET_KEY", "custom-super-secure-jwt-secret-key-change-it")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 90

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- Pydantic Схемы ---

class UserAuthSchema(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


# --- Вспомогательные функции хеширования ---

def get_password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return f"{salt}${key}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, key = hashed_password.split('$')
        new_key = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return secrets.compare_digest(key, new_key)
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# --- Dependency для защиты эндпоинтов ---

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не авторизован или токен недействителен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_username(username)
    if user is None:
        raise credentials_exception

    return user["username"]


# --- Эндпоинты Регистрации и Логина ---

@router.post("/register", response_model=TokenResponse)
def register(data: UserAuthSchema):
    username = data.username.strip().lower()
    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="Имя пользователя должно быть от 3 символов")
    
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен содержать минимум 4 символа")

    if get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")

    hashed_pw = get_password_hash(data.password)
    create_user(username, hashed_pw)

    token = create_access_token(data={"sub": username})
    return {"access_token": token, "token_type": "bearer", "username": username}


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    username = form_data.username.strip().lower()
    user = get_user_by_username(username)
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверное имя пользователя или пароль"
        )

    token = create_access_token(data={"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer", "username": user["username"]}

from database import create_user, get_user_by_username, update_user_api_key, get_user_api_key

class ApiKeySchema(BaseModel):
    api_key: str

# Только запись — бэкенд никогда не отдает ключ обратно в браузер
@router.post("/api-key")
def set_key(data: ApiKeySchema, current_user: str = Depends(get_current_user)):
    clean_key = data.api_key.strip()
    if not clean_key:
        raise HTTPException(status_code=400, detail="Ключ не может быть пустым")
    
    update_user_api_key(current_user, clean_key)
    return {"status": "ok", "message": "API ключ успешно сохранен"}
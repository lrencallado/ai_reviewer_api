from openai import OpenAI
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from sqlmodel import select
from app.models import User
from app.database import get_session
import jwt
from jwt.exceptions import InvalidTokenError
from app.config import SETTINGS

client = OpenAI(api_key=SETTINGS.openai_api_key)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/token",
    scopes={"user": "Regular user access", "admin": "Admin privileges"}
)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# def authenticate_user(fake_db, username: str, password: str):
#     user = get_user(fake_db, username)
#     if not user:
#         return False
#     if not verify_password(password, user.hashed_password):
#         return False
#     return user

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    if not isinstance(data, dict):
        raise TypeError("Expected dict for data, got: {}".format(type(data).__name__))
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=SETTINGS.access_token_expires_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SETTINGS.secret_key, algorithm=SETTINGS.algorithm)

def get_openai_client():
    return client

async def get_current_user(
    security_scopes: SecurityScopes,
    token: str = Depends(oauth2_scheme),
    session = Depends(get_session)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SETTINGS.secret_key, algorithms=[SETTINGS.algorithm])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    
    result = await session.exec(select(User).where(User.username == username))
    user = result.first()
    if user is None:
        raise credentials_exception
    
    for scope in security_scopes.scopes:
        if scope not in user.scopes:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        
    return user

async def seed_admin(session = Depends(get_session)):
    result = await session.exec(select(User).where(User.username == "admin"))
    if result.first():
        return {"message": "Admin user already exists"}

    admin = User(
        username="admin",
        full_name="Admin User",
        hashed_password=get_password_hash("admin123"),
        scopes=["admin"]
    )
    session.add(admin)
    await session.commit()
    return {"message": "Admin user created"}
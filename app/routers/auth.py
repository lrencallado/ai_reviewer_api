from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select
from app.database import get_session
from app.dependencies import verify_password, create_access_token
from app.models import User, Token
from typing import Annotated
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import timedelta
from app.config import settings

router = APIRouter(tags=["Auth"])

@router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)]
) -> Token:
    result = await session.exec(select(User).where(User.username == form_data.username))
    user = result.first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.access_token_expires_minutes)
    access_token = create_access_token(
        data={"sub": user.username, "scopes": user.scopes},
        expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")
from fastapi import APIRouter, Depends, HTTPException, Security
from pydantic import BaseModel
from sqlmodel import select
from app.models import User
from app.database import get_session
from app.dependencies import get_password_hash, get_current_user
from typing import List, Optional, Annotated, Union

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])

class UserCreate(BaseModel):
    username: str
    full_name: str
    email: str
    password: str
    scopes: List[str]

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None
    scopes: Optional[List[str]] = None

@router.get("/", response_model=List[User])
async def list_users(
    current_user: Annotated[User, Security(get_current_user, scopes=["admin"])],
    session: Annotated = Depends(get_session)
):
    if "admin" not in current_user.scopes:
        raise HTTPException(status_code=403, detail="Not authorized")
    result = await session.exec(select(User))
    return result.all()

@router.post("/create")
async def create_user(
    user: UserCreate,
    current_user: Annotated[User, Security(get_current_user, scopes=["admin"])],
    session: Annotated = Depends(get_session)
):
    if "admin" not in current_user.scopes:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await session.exec(
        select(User).where(
            (User.username == user.username) | (User.email == user.email)
        )
    )
    existing_user = result.first()
    if existing_user:
        if existing_user.username == user.username:
            raise HTTPException(status_code=400, detail="Username already exists")
        if existing_user.email == user.email:
            raise HTTPException(status_code=400, detail="Email already exists")

    new_user = User(
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        scopes=user.scopes
    )
    session.add(new_user)
    await session.commit()
    return {"message": f"Created user {user.username}"}

@router.put("/{username}")
async def update_user(
    username: str,
    user_update: UserUpdate,
    current_user: Annotated[User, Security(get_current_user, scopes=["admin"])],
    session: Annotated = Depends(get_session)
):
    if "admin" not in current_user.scopes:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await session.exec(select(User).where(User.username == username))
    user = result.first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_update.full_name:
        user.full_name = user_update.full_name
    if user_update.password:
        user.hashed_password = get_password_hash(user_update.password)
    if user_update.scopes:
        user.scopes = user_update.scopes

    session.add(user)
    await session.commit()
    return {"message": f"Updated user {username}"}

@router.delete("/{username}")
async def delete_user(
    username: str,
    current_user: Annotated[User, Security(get_current_user, scopes=["admin"])],
    session = Depends(get_session)
):
    if "admin" not in current_user.scopes:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await session.exec(select(User).where(User.username == username))
    user = result.first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
    return {"message": f"Deleted user {username}"}

@router.get("/{username}", response_model=User)
async def get_user(
    username: str,
    current_user: Annotated[User, Security(get_current_user, scopes=["admin"])],
    session: Annotated = Depends(get_session)
):
    if "admin" not in current_user.scopes:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await session.exec(select(User).where(User.username == username))
    user = result.first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
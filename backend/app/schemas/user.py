from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str
    organization_id: Optional[int] = None
    create_organization: Optional[bool] = False
    organization_name: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    username: Optional[str] = None  # For compatibility with tests
    password: Optional[str] = None
    organization_id: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserInDBBase(UserBase):
    id: Optional[int] = None
    organization_id: Optional[int] = None
    role: Optional[str] = None
    is_superuser: Optional[bool] = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class User(UserInDBBase):
    pass


class UserWithOrganization(UserInDBBase):
    organization_name: Optional[str] = None


class UserInDB(UserInDBBase):
    hashed_password: str


# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str


 
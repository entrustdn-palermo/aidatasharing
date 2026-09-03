from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ConfigurationBase(BaseModel):
    key: str
    value: Optional[str] = None
    description: Optional[str] = None


class ConfigurationCreate(ConfigurationBase):
    pass


class ConfigurationUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None


class ConfigurationInDBBase(ConfigurationBase):
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Configuration(ConfigurationInDBBase):
    pass

 
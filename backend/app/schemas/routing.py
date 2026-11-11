import uuid

from pydantic import BaseModel, Field


class ManualAssignRequest(BaseModel):
    agent_profile_id: uuid.UUID


class TerritoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    is_active: bool = True


class TerritoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    aliases: list[str] | None = None
    is_active: bool | None = None


class TerritoryMappingCreate(BaseModel):
    territory_id: uuid.UUID
    agent_profile_id: uuid.UUID
    priority: int = Field(default=100, ge=1, le=10000)


class TerritoryMappingUpdate(BaseModel):
    priority: int = Field(ge=1, le=10000)


class TerritoryOut(BaseModel):
    id: uuid.UUID
    name: str
    aliases: list[str]
    is_active: bool

    model_config = {"from_attributes": True}


class TerritoryMappingOut(BaseModel):
    id: uuid.UUID
    territory_id: uuid.UUID
    agent_profile_id: uuid.UUID
    priority: int

    model_config = {"from_attributes": True}

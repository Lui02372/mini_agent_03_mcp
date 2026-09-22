"""Four explicit roles and bounded request/evidence contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

AgentId = Literal['weather_agent', 'place_agent', 'budget_agent', 'validation_agent']
Provider = Literal['openai', 'gemini', 'ollama', 'mock']
AGENTS = ('weather_agent', 'place_agent', 'budget_agent', 'validation_agent')


class TripRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    city: Literal['서울', '부산', '제주'] = '부산'
    days: int = Field(default=2, ge=1, le=14)
    budget: int = Field(default=300000, ge=10000, le=10000000)
    question: str = Field(default='날씨를 고려한 여행 장소와 예산을 추천해 주세요.', min_length=1, max_length=1000)
    providers: dict[AgentId, Provider] = Field(default_factory=dict)
    data_mode: Literal['auto', 'mock'] = 'auto'
    allow_model_mock: bool = True


class Place(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    admission: int = Field(ge=0, le=1000000)
    outdoor: bool


class TripFacts(BaseModel):
    is_mock: bool = False
    city: str
    weather: str = Field(min_length=1, max_length=200)
    temperature_c: float = Field(ge=-70, le=60)
    places: list[Place] = Field(min_length=1, max_length=6)
    hotel_per_night: int = Field(ge=0, le=10000000)
    food_per_day: int = Field(ge=0, le=1000000)
    transport_per_day: int = Field(ge=0, le=1000000)
    as_of: str = Field(default='확인되지 않음', max_length=100)


class AgentAnswer(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    details: list[str] = Field(max_length=8)
    cautions: list[str] = Field(max_length=8)


class Evidence(BaseModel):
    facts: TripFacts
    source: Literal['mock', 'postgres', 'redis']
    reason: str
    checks: dict[str, str] = Field(default_factory=dict)

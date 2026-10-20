from pydantic import BaseModel, Field, field_validator
from typing import Literal
from urllib.parse import urlsplit

def valid_url(value):
    u = urlsplit(value)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:
        raise ValueError('Use an http or https URL without embedded credentials.')
    return value

class PersonaInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    technical_skill: str = Field(default='moderate', max_length=50)
    goal: str = Field(min_length=1, max_length=2000)
    criteria: list[str] = Field(min_length=1, max_length=30)

    @field_validator('name', 'goal')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('This field cannot be blank.')
        return value.strip()

    @field_validator('criteria')
    @classmethod
    def clean_criteria(cls, values):
        values = [x.strip() for x in values if x.strip()]
        if not values or any(len(x)>500 for x in values):
            raise ValueError('Add at least one criterion, up to 500 characters each.')
        return list(dict.fromkeys(values))

class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=2000)
    description: str = Field(default='', max_length=2000)

    @field_validator('url')
    @classmethod
    def check_url(cls, value):
        return valid_url(value)

class PlanInput(BaseModel):
    url: str = Field(max_length=2000)
    instructions: str = Field(min_length=1, max_length=10000)
    persona_id: str
    screenshot_id: str | None = None
    method: Literal['screenshot', 'live'] = 'screenshot'
    max_actions: int = Field(default=20, ge=1, le=60)
    project_id: str | None = None
    mode: Literal['UX'] = 'UX'

    @field_validator('url')
    @classmethod
    def check_url(cls, value):
        return valid_url(value)

    @field_validator('instructions')
    @classmethod
    def valid_instructions(cls, value):
        if not value.strip():
            raise ValueError('Describe the task to evaluate.')
        return value.strip()

class CaseInput(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=500)
    expected: str = Field(min_length=1, max_length=2000)
    selected: bool = True

    @field_validator('title', 'expected')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Case title and expected behavior are required.')
        return value.strip()

class PlanUpdate(BaseModel):
    cases: list[CaseInput] = Field(min_length=1, max_length=30)

class RunInput(BaseModel):
    plan_id: str

class ScreenshotInput(BaseModel):
    name: str = Field(default='Screenshot', max_length=100)
    data: str = Field(max_length=14000000)

class CaptureInput(BaseModel):
    url: str = Field(max_length=2000)
    name: str = Field(default='TestLab capture', max_length=100)

    @field_validator('url')
    @classmethod
    def local_testlab(cls, value):
        u = urlsplit(valid_url(value))
        if u.hostname not in ('127.0.0.1', 'localhost') or u.port != 5173:
            raise ValueError('Live capture is limited to your local TestLab on port 5173.')
        return value

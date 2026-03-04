from pydantic import BaseModel


class BotInfo(BaseModel):
    name: str
    type: str
    module: str


class BotRunRequest(BaseModel):
    name: str


class BotRunResponse(BaseModel):
    name: str
    task_id: str
    status: str

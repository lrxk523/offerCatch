"""请求体模型（DTO）"""

from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ClearRequest(BaseModel):
    session_id: str = "default"

class JDTextRequest(BaseModel):
    text: str

class MatchRequest(BaseModel):
    resume_text: str = ""
    jd_text: str = ""
    resume_name: str = ""
    jd_title: str = ""
    resume_id: str = ""  # 可选：从 Redis 拉取简历
    jd_title: str = ""


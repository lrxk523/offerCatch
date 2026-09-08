"""对话接口：/api/chat (SSE 流式)、/api/clear、/api/status"""

import json
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from app.agent import Agent
from app.schemas.request import ChatRequest
from app.services.agent_runtime import get_agent

router = APIRouter(prefix="/api", tags=["chat"])

JD_KEYWORDS = {"岗位职责", "任职要求", "岗位要求", "职位描述",
               "工作职责", "本科", "学历", "工程师", "招聘"}

async def _try_direct_skill(agent: Agent, message: str) -> Optional[str]:
    """检测消息是否匹配 Skill 意图，是则直接调用返回格式化结果。"""
    m = message.strip()
    if any(kw in m for kw in JD_KEYWORDS) and len(m) >= 15:
        result = await agent.invoke_skill("parse_jd", text=m)
        if result and result.success and result.message:
            return result.message
    return None

@router.post("/chat")
async def chat(req: ChatRequest):
    agent = get_agent(session_id=req.session_id)

    # JD 类消息直接调 Skill，绕过 LLM
    direct = await _try_direct_skill(agent, req.message)
    if direct is not None:
        async def direct_gen():
            yield f"data: {json.dumps({'type': 'text', 'content': direct}, ensure_ascii=False)}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
        return StreamingResponse(direct_gen(), media_type="text/event-stream")

    async def generate():
        try:
            async for chunk in agent.chat_stream(req.message):
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@router.get("/status")
async def status():
    agent = get_agent()
    return JSONResponse(agent.status())

@router.post("/clear")
async def clear_history():
    agent = get_agent()
    agent.clear_history()
    return JSONResponse({"success": True})


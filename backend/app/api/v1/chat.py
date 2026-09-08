"""对话接口：/api/chat (SSE 流式)、/api/clear、/api/status"""

import json
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from app.agent import Agent
from app.schemas.request import ChatRequest, ClearRequest
from app.services.agent_runtime import get_agent

router = APIRouter(prefix="/api", tags=["chat"])

# JD 捷径触发词：必须包含 JD 结构特征词（职责/要求等），避免"应聘工程师/本科学历"等
# 泛职业词误触发。意图词（分析/解析/看看/帮忙）作为补充命中条件。
JD_KEYWORDS = {
    # JD 结构特征词（强信号）
    "岗位职责", "任职要求", "岗位要求", "职位描述", "工作职责", "任职资格",
    "岗位JD", "岗位jd", "职位jd", "职位JD", "招聘JD", "招聘jd",
    # 意图词（弱信号，需与 JD 上下文组合才触发）
    "分析这个JD", "解析这个JD", "看看这个JD", "分析这个jd", "解析这个jd", "看看这个jd",
    "帮我分析JD", "帮我解析JD", "帮我看看JD", "帮我分析jd", "帮我解析jd", "帮我看看jd",
}

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
async def clear_history(req: Optional[ClearRequest] = None):
    session_id = req.session_id if req else "default"
    agent = get_agent(session_id=session_id)
    agent.clear_history()
    return JSONResponse({"success": True, "session_id": session_id})


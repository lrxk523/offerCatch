"""Agent 运行时：OCR 引擎懒加载单例 + 全局/会话 Agent 池"""

from typing import Dict, Optional

from app.agent import Agent, AgentConfig

from app.skills.jd_parser import JDParseSkill
from app.skills.common.ocr import OCREngine, get_shared_ocr
from app.skills.resume_optimizer import ResumeOptimizeSkill
from app.skills.resume_jd_matcher import ResumeJDMatcherSkill
from app.workflows.jd_workflow import create_jd_parse_workflow

# OCR 引擎全局共享（懒加载单例见 app/skills/common/ocr.py 的 get_shared_ocr）
_base_agent: Optional[Agent] = None
# 会话 Agent 池 {session_id: Agent}
_session_agents: Dict[str, Agent] = {}
_MAX_SESSION_AGENTS = 1000

async def _get_ocr_engine() -> OCREngine:
    """获取全局共享 OCR 引擎（所有模块共用同一实例）"""
    engine = await get_shared_ocr()
    return engine

def get_agent(session_id: str = "") -> Agent:
    """
    获取会话隔离的 Agent 实例。

    无 session_id -> 返回全局共享 Agent（兼容旧调用方）。
    有 session_id -> 返回该会话专属 Agent（对话历史独立于其他会话）。
    """
    if not session_id:
        return _get_base_agent()

    if session_id not in _session_agents:
        base = _get_base_agent()
        agent = Agent(config=base.config, session_id=session_id)
        for skill in base.skills.list_all_raw():
            agent.register_skill(skill)
        for wf in base.workflows.list_all_raw():
            agent.register_workflow(wf)
        _session_agents[session_id] = agent
        if len(_session_agents) > _MAX_SESSION_AGENTS:
            oldest = next(iter(_session_agents))
            del _session_agents[oldest]
    return _session_agents[session_id]

def _get_base_agent() -> Agent:
    """构建/返回全局基础 Agent（skills + workflows 模板）"""
    global _base_agent
    if _base_agent is None:
        config = AgentConfig(
            system_prompt=(
                "你是一个 AI 求职助手，名叫 OfferCatch，帮助用户处理求职相关任务。"
                "你可以使用以下技能：\n"
                "- parse_jd: 解析岗位 JD（职位描述），提取岗位名称/职责/要求/薪资/地点等结构化信息\n"
                "- optimize_resume: 优化润色简历，使其更匹配目标岗位\n"
                "- match_resume_jd: 分析简历与 JD 的关键词重合度和匹配度，生成可视化报告\n\n"
                "【JD 解析规则】\n"
                "当用户发送 JD 文本或说「解析JD」「分析职位」时，调用 parse_jd。\n"
                "如果用户直接粘贴了 JD 文本，将文本传给 parse_jd 的 text 参数。\n\n"
                "【简历优化规则-非常重要】\n"
                "只有当用户提供了完整的简历内容（文本或图片）时，才调用 optimize_resume。\n"
                "如果用户只说「优化简历」「帮我改简历」但没有给出简历内容，\n"
                "请直接回复引导用户：「请上传简历截图或粘贴完整的简历文本，我才能帮你优化哦。你也可以点击侧边栏的『上传简历』按钮。」\n"
                "不要在没有简历内容的情况下调用 optimize_resume 工具。\n\n"
                "调用工具后，将结果用自然语言呈现给用户，不要输出 JSON。"
                "请始终用中文回复，简洁清晰。"
            ),
            temperature=0.7,
        )
        _agent = Agent(config)
        _agent.register_skill(JDParseSkill())
        _agent.register_skill(ResumeOptimizeSkill())
        _agent.register_skill(ResumeJDMatcherSkill())
        _agent.register_workflow(create_jd_parse_workflow())
        print("[Web] Agent 初始化完成")
    return _agent


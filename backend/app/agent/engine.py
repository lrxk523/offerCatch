"""智能体核心引擎 - 整合 LLM、Skill、Workflow"""

import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import AsyncOpenAI

from .skill import Skill, SkillRegistry, SkillResult
from .workflow import Workflow, WorkflowRegistry, StepResult

load_dotenv()


class AgentConfig:
    """Agent 全局配置"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        system_prompt: str = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        from app.core.config import get_llm_config
        default_key, default_url, default_model = get_llm_config("default")
        self.api_key = api_key or default_key
        self.base_url = base_url or default_url
        self.model = model or default_model
        self.system_prompt = system_prompt or "你是一个有用的智能助手。你可以使用各种技能来帮助用户解决问题。"
        self.max_tokens = max_tokens
        self.temperature = temperature


class Agent:
    """对话智能体"""

    def __init__(self, config: AgentConfig = None, session_id: str = ""):
        self.config = config or AgentConfig()
        self.skills = SkillRegistry()
        self.workflows = WorkflowRegistry()
        self._client: Optional[AsyncOpenAI] = None
        self._session_id = session_id
        self._conversation_history: List[Dict[str, Any]] = []
        self._max_history = 20

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    def _use_redis(self) -> bool:
        """是否启用 Redis 持久化（有 session_id 时启用）"""
        return bool(self._session_id)

    def _add_to_history(self, role: str, content: str) -> None:
        entry = {"role": role, "content": content}
        self._conversation_history.append(entry)
        if self._use_redis():
            from app.db.chat_history import save_message
            save_message(self._session_id, entry)
        if len(self._conversation_history) > self._max_history:
            self._conversation_history = self._conversation_history[-self._max_history:]

    def _load_history(self) -> None:
        """从 Redis 加载历史（session 模式），合并到内存"""
        if not self._use_redis():
            return
        from app.db.chat_history import load_history
        remote = load_history(self._session_id, self._max_history)
        # 仅当远端有更新时才替换（避免每轮反复覆盖）
        if remote and len(remote) > len(self._conversation_history):
            self._conversation_history = remote

    def clear_history(self) -> None:
        """清空对话历史"""
        self._conversation_history.clear()
        if self._use_redis():
            from app.db.chat_history import clear_history
            clear_history(self._session_id)

    # ---- Skill 管理 ----

    def register_skill(self, skill: Skill) -> "Agent":
        """注册 Skill，支持链式调用"""
        self.skills.register(skill)
        return self

    def register_skills(self, *skills: Skill) -> "Agent":
        """批量注册 Skill"""
        for s in skills:
            self.skills.register(s)
        return self

    # ---- Workflow 管理 ----

    def register_workflow(self, workflow: Workflow) -> "Agent":
        """注册 Workflow"""
        self.workflows.register(workflow)
        return self

    # ---- 对话核心 ----

    def _build_system_message(self) -> Dict[str, Any]:
        """构建 system message，注入 skill/workflow 信息"""
        skill_info = "\n".join(
            f"- **{s['name']}**: {s['description']}" for s in self.skills.list_all()
        ) or "无可用技能"

        workflow_info = "\n".join(
            f"- **{w['name']}**: {w['description']}" for w in self.workflows.list_all()
        ) or "无可用工作流"

        prompt = f"""{self.config.system_prompt}

## 可用技能 (Skills)
{skill_info}

## 可用工作流 (Workflows)
{workflow_info}

## 指令
当用户请求匹配某个技能时，请使用 function calling 调用对应工具。
当用户需要多步骤操作时，可以建议使用对应的工作流。
调用工具后，请基于工具返回的结果，用自然语言回复用户。"""
        return {"role": "system", "content": prompt}

    async def chat(self, user_input: str, max_tool_rounds: int = 2) -> str:
        """同步对话（返回完整回复），最多执行 max_tool_rounds 轮工具调用防止死循环"""
        self._load_history()
        self._add_to_history("user", user_input)

        tools = self.skills.get_all_tool_schemas()
        round_count = 0
        final_result: List[str] = []

        while round_count <= max_tool_rounds:
            round_count += 1
            messages = [self._build_system_message()] + self._conversation_history

            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )

            msg = response.choices[0].message

            # 没有 tool calls，直接返回
            if not msg.tool_calls:
                content = msg.content or ""
                if round_count == 1:
                    self._add_to_history("assistant", content)
                    return content
                else:
                    final_result.append(content)
                    break

            # 记录 assistant 的 tool call
            self._conversation_history.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # 执行工具调用
            tool_results = []
            for tc in msg.tool_calls:
                tool_result = await self._execute_tool(tc.function.name, tc.function.arguments)
                tool_results.append(json.loads(tool_result))

            # tool 响应先入历史：assistant(tool_calls) 后必有对应 tool 消息（内存），序列才合法
            for i, tc in enumerate(msg.tool_calls):
                self._conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_results[i], ensure_ascii=False),
                })

            # ★ 如果 Skill 已返回格式化好的 message，直接展示
            display_text = None
            for tr in tool_results:
                if tr.get("success") and tr.get("message") and len(tr["message"]) > 20:
                    display_text = tr["message"]
                    break

            if display_text:
                self._add_to_history("assistant", display_text)
                return display_text

        # 超出轮次或正常结束
        if final_result:
            final_content = "".join(final_result)
            self._add_to_history("assistant", final_content)
            return final_content
        return ""

    async def chat_stream(self, user_input: str, max_tool_rounds: int = 2) -> AsyncGenerator[str, None]:
        """流式对话，最多执行 max_tool_rounds 轮工具调用防止死循环"""
        self._load_history()
        self._add_to_history("user", user_input)

        tools = self.skills.get_all_tool_schemas()
        round_count = 0

        while round_count <= max_tool_rounds:
            round_count += 1
            messages = [self._build_system_message()] + self._conversation_history

            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                stream=True,
            )

            # 收集流式输出的 tool_calls
            tool_calls_acc: Dict[int, Dict] = {}
            content_parts: List[str] = []

            async for chunk in response:
                delta = chunk.choices[0].delta

                if delta.content:
                    content_parts.append(delta.content)
                    # ★ 不立即 yield — 等确认没有 tool_calls 再输出

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc.id or "",
                                "function_name": "",
                                "function_args": "",
                            }
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_acc[idx]["function_name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_acc[idx]["function_args"] += tc.function.arguments

            # 没有 tool calls 就结束
            if not tool_calls_acc:
                full = "".join(content_parts)
                self._add_to_history("assistant", full)
                yield full
                return

            # 最后一轮不允许再调工具，强制文本回复
            if round_count > max_tool_rounds:
                self._add_to_history("assistant", "".join(content_parts))
                yield "\n\n⚠️ 已达到最大工具调用次数，请提供更多信息后重试。"
                return

            # 记录 assistant 的 tool call
            full_content = "".join(content_parts)
            tc_list = []
            for tc_data in tool_calls_acc.values():
                tc_list.append({
                    "id": tc_data["id"],
                    "type": "function",
                    "function": {
                        "name": tc_data["function_name"],
                        "arguments": tc_data["function_args"],
                    },
                })

            self._conversation_history.append({
                "role": "assistant",
                "content": full_content,
                "tool_calls": tc_list,
            })

            # 执行工具调用
            tool_messages = []
            for tc_data in tool_calls_acc.values():
                tool_result = await self._execute_tool(
                    tc_data["function_name"], tc_data["function_args"]
                )
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tc_data["id"],
                    "content": tool_result,
                })

            # tool 响应先入历史：assistant(tool_calls) 后必有对应 tool 消息（内存），序列才合法
            self._conversation_history.extend(tool_messages)

            # ★ 关键改进：如果 Skill 已返回格式化好的 message，直接展示，不让 LLM 重包装
            display_text = None
            for tm in tool_messages:
                try:
                    parsed = json.loads(tm["content"])
                    msg = parsed.get("message", "")
                    # 只对成功的、有具体格式化内容的技能结果做直接展示
                    if parsed.get("success") and msg and len(msg) > 20:
                        display_text = msg
                        break
                except (json.JSONDecodeError, TypeError):
                    pass

            if display_text:
                self._add_to_history("assistant", display_text)
                yield display_text
                return

    # ---- 工具执行 ----

    async def _execute_tool(self, function_name: str, arguments: str) -> str:
        """执行 tool call"""
        try:
            args = json.loads(arguments) if arguments else {}

            # 优先匹配 Skill
            skill = self.skills.get(function_name)
            if skill:
                result: SkillResult = await skill.execute(**args)
                return json.dumps({
                    "success": result.success,
                    "data": result.data,
                    "message": result.message,
                }, ensure_ascii=False)

            # 匹配 Workflow
            results = await self.workflows.execute(function_name, args)
            if results is not None:
                summary = []
                for r in results:
                    summary.append(f"[{r.status.value}] {r.step_name}: {r.output or r.error or ''}")
                return json.dumps({"workflow": function_name, "steps": summary}, ensure_ascii=False)

            return json.dumps({"error": f"未找到工具: {function_name}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    # ---- 直接调用 Skill ----

    async def invoke_skill(self, skill_name: str, **kwargs) -> Optional[SkillResult]:
        """直接调用指定 Skill"""
        skill = self.skills.get(skill_name)
        if not skill:
            return None
        return await skill.execute(**kwargs)

    # ---- 直接调用 Workflow ----

    async def invoke_workflow(self, workflow_name: str, ctx: Dict = None) -> Optional[List[StepResult]]:
        """直接调用指定 Workflow"""
        return await self.workflows.execute(workflow_name, ctx)

    # ---- 状态查询 ----

    def status(self) -> Dict[str, Any]:
        """获取 Agent 状态"""
        return {
            "model": self.config.model,
            "skills": self.skills.skill_names,
            "workflows": self.workflows.workflow_names,
            "conversation_turns": len(self._conversation_history) // 2,
        }

    def print_status(self) -> None:
        """打印状态信息"""
        s = self.status()
        print(f"\n{'='*50}")
        print(f"Agent Status")
        print(f"{'='*50}")
        print(f"  Model:      {s['model']}")
        print(f"  Skills:     {', '.join(s['skills']) if s['skills'] else 'none'}")
        print(f"  Workflows:  {', '.join(s['workflows']) if s['workflows'] else 'none'}")
        print(f"  History:    {s['conversation_turns']} turns")
        print(f"{'='*50}\n")

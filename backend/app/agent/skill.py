"""Skill 系统 - 可插拔的能力模块"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class SkillResult:
    """Skill 执行结果"""
    success: bool
    data: Any = None
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class Skill(ABC):
    """Skill 基类，所有 Skill 需继承此类"""

    name: str = ""
    description: str = ""
    keywords: List[str] = []
    triggers: List[str] = []  # 触发短语，用于自动路由

    @abstractmethod
    async def execute(self, **kwargs) -> SkillResult:
        """执行 Skill 逻辑"""
        ...

    def match(self, user_input: str) -> float:
        """根据用户输入计算匹配置信度 0.0-1.0，默认用 triggers 匹配"""
        user_lower = user_input.lower()
        for trigger in self.triggers:
            if trigger.lower() in user_lower:
                return 0.8
        for kw in self.keywords:
            if kw.lower() in user_lower:
                return 0.5
        return 0.0

    def tool_schema(self) -> Optional[Dict[str, Any]]:
        """返回 OpenAI function calling 的 tool schema，子类可选重写"""
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "triggers": self.triggers,
        }


class SkillRegistry:
    """Skill 注册中心"""

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._hooks: Dict[str, List[Callable]] = {
            "before_execute": [],
            "after_execute": [],
        }

    def register(self, skill: Skill) -> None:
        """注册一个 Skill"""
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' already registered")
        self._skills[skill.name] = skill
        print(f"[SkillRegistry] Registered skill: {skill.name}")

    def unregister(self, name: str) -> None:
        """注销一个 Skill"""
        self._skills.pop(name, None)

    def get(self, name: str) -> Optional[Skill]:
        """按名称获取 Skill"""
        return self._skills.get(name)

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有已注册 Skill 的元信息"""
        return [s.to_dict() for s in self._skills.values()]

    def list_all_raw(self) -> List["Skill"]:
        """返回所有已注册 Skill 实例（用于共享给子 Agent）"""
        return list(self._skills.values())

    def match(self, user_input: str, threshold: float = 0.5) -> Optional[Skill]:
        """根据用户输入匹配最佳 Skill"""
        best: Optional[Skill] = None
        best_score = threshold
        for skill in self._skills.values():
            score = skill.match(user_input)
            if score > best_score:
                best_score = score
                best = skill
        return best

    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        """获取所有 Skill 的 function calling schema"""
        schemas = []
        for skill in self._skills.values():
            schema = skill.tool_schema()
            if schema:
                schemas.append(schema)
        return schemas

    def add_hook(self, event: str, callback: Callable) -> None:
        """添加生命周期钩子"""
        if event in self._hooks:
            self._hooks[event].append(callback)

    async def run_hooks(self, event: str, **kwargs) -> None:
        """运行指定事件的所有钩子"""
        for hook in self._hooks.get(event, []):
            await hook(**kwargs)

    @property
    def skill_names(self) -> List[str]:
        return list(self._skills.keys())

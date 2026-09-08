"""Workflow 工作流引擎 - 支持编排多个 Skill 形成流程"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import asyncio


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowContext:
    """工作流上下文，在步骤间传递数据"""
    data: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def update(self, d: Dict[str, Any]) -> None:
        self.data.update(d)


@dataclass
class StepResult:
    """单步执行结果"""
    step_name: str
    status: StepStatus
    output: Any = None
    error: Optional[str] = None


class WorkflowStep(ABC):
    """工作流步骤基类"""

    name: str = ""

    @abstractmethod
    async def run(self, ctx: WorkflowContext) -> StepResult:
        """执行步骤"""
        ...


class SkillStep(WorkflowStep):
    """将 Skill 包装为工作流步骤"""

    def __init__(self, skill, step_name: str = None, input_map: Dict[str, str] = None):
        from .skill import Skill
        self.skill: Skill = skill
        self.name = step_name or f"skill:{skill.name}"
        # input_map: skill参数名 -> ctx中的key名
        self.input_map = input_map or {}

    async def run(self, ctx: WorkflowContext) -> StepResult:
        try:
            kwargs = {param: ctx.get(ctx_key) for param, ctx_key in self.input_map.items()}
            result = await self.skill.execute(**kwargs)
            ctx.set(f"__result_{self.name}", result)
            return StepResult(
                step_name=self.name,
                status=StepStatus.COMPLETED if result.success else StepStatus.FAILED,
                output=result,
                error=result.message if not result.success else None,
            )
        except Exception as e:
            return StepResult(step_name=self.name, status=StepStatus.FAILED, error=str(e))


class ConditionalStep(WorkflowStep):
    """条件步骤 - 根据上下文决定执行哪个分支"""

    def __init__(self, condition, true_step: WorkflowStep,
                 false_step: WorkflowStep = None, step_name: str = "conditional"):
        self.condition = condition  # async callable(ctx) -> bool
        self.true_step = true_step
        self.false_step = false_step
        self.name = step_name

    async def run(self, ctx: WorkflowContext) -> StepResult:
        try:
            if await self.condition(ctx):
                return await self.true_step.run(ctx)
            elif self.false_step:
                return await self.false_step.run(ctx)
            return StepResult(step_name=self.name, status=StepStatus.SKIPPED)
        except Exception as e:
            return StepResult(step_name=self.name, status=StepStatus.FAILED, error=str(e))


class Workflow:
    """工作流编排器"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._steps: List[WorkflowStep] = []
        self._on_error: Optional[str] = "stop"  # "stop" | "continue" | "rollback"

    def add_step(self, step: WorkflowStep) -> "Workflow":
        """添加步骤，支持链式调用"""
        self._steps.append(step)
        return self

    def on_error(self, strategy: str) -> "Workflow":
        """设置错误处理策略"""
        self._on_error = strategy
        return self

    async def execute(self, initial_ctx: Dict[str, Any] = None) -> List[StepResult]:
        """执行整个工作流"""
        ctx = WorkflowContext(data=initial_ctx or {})
        results: List[StepResult] = []

        for step in self._steps:
            result = await step.run(ctx)
            results.append(result)

            if result.status == StepStatus.FAILED:
                if self._on_error == "stop":
                    break
                elif self._on_error == "continue":
                    continue
                # rollback 可后续扩展

        return results

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps_count": len(self._steps),
        }


class WorkflowRegistry:
    """工作流注册中心"""

    def __init__(self):
        self._workflows: Dict[str, Workflow] = {}

    def register(self, workflow: Workflow) -> None:
        """注册工作流"""
        self._workflows[workflow.name] = workflow
        print(f"[WorkflowRegistry] Registered workflow: {workflow.name}")

    def get(self, name: str) -> Optional[Workflow]:
        """按名称获取工作流"""
        return self._workflows.get(name)

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有工作流"""
        return [w.to_dict() for w in self._workflows.values()]

    def list_all_raw(self) -> List[Workflow]:
        """返回所有已注册 Workflow 实例（用于共享给子 Agent）"""
        return list(self._workflows.values())

    async def execute(self, name: str, ctx: Dict[str, Any] = None) -> Optional[List[StepResult]]:
        """执行指定工作流"""
        wf = self._workflows.get(name)
        if not wf:
            return None
        return await wf.execute(ctx)

    @property
    def workflow_names(self) -> List[str]:
        return list(self._workflows.keys())

"""内置示例 Workflows"""

from app.agent.workflow import Workflow, SkillStep, ConditionalStep, WorkflowContext
from app.skills.builtin_skills import WeatherSkill, TimeSkill, CalculatorSkill


def create_daily_brief_workflow() -> Workflow:
    """每日简报工作流：获取时间 + 天气"""
    wf = Workflow(
        name="daily_brief",
        description="生成每日简报，包含当前时间和天气信息"
    )
    wf.add_step(SkillStep(TimeSkill(), step_name="get_current_time"))
    wf.add_step(SkillStep(
        WeatherSkill(),
        step_name="get_weather",
        input_map={"city": "city"}
    ))
    return wf


def create_smart_calc_workflow() -> Workflow:
    """智能计算工作流：先获取表达式再计算"""
    wf = Workflow(
        name="smart_calc",
        description="接收数学表达式并计算结果"
    )
    wf.add_step(SkillStep(
        CalculatorSkill(),
        step_name="do_calculation",
        input_map={"expression": "expression"}
    ))
    return wf

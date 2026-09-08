"""JD 解析工作流 - OCR → 清洗 → 解析"""

from app.agent.workflow import Workflow, SkillStep, WorkflowContext, WorkflowStep, StepResult, StepStatus
from app.skills.jd_parser import JDParseSkill


def create_jd_parse_workflow() -> Workflow:
    """
    JD 解析工作流:
      上传 JD 截图 → OCR 提取全部文字 → 清洗排版 → 还原完整岗位要求
    """
    wf = Workflow(
        name="jd_parse_pipeline",
        description="上传 JD 截图 → OCR 提取文字 → 清洗排版 → 提取结构化岗位信息"
    )

    # 单步调用 JDParseSkill 即可完成全流程
    # (OCR → 清洗 → 分段 → 提取 均在该 Skill 内部完成)
    wf.add_step(SkillStep(
        JDParseSkill(),
        step_name="parse_jd",
        input_map={
            "image_path": "image_path",
            "image_base64": "image_base64",
            "text": "jd_text",
        }
    ))

    return wf

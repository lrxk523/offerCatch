"""简历优化 Skill - 上传简历 → 解析 → LLM优化 → 输出建议"""

import asyncio
import os
import traceback
from typing import Optional

from app.agent.skill import Skill, SkillResult
from .parser import ResumeParser, ResumeData, LLMResumeParser
from .optimizer import ResumeOptimizer
from app.skills.common.ocr import OCREngine, get_shared_ocr


class ResumeOptimizeSkill(Skill):
    """简历优化 Skill"""

    name = "optimize_resume"
    description = (
        "上传简历（文本/图片），自动解析简历内容，"
        "使用 AI 进行深度审计和优化润色，"
        "输出结构化优化建议和改写后的简历内容。"
    )
    keywords = [
        "简历", "resume", "CV", "优化简历", "润色简历",
        "修改简历", "简历优化", "简历润色", "完善简历",
        "美化简历", "简历修改", "优化我的简历",
    ]
    triggers = [
        "优化简历", "帮我优化简历", "润色我的简历",
        "修改简历", "帮我改简历", "优化我的简历",
        "美化简历", "简历优化", "帮我看看简历",
        "完善简历", "润色简历",
    ]

    def __init__(self):
        self._ocr: Optional[OCREngine] = None
        self._optimizer: Optional[ResumeOptimizer] = None

    async def _ensure_ocr(self):
        """获取全局共享 OCR 引擎（与 API 层/其他 skill 同实例）"""
        if self._ocr is not None:
            return
        self._ocr = await get_shared_ocr()

    def _ensure_optimizer(self):
        """延迟初始化优化器"""
        if self._optimizer is None:
            self._optimizer = ResumeOptimizer()

    async def execute(
        self,
        text: str = "",
        image_base64: str = "",
        image_path: str = "",
        resume_id: str = "",       # Redis 简历 ID
        target_position: str = "",
        **kwargs,
    ) -> SkillResult:
        """
        执行简历优化。

        参数:
          - text: 简历文本内容
          - image_base64: 简历图片的 base64 编码
          - image_path: 简历图片的本地路径
          - resume_id: Redis 中的简历 ID，自动加载已存储的简历
          - target_position: 目标岗位（用于定向优化）
        """
        try:
            raw_text = ""
            on_progress = kwargs.get("on_progress")  # 阶段进度回调（resume.py 注入 → 转发 SSE）

            # ---- 从 Redis 加载简历 ----
            if resume_id and not text and not image_base64 and not image_path:
                from app.db.resume_store import load_resume_text
                loaded_text, loaded_name = load_resume_text(resume_id)
                if loaded_text:
                    raw_text = loaded_text
                    text = raw_text
                    if loaded_name and not target_position:
                        target_position = loaded_name
                    print(f"[ResumeOptimizer] 从 Redis ({resume_id}) 加载简历, {len(raw_text)} 字符")
                else:
                    return SkillResult(
                        success=False,
                        message=f"无法从 Redis 加载简历 (id={resume_id})，请重新上传",
                    )

            # ---- 第1步: 获取原始文本 ----
            if text:
                if len(text.strip()) < 30:
                    return SkillResult(
                        success=False,
                        message="简历内容太少，无法解析。请粘贴完整的简历文本（至少包含教育经历、工作经历等信息），或上传简历截图。",
                    )
                raw_text = text
            elif image_base64 or image_path:
                await self._ensure_ocr()
                image_input = image_base64 if image_base64 else image_path
                raw_text = await self._ocr.extract_text(image_input)
                if not raw_text or len(raw_text.strip()) < 10:
                    return SkillResult(
                        success=False,
                        message="OCR 未能识别到有效简历内容，请确保图片清晰或直接粘贴文字",
                        data={"ocr_engine": self._ocr.engine_name},
                    )
            else:
                return SkillResult(
                    success=False,
                    message="请上传简历截图或粘贴完整的简历文本。点击侧边栏「📄 上传简历」按钮上传截图，或点击「📝 优化简历」粘贴文本。",
                )

            # ---- 第2+3步: 解析 + 优化 (合并为单次 LLM 调用) ----
            # 提供 on_progress 时强制分步：合并是单次 LLM 调用，中间无阶段可报
            use_combined = os.getenv("RESUME_COMBINED_LLM", "1") != "0" and not on_progress

            if use_combined:
                # 快速路径：一次 LLM 调用同时完成解析+优化
                try:
                    loop = asyncio.get_event_loop()
                    resume_data, optimized = await loop.run_in_executor(
                        None, LLMResumeParser.parse_and_optimize,
                        raw_text, target_position,
                    )
                except Exception as e:
                    # 合并路径失败，fallback 到分步
                    print(f"[ResumeOptimizer] 合并调用失败({e})，回退分步调用")
                    use_combined = False

            if not use_combined:
                # 慢速路径：先解析，再优化（两次 LLM 调用，可报阶段进度）
                if on_progress:
                    await on_progress("llm", "正在提取简历结构化信息（教育/工作/项目/技能）...")
                try:
                    loop = asyncio.get_event_loop()
                    resume_data: ResumeData = await loop.run_in_executor(None, ResumeParser.parse, raw_text)
                except Exception as parse_err:
                    traceback.print_exc()
                    return SkillResult(success=False, message=f"简历解析失败: {str(parse_err)}")

                has_content = (
                    resume_data.work_experience or
                    resume_data.project_experience or
                    resume_data.skills or
                    resume_data.education
                )
                if not has_content:
                    return SkillResult(
                        success=False,
                        message="未能从文本中解析到有效简历信息。请确保简历包含工作经历、项目经历、教育背景或技能等信息。",
                        data={"raw_text_preview": raw_text[:300]},
                    )

                if on_progress:
                    pos = f"（目标岗位：{target_position}）" if target_position else ""
                    await on_progress("llm", f"AI 正在逐段审计并实质性改写简历{pos}...")
                try:
                    self._ensure_optimizer()
                    loop = asyncio.get_event_loop()
                    optimized = await loop.run_in_executor(
                        None, self._optimizer.optimize, resume_data, target_position
                    )
                except Exception as opt_err:
                    traceback.print_exc()
                    return SkillResult(success=False, message=f"LLM优化失败: {str(opt_err)}")

                if optimized is None:
                    return SkillResult(success=False, message="LLM 优化返回了空结果")

            # 内容检查（合并路径也需要）
            has_content = (
                resume_data.work_experience or
                resume_data.project_experience or
                resume_data.skills or
                resume_data.education
            )
            if not has_content:
                return SkillResult(
                    success=False,
                    message="未能从文本中解析到有效简历信息。请确保简历包含工作经历、项目经历、教育背景或技能等信息。",
                    data={"raw_text_preview": raw_text[:300]},
                )

            # ---- 后处理：检测相似并自动增强 ----
            self._ensure_optimizer()
            optimized = self._optimizer.post_process(resume_data, optimized)

            # ---- 格式化输出 ----
            formatted = self._format_output(resume_data, optimized)

            return SkillResult(
                success=True,
                data={
                    "parsed": resume_data.to_dict(),
                    "optimized": {
                        "verdict": optimized.get("verdict", ""),
                        "self_evaluation": optimized.get("self_evaluation", ""),
                        "work_experience": optimized.get("work_experience", []),
                        "project_experience": optimized.get("project_experience", []),
                        "optimization_summary": optimized.get("optimization_summary", ""),
                    },
                    "optimized_count": {
                        "work_experience": len(optimized.get("work_experience", [])),
                        "project_experience": len(optimized.get("project_experience", [])),
                    },
                    "raw_text": raw_text,
                },
                message=formatted,
                metadata={
                    "name": resume_data.name,
                    "exp_count": len(resume_data.work_experience),
                    "proj_count": len(resume_data.project_experience),
                    "skill_count": len(resume_data.skills),
                },
            )

        except Exception as e:
            traceback.print_exc()
            return SkillResult(success=False, message=f"简历优化失败: {str(e)}")

    def _format_output(self, resume: ResumeData, optimized: dict) -> str:
        """格式化输出 — 审计报告 + 优化前后对比"""
        lines = ["# 🔎 简历审计与优化报告\n"]

        # 确定用于"原文"对比的数据源（优先使用 true_original）
        true_orig = optimized.get("_true_original", {})
        orig_work = true_orig.get("work_experience", resume.work_experience) if true_orig else resume.work_experience
        orig_proj = true_orig.get("project_experience", resume.project_experience) if true_orig else resume.project_experience

        # ---- 一句话结论 (LLM 返回 verdict) ----
        verdict = optimized.get("verdict", optimized.get("one_line_verdict", ""))
        if isinstance(verdict, list):
            verdict = "；".join(str(v) for v in verdict if v)
        if verdict:
            lines.append(f"> {verdict}")

        # ---- 优化建议 (用户最关心，放前面) ----
        summary = optimized.get("optimization_summary", "")
        if summary:
            lines.append("\n## 💡 优化建议")
            # LLM 可能返回 string 或 list，兼容两种情况
            if isinstance(summary, list):
                items = [str(s) for s in summary if s]
            else:
                items = str(summary).replace("；", ";").replace("\n", ";").split(";")
            for item in items:
                item = item.strip().strip("。")
                if item:
                    lines.append(f"- {item}")

        # ---- 优化后自我评价 ----
        opt_eval = optimized.get("self_evaluation", "")
        if isinstance(opt_eval, list):
            opt_eval = "\n".join(str(v) for v in opt_eval if v)
        if opt_eval:
            lines.append("\n## 💪 优化后自我评价")
            lines.append(f"\n{opt_eval}")

        # ---- 工作经历对比 ----
        opt_work = optimized.get("work_experience", [])
        if opt_work:
            lines.append(f"\n## 📝 工作经历优化")
            for i, exp in enumerate(opt_work[:5], 1):
                company = exp.get("company", "某公司")
                position = exp.get("position", "")
                header = company
                if position:
                    header += f" | {position}"
                lines.append(f"\n### {i}. {header}")

                orig_exp = orig_work[i - 1] if i - 1 < len(orig_work) else {}
                orig_resp = orig_exp.get("responsibilities", [])
                if orig_resp:
                    lines.append("\n> 原文：")
                    for r in orig_resp[:3]:
                        lines.append(f"> • {r}")

                opt_resp = exp.get("responsibilities", [])
                if opt_resp:
                    lines.append("\n优化后：")
                    for r in opt_resp:
                        lines.append(f"• {r}")

        # ---- 项目经历对比 ----
        opt_proj_list = optimized.get("project_experience", [])
        if opt_proj_list:
            lines.append(f"\n## 📌 项目经历优化")
            for i, proj in enumerate(opt_proj_list[:5], 1):
                name = proj.get("name", "未命名项目")
                desc = proj.get("description", "")
                lines.append(f"\n### {i}. {name}")
                if desc:
                    lines.append(f"{desc}")

                orig_p = orig_proj[i - 1] if i - 1 < len(orig_proj) else {}
                orig_hl = orig_p.get("highlights", [])
                if orig_hl:
                    lines.append("\n> 原文：")
                    for h in orig_hl[:3]:
                        lines.append(f"> • {h}")

                opt_hl = proj.get("highlights", [])
                if opt_hl:
                    lines.append("\n优化后：")
                    for h in opt_hl:
                        lines.append(f"• {h}")

        # ---- 底部提示 ----
        auto_count = optimized.get("_auto_enhanced_count", 0)
        if auto_count > 0:
            lines.append(f"\n---\n_💡 有 {auto_count} 条描述经智能增强优化，建议补充具体量化数据以进一步提升说服力_")

        return "\n".join(lines)

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "简历文本内容（如果用户直接粘贴了简历）",
                        },
                        "image_base64": {
                            "type": "string",
                            "description": "简历截图的 base64 编码",
                        },
                        "target_position": {
                            "type": "string",
                            "description": "求职者目标岗位，用于定向优化，如 '前端工程师'、'产品经理'",
                        },
                    },
                },
            },
        }

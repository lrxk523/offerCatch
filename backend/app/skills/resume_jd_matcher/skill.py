"""简历与JD匹配度分析 Skill - 可视化重合关键词 + 匹配度分析报告"""

import traceback
from typing import Optional

from app.agent.skill import Skill, SkillResult
from app.skills.resume_optimizer.parser import ResumeParser, ResumeData
from app.skills.common.text_cleaner import JDTextCleaner
from app.skills.jd_parser.parser import (
    JDSectionSplitter,
    JDExtractor,
    JDParsedResult,
)

from .matcher import KeywordExtractor, ResumeJDMatcher, MatchResult, LLMMatcher, OCRKeywordMatcher
from .visualizer import MatchVisualizer


class ResumeJDMatcherSkill(Skill):
    """简历与JD匹配度分析 Skill"""

    name = "match_resume_jd"
    description = (
        "分析简历与岗位JD的关键词重合度和匹配度，"
        "生成可视化报告，包括重合关键词展示、维度分析、"
        "匹配评分和优化建议。"
    )
    keywords = [
        "匹配度", "匹配分析", "简历匹配", "jd匹配",
        "岗位匹配", "重合", "重合度", "匹配度分析",
        "和jd", "和职位", "合不合", "匹配情况",
        "匹配程度", "对比分析", "对比简历", "简历对比",
        "match", "匹配报告", "关键词重合", "重合分析",
    ]
    triggers = [
        "匹配度分析", "分析匹配度", "简历和jd匹配",
        "匹配分析", "对比简历和jd", "简历匹配分析",
        "分析简历和岗位", "重合度分析", "关键词重合",
        "帮我看看匹配度", "匹配度怎么样", "看看匹不匹配",
        "分析一下匹配", "match analysis",
    ]

    async def execute(
        self,
        resume_text: str = "",
        jd_text: str = "",
        resume_name: str = "",
        jd_title: str = "",
        resume_id: str = "",  # Redis 简历 ID：resume_text 为空时自动加载
        mode: str = "",       # "ocr" 表示使用 OCR 关键词搜索模式
        ocr_text: str = "",   # OCR 模式下传入的已识别文本
        **kwargs,
    ) -> SkillResult:
        """
        执行简历-JD匹配度分析。

        参数:
          - resume_text: 简历文本内容（文本模式必填）
          - jd_text: JD文本内容（必填）
          - resume_name: 简历主人姓名（选填，用于报告标题）
          - jd_title: JD岗位名称（选填，用于报告标题）
          - resume_id: Redis 中的简历 ID，resume_text 为空时自动加载
          - mode: "ocr" 使用 OCR 关键词搜索模式
          - ocr_text: OCR 已识别文本（OCR 模式必填）
        """
        # ---- 从 Redis 加载简历 ----
        if resume_id and not resume_text:
            from app.db.resume_store import load_resume_text
            loaded_text, loaded_name = load_resume_text(resume_id)
            if loaded_text:
                resume_text = loaded_text
                if loaded_name and not resume_name:
                    resume_name = loaded_name
                print(f"[Matcher] 从 Redis ({resume_id}) 加载简历, {len(resume_text)} 字符")
            else:
                return SkillResult(
                    success=False,
                    message=f"无法从 Redis 加载简历 (id={resume_id})，请重新上传",
                )
        # OCR 模式：委托给 execute_ocr
        if mode == "ocr":
            return await self.execute_ocr(
                jd_text=jd_text,
                ocr_text=ocr_text,
                jd_title=jd_title,
                resume_name=resume_name,
                **kwargs,
            )

        try:
            # ---- 校验输入 ----
            if not resume_text or len(resume_text.strip()) < 30:
                return SkillResult(
                    success=False,
                    message="简历内容太少，无法分析。请提供完整的简历文本（至少包含教育经历、工作经历、技能等信息）。",
                )

            if not jd_text or len(jd_text.strip()) < 20:
                return SkillResult(
                    success=False,
                    message="JD内容太少，无法分析。请提供完整的岗位描述。",
                )

            # ---- 第1步: 解析简历为结构化数据 ----
            try:
                resume_data: ResumeData = ResumeParser.parse(resume_text.strip())
                has_resume_content = (
                    resume_data.work_experience or
                    resume_data.project_experience or
                    resume_data.skills or
                    resume_data.education
                )
                if not has_resume_content:
                    print(f"[Matcher] 简历结构化解析无内容，但仍尝试 LLM 匹配")
            except Exception as e:
                print(f"[Matcher] 简历解析失败({e})，使用原始文本")
                resume_data = None

            # ---- 第2步: 解析 JD 为结构化数据 ----
            try:
                cleaned_jd = JDTextCleaner.clean(jd_text.strip())
                jd_sections = JDSectionSplitter.split(cleaned_jd)
                jd_result: JDParsedResult = JDExtractor.extract(cleaned_jd, jd_sections)
            except Exception as e:
                print(f"[Matcher] JD 解析失败({e})，使用原始文本")
                jd_result = JDParsedResult()
                jd_result.job_title = jd_title

            display_name = resume_name or (resume_data.name if resume_data else "") or "候选人简历"
            display_jd = jd_title or jd_result.job_title or "目标岗位"

            # ---- 第3步: LLM 智能匹配（主路径） ----
            print(f"[Matcher] 使用 LLM 智能匹配引擎...")
            match_result: Optional[MatchResult] = LLMMatcher.match(
                resume_text=resume_text.strip(),
                jd_text=jd_text.strip(),
                resume_data=resume_data,
                jd_parsed=jd_result,
                resume_name=display_name,
                jd_title=display_jd,
            )

            if match_result is not None and match_result.overall_score > 0:
                print(f"[Matcher] LLM 匹配成功，综合评分: {match_result.overall_score}")
            else:
                print(f"[Matcher] LLM 匹配失败，降级为关键词匹配...")
                match_result = None

            # ---- 第4步: 关键词匹配（应急 fallback） ----
            if match_result is None:
                # 简历关键词
                if resume_data and has_resume_content:
                    resume_kw = KeywordExtractor.extract_from_resume(resume_data.to_dict())
                else:
                    resume_kw = KeywordExtractor.extract_from_text(resume_text)

                # JD 关键词
                if jd_result.requirements or jd_result.responsibilities:
                    jd_kw = KeywordExtractor.extract_from_jd(
                        {
                            "job_title": jd_result.job_title,
                            "requirements": jd_result.requirements,
                            "responsibilities": jd_result.responsibilities,
                            "education": jd_result.education,
                            "experience": jd_result.experience,
                        },
                        jd_text=getattr(jd_result, 'cleaned_text', '') or jd_text.strip(),
                    )
                else:
                    jd_kw = KeywordExtractor.extract_from_jd_text(jd_text.strip())

                if not resume_kw.all_keywords:
                    return SkillResult(
                        success=False,
                        message="无法从简历中提取关键词，且 LLM 匹配不可用。请确保简历包含技术栈、工作职责等具体内容。",
                    )
                if not jd_kw.all_keywords:
                    return SkillResult(
                        success=False,
                        message="无法从JD中提取关键词，且 LLM 匹配不可用。请确保JD包含技术要求、岗位职责等具体内容。",
                    )

                match_result = ResumeJDMatcher.match(resume_kw, jd_kw)

            html_report = MatchVisualizer.generate(
                match_result,
                resume_name=display_name,
                jd_title=display_jd,
            )

            # ---- 第6步: 生成文本摘要 ----
            text_summary = self._generate_text_summary(match_result, display_name, display_jd)

            return SkillResult(
                success=True,
                data={
                    "overall_score": match_result.overall_score,
                    "score_level": match_result.score_level,
                    "matched_keywords": match_result.matched_keywords,
                    "unmatched_keywords": match_result.unmatched_jd_keywords,
                    "tech_match_score": match_result.tech_match_score,
                    "soft_skill_score": match_result.soft_skill_score,
                    "education_match": match_result.education_match,
                    "experience_match": match_result.experience_match,
                    "category_scores": match_result.category_scores,
                    "resume_highlights": match_result.resume_highlights,
                    "suggestions": match_result.suggestions,
                    "html_report": html_report,
                },
                message=text_summary,
                metadata={
                    "resume_name": display_name,
                    "jd_title": display_jd,
                    "resume_kw_count": match_result.total_resume_keywords,
                    "jd_kw_count": match_result.total_jd_keywords,
                    "matched_count": match_result.matched_count,
                },
            )

        except Exception as e:
            traceback.print_exc()
            return SkillResult(success=False, message=f"匹配分析失败: {str(e)}")

    def _generate_text_summary(
        self, mr: MatchResult, resume_name: str, jd_title: str
    ) -> str:
        """生成文本摘要"""
        level_icon = {"极高": "🏆", "高": "🎯", "中等": "📌", "较低": "⚠️", "低": "❌"}

        lines = [
            f"# 📊 {resume_name} 与「{jd_title}」匹配度分析报告",
            "",
            f"## 综合评分: {mr.overall_score} 分 — {level_icon.get(mr.score_level, '')} {mr.score_level}匹配",
            "",
            f"### 核心数据",
            f"- JD关键词总数: {mr.total_jd_keywords} 个",
            f"- 简历匹配关键词: {mr.matched_count} 个",
            f"- 简历缺失关键词: {len(mr.unmatched_jd_keywords)} 个",
            f"- 技术栈匹配度: {mr.tech_match_score}%",
            f"- 软技能匹配度: {mr.soft_skill_score}%",
            f"- 学历匹配: {'✅ 满足' if mr.education_match else '❌ 不满足'}",
            f"- 经验年限: {'✅ 满足' if mr.experience_match else '❌ 不满足'}",
        ]

        if mr.matched_keywords:
            lines.append(f"\n### ✅ 匹配关键词 ({mr.matched_count}个)")
            lines.append("，".join(mr.matched_keywords[:20]))
            if mr.matched_count > 20:
                lines.append(f"... 还有 {mr.matched_count - 20} 个")

        if mr.unmatched_jd_keywords:
            lines.append(f"\n### ⚠️ 缺失关键词 ({len(mr.unmatched_jd_keywords)}个)")
            lines.append("，".join(mr.unmatched_jd_keywords[:20]))
            if len(mr.unmatched_jd_keywords) > 20:
                lines.append(f"... 还有 {len(mr.unmatched_jd_keywords) - 20} 个")

        if mr.suggestions:
            lines.append(f"\n### 📝 改进建议")
            for i, s in enumerate(mr.suggestions, 1):
                lines.append(f"{i}. {s}")

        lines.append(f"\n> 详细可视化报告请查看 HTML 输出。")

        return "\n".join(lines)

    async def execute_ocr(
        self,
        jd_text: str = "",
        ocr_text: str = "",
        jd_title: str = "",
        resume_name: str = "",
        **kwargs,
    ) -> SkillResult:
        """
        OCR 模式匹配：从 JD 提取关键词 → 在 OCR 简历文本中搜索评分。

        适用于 PDF 简历 → 图片 → OCR 文字识别后的场景。

        参数:
          - jd_text: JD 文本内容（必填）
          - ocr_text: OCR 识别的简历文本（必填）
          - jd_title: JD 岗位名称（选填）
          - resume_name: 简历候选人姓名（选填）
        """
        try:
            # ---- 校验输入 ----
            if not jd_text or len(jd_text.strip()) < 20:
                return SkillResult(
                    success=False,
                    message="JD 内容太少，无法分析。请提供完整的岗位描述。",
                )

            if not ocr_text or len(ocr_text.strip()) < 30:
                return SkillResult(
                    success=False,
                    message="OCR 识别出的简历内容太少，无法分析。请确保 PDF 清晰可读。",
                )

            # ---- 第1步: 从 JD 提取关键词 ----
            print("[Matcher-OCR] 从 JD 提取关键词...")
            try:
                cleaned_jd = JDTextCleaner.clean(jd_text.strip())
                jd_sections = JDSectionSplitter.split(cleaned_jd)
                jd_result: JDParsedResult = JDExtractor.extract(cleaned_jd, jd_sections)
            except Exception as e:
                print(f"[Matcher-OCR] JD 解析失败({e})，使用原始文本")
                jd_result = JDParsedResult()

            display_jd = jd_title or jd_result.job_title or "目标岗位"
            display_name = resume_name or "候选人简历"

            # 提取 JD 关键词
            if jd_result.requirements or jd_result.responsibilities:
                jd_kw = KeywordExtractor.extract_from_jd(
                    {
                        "job_title": jd_result.job_title,
                        "requirements": jd_result.requirements,
                        "responsibilities": jd_result.responsibilities,
                        "education": jd_result.education,
                        "experience": jd_result.experience,
                    },
                    jd_text=jd_text.strip(),
                )
            else:
                jd_kw = KeywordExtractor.extract_from_jd_text(jd_text.strip())

            if not jd_kw.all_keywords:
                return SkillResult(
                    success=False,
                    message="无法从 JD 中提取关键词。请确保 JD 包含技术要求、岗位职责等具体内容。",
                )

            print(
                f"[Matcher-OCR] JD 提取到 {len(jd_kw.all_keywords)} 个关键词 "
                f"(技术: {len(jd_kw.tech_keywords)}, 软技能: {len(jd_kw.soft_skills)})"
            )

            # ---- 第2步: OCR 文本关键词搜索评分 ----
            print(f"[Matcher-OCR] 在 OCR 文本（{len(ocr_text)} 字符）中搜索关键词...")
            match_result: MatchResult = OCRKeywordMatcher.match(
                jd_keywords=jd_kw,
                ocr_text=ocr_text.strip(),
                jd_title=display_jd,
                resume_name=display_name,
            )

            # ---- 第3步: 生成可视化报告 ----
            html_report = MatchVisualizer.generate(
                match_result,
                resume_name=display_name,
                jd_title=display_jd,
            )

            # ---- 第4步: 生成文本摘要 ----
            text_summary = self._generate_text_summary(match_result, display_name, display_jd)

            print(
                f"[Matcher-OCR] 匹配完成: 综合评分 {match_result.overall_score} "
                f"({match_result.score_level}), "
                f"匹配 {match_result.matched_count}/{match_result.total_jd_keywords} 个关键词"
            )

            return SkillResult(
                success=True,
                data={
                    "overall_score": match_result.overall_score,
                    "score_level": match_result.score_level,
                    "matched_keywords": match_result.matched_keywords,
                    "unmatched_keywords": match_result.unmatched_jd_keywords,
                    "tech_match_score": match_result.tech_match_score,
                    "soft_skill_score": match_result.soft_skill_score,
                    "education_match": match_result.education_match,
                    "experience_match": match_result.experience_match,
                    "category_scores": match_result.category_scores,
                    "resume_highlights": match_result.resume_highlights,
                    "suggestions": match_result.suggestions,
                    "html_report": html_report,
                },
                message=text_summary,
                metadata={
                    "resume_name": display_name,
                    "jd_title": display_jd,
                    "jd_kw_count": match_result.total_jd_keywords,
                    "matched_count": match_result.matched_count,
                    "mode": "ocr",
                },
            )

        except Exception as e:
            traceback.print_exc()
            return SkillResult(success=False, message=f"OCR 匹配分析失败: {str(e)}")

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resume_text": {
                            "type": "string",
                            "description": "完整的简历文本内容",
                        },
                        "jd_text": {
                            "type": "string",
                            "description": "完整的岗位JD文本内容",
                        },
                        "resume_name": {
                            "type": "string",
                            "description": "简历候选人姓名（选填）",
                        },
                        "jd_title": {
                            "type": "string",
                            "description": "JD岗位名称（选填）",
                        },
                    },
                    "required": ["resume_text", "jd_text"],
                },
            },
        }

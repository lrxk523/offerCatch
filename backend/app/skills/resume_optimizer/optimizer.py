"""简历优化引擎 - 融合深度审计 + STAR 改写 + 7B 模型兼容"""

import json
import os
import re
from typing import List, Optional
from openai import OpenAI

from .parser import ResumeData


OPTIMIZE_SYSTEM_PROMPT = """你是资深简历审计官，必须对简历进行实质性改写，绝对不能照搬原文！

## 核心原则：优化后的每条 bullet 必须与原文结构和表达完全不同！

### ❌ 错误示范（零优化，简单复制+加占位符）：
原文："参与基于 SpringBoot 的商城项目开发，独立负责商品检索模块"
❌ 优化后："参与基于 SpringBoot 的商城项目开发，独立负责商品检索模块 [X%]"
（只是复制原文加了个 [X%]，根本不算优化！）

❌ 优化后："主导基于 SpringBoot 的商城项目开发，独立负责商品检索模块，最终提升系统性能 [X%]"
（只改了一个动词+加了占位符，整体结构和原文一样，不算优化！）

### ✅ 正确示范（实质性改写，结构和表达完全不同）：
原文："参与基于 SpringBoot 的商城项目开发，独立负责商品检索模块"
✅ 优化后："主导线上商城核心检索模块的架构设计与落地，基于 SpringBoot + MyBatis 构建商品全文检索引擎，支撑 [X万+] SKU 的毫秒级查询 [性能指标待补]"

原文："熟练使用 Git 进行代码版本管理、迭代开发与持续优化"
✅ 优化后："搭建 Git 分支管理规范与 CI/CD 流程，推动团队从手动部署到自动化发布，发布效率提升 [X%]，线上故障回滚时间缩短至 [X分钟]"

原文："构建私有知识库，实现基于知识库的精准问答"
✅ 优化后："设计并搭建私有知识库体系，整合 [X篇] 文档与 FAQ，基于向量检索实现精准问答，知识命中率 [X%]，覆盖 [X%] 用户常见问题"

## 改写规则

1. **结构重组**：不要保留原文的句式结构，必须用全新的表达方式重写
2. **强动词替换**："负责/参与/协助/完成" → "主导/设计/重构/落地/推动/搭建"
3. **量化优先**：每条 bullet 必须包含"动作 + 产物 + 结果"，补充具体的业务指标占位符
4. **STAR 公式**：为了[目标/挑战]，我[关键动作]，最终[可量化/可感知结果]
5. **产物导向**：写清交付了什么系统/平台/工具/流程 → 谁在用 → 带来什么变化
6. **不编造具体数字**：但必须用量化占位符引导用户补充，如 [日活X万] [响应时间降至Xms]
7. **项目先有上下文**：每段项目必须先用一句话说清系统定位和服务对象

## 再次强调
优化后的每条 bullet 都必须比原文更具体、更有冲击力、更能量化。
如果优化后和原文几乎一样（只是换了个动词或加了个 [X%]），说明你没有真正优化！

## 输出格式

严格返回以下 JSON，不要多余文字：

{
  "verdict": "一句话结论：最致命问题 + 最大亮点",
  "self_evaluation": "优化后自我评价(80-150字，公式：定位+年限+核心领域+最强成果)",
  "work_experience": [
    {"company":"原文","position":"原文","start":"原文","end":"原文","responsibilities":["实质性改写后的bullet，结构和表达必须与原文完全不同"]}
  ],
  "project_experience": [
    {"name":"原文","role":"原文","start":"原文","end":"原文","description":"1-2句项目背景(系统定位+服务对象+业务问题)","highlights":["实质性改写后的亮点，结构和表达必须与原文完全不同"]}
  ],
  "optimization_summary": "3-5条具体建议，每条格式：问题→影响→修改建议。如有红旗风险请明确标注。"
}"""


class ResumeOptimizer:
    """简历优化器"""

    def __init__(self):
        self._client = None
        self._model = None

    @property
    def client(self):
        if self._client is None:
            from app.core.config import create_openai_client
            self._client, self._model = create_openai_client("resume")
        return self._client

    def optimize(self, resume: ResumeData, target_position: str = "", _attempt: int = 0) -> dict:
        user_prompt = self._build_optimize_prompt(resume, target_position)

        # 重试时添加强烈警告
        if _attempt > 0:
            user_prompt = (
                "⚠️ 上一次优化结果与原文几乎完全相同，只是简单复制了原文！\n"
                "请务必对每条内容进行实质性改写——改变句式结构、补充业务影响、使用强动词！\n"
                "不要只是替换一个动词然后加 [X%] 占位符！\n\n" + user_prompt
            )

        temperature = 0.7 if _attempt == 0 else 0.9

        try:
            response = self.client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": OPTIMIZE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4096,
                temperature=temperature,
            )
            result_text = (response.choices[0].message.content or "").strip()
            optimized = self._parse_json_response(result_text, resume)
            optimized.setdefault("original", resume.to_dict())

            # 检查优化结果是否与原文过于相似，最多重试1次
            if _attempt == 0 and self._check_too_similar(resume, optimized):
                print("[Optimizer] 优化结果与原文相似度过高，正在重试(提高温度)...")
                return self.optimize(resume, target_position, _attempt=1)

            return optimized
        except Exception as e:
            print(f"[Optimizer] LLM 调用失败: {e}")
            return self._fallback_result(resume)

    def _check_too_similar(self, resume: ResumeData, optimized: dict, threshold: float = 0.4) -> bool:
        """检查优化结果是否与原文过于相似"""
        total, similar = 0, 0
        for i, opt_exp in enumerate(optimized.get("work_experience", [])):
            orig_exp = resume.work_experience[i] if i < len(resume.work_experience) else {}
            orig_resp = orig_exp.get("responsibilities", [])
            opt_resp = opt_exp.get("responsibilities", [])
            for j, opt in enumerate(opt_resp):
                if j < len(orig_resp) and orig_resp[j]:
                    total += 1
                    if self._is_near_duplicate(opt, orig_resp[j]):
                        similar += 1

        for i, opt_proj in enumerate(optimized.get("project_experience", [])):
            orig_proj = resume.project_experience[i] if i < len(resume.project_experience) else {}
            orig_hl = orig_proj.get("highlights", [])
            opt_hl = opt_proj.get("highlights", [])
            for j, opt in enumerate(opt_hl):
                if j < len(orig_hl) and orig_hl[j]:
                    total += 1
                    if self._is_near_duplicate(opt, orig_hl[j]):
                        similar += 1

        if total == 0:
            return False
        ratio = similar / total
        print(f"[Optimizer] 相似度检查: {similar}/{total} = {ratio:.0%}")
        return ratio > threshold

    def _build_optimize_prompt(self, resume: ResumeData, target: str) -> str:
        parts = []
        if target:
            parts.append(f"【目标岗位】{target}")
            parts.append("请围绕此岗位定向优化：突出相关经验、用目标岗位常用关键词。\n")

        parts.append("## 简历原文\n")
        if resume.name:
            parts.append(f"姓名: {resume.name}")

        if resume.self_evaluation:
            parts.append(f"\n自我评价:\n{resume.self_evaluation}")

        # 工作经历
        if resume.work_experience:
            parts.append(f"\n--- 工作经历 ({len(resume.work_experience)}段) ---")
            for i, exp in enumerate(resume.work_experience, 1):
                parts.append(f"\n[{i}] {exp.get('company', '')} | {exp.get('position', '')}")
                parts.append(f"时间: {exp.get('start', '')} - {exp.get('end', '')}")
                for r in exp.get("responsibilities", []):
                    parts.append(f"  - {r}")

        # 项目经历
        if resume.project_experience:
            parts.append(f"\n--- 项目经历 ({len(resume.project_experience)}个) ---")
            for i, proj in enumerate(resume.project_experience, 1):
                parts.append(f"\n[{i}] {proj.get('name', '')}")
                if proj.get("role"):
                    parts.append(f"角色: {proj['role']}")
                if proj.get("start") or proj.get("end"):
                    parts.append(f"时间: {proj.get('start', '')} - {proj.get('end', '')}")
                if proj.get("description"):
                    parts.append(f"描述: {proj['description']}")
                for h in proj.get("highlights", []):
                    parts.append(f"  - {h}")

        if resume.skills:
            parts.append(f"\n技能: {', '.join(resume.skills)}")

        if resume.education:
            edu = resume.education[0]
            parts.append(f"学历: {edu.get('school', '')} {edu.get('degree', '')} {edu.get('major', '')}")

        parts.append("\n请按系统指令优化以上简历，直接返回 JSON。")
        return "\n".join(parts)

    def _parse_json_response(self, text: str, resume: ResumeData) -> dict:
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            print(f"[Optimizer] 未能提取 JSON: {text[:200]}")
            return self._fallback_result(resume)

        try:
            result = json.loads(json_match.group())
        except json.JSONDecodeError:
            cleaned = re.sub(r',\s*}', '}', json_match.group())
            cleaned = re.sub(r',\s*]', ']', cleaned)
            try:
                result = json.loads(cleaned)
            except json.JSONDecodeError:
                print(f"[Optimizer] JSON 解析失败: {json_match.group()[:200]}")
                return self._fallback_result(resume)

        # 补齐字段
        result.setdefault("verdict", "")
        result.setdefault("self_evaluation", resume.self_evaluation or "")
        result.setdefault("optimization_summary", "")

        optimized_work = result.get("work_experience", [])
        result["work_experience"] = (
            self._align_work(optimized_work, resume.work_experience)
            if optimized_work else list(resume.work_experience)
        )

        optimized_proj = result.get("project_experience", [])
        result["project_experience"] = (
            self._align_project(optimized_proj, resume.project_experience)
            if optimized_proj else list(resume.project_experience)
        )

        return result

    def _align_work(self, optimized: list, original: list) -> list:
        aligned = []
        for i, orig in enumerate(original):
            if i < len(optimized):
                item = dict(orig)
                opt = optimized[i]
                item["responsibilities"] = opt.get("responsibilities", orig.get("responsibilities", []))
                aligned.append(item)
            else:
                aligned.append(dict(orig))
        return aligned

    def _align_project(self, optimized: list, original: list) -> list:
        aligned = []
        for i, orig in enumerate(original):
            if i < len(optimized):
                item = dict(orig)
                opt = optimized[i]
                item["description"] = opt.get("description", orig.get("description", ""))
                item["highlights"] = opt.get("highlights", orig.get("highlights", []))
                aligned.append(item)
            else:
                aligned.append(dict(orig))
        return aligned

    def post_process(self, resume: ResumeData, optimized: dict) -> dict:
        """后处理：检测与原文过于相似的 bullet 并自动增强"""
        true_orig = optimized.pop("_true_original", None)

        # 确定用于对比的"原文"数据源
        orig_work = true_orig["work_experience"] if true_orig else resume.work_experience
        orig_proj = true_orig["project_experience"] if true_orig else resume.project_experience

        auto_enhanced_count = 0

        # 处理工作经历
        for i, opt_exp in enumerate(optimized.get("work_experience", [])):
            orig_exp = orig_work[i] if i < len(orig_work) else {}
            orig_resp = orig_exp.get("responsibilities", [])
            opt_resp = opt_exp.get("responsibilities", [])
            enhanced_resp = []
            for j, opt in enumerate(opt_resp):
                orig = orig_resp[j] if j < len(orig_resp) else ""
                if orig and self._is_near_duplicate(opt, orig):
                    enhanced_resp.append(self._auto_enhance(opt, orig))
                    auto_enhanced_count += 1
                else:
                    enhanced_resp.append(opt)
            opt_exp["responsibilities"] = enhanced_resp

        # 处理项目经历
        for i, opt_proj in enumerate(optimized.get("project_experience", [])):
            orig_p = orig_proj[i] if i < len(orig_proj) else {}
            orig_hl = orig_p.get("highlights", [])
            opt_hl = opt_proj.get("highlights", [])
            enhanced_hl = []
            for j, opt in enumerate(opt_hl):
                orig = orig_hl[j] if j < len(orig_hl) else ""
                if orig and self._is_near_duplicate(opt, orig):
                    enhanced_hl.append(self._auto_enhance(opt, orig))
                    auto_enhanced_count += 1
                else:
                    enhanced_hl.append(opt)
            opt_proj["highlights"] = enhanced_hl

            # 项目描述增强
            orig_desc = orig_p.get("description", "")
            opt_desc = opt_proj.get("description", "")
            if not opt_desc or (orig_desc and self._is_near_duplicate(opt_desc, orig_desc)):
                name = opt_proj.get("name", orig_p.get("name", ""))
                if name:
                    opt_proj["description"] = f"{name}：[请补充系统定位和服务对象]"

        if auto_enhanced_count > 0:
            print(f"[Optimizer] 自动增强 {auto_enhanced_count} 条相似 bullet")
            optimized["_auto_enhanced_count"] = auto_enhanced_count

        # 保存真正原文供 _format_output 使用
        if true_orig:
            optimized["_true_original"] = true_orig

        return optimized

    @staticmethod
    def _is_near_duplicate(text_a: str, text_b: str, threshold: float = 0.75) -> bool:
        """判断两条文本是否近似重复"""
        a, b = text_a.strip(), text_b.strip()
        if not a or not b:
            return False
        if a == b:
            return True
        if len(a) < 8 or len(b) < 8:
            return a == b
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        common = sum(1 for c in shorter if c in longer)
        ratio = common / max(len(longer), 1)
        return ratio >= threshold

    @staticmethod
    def _auto_enhance(text: str, original: str = "") -> str:
        """当 LLM 照搬原文时，自动增强弱表达（基于正则的句式重组）"""
        result = text

        # Phase 1: 正则句式重组（比简单替换更有效）
        restructuring = [
            (r'参与(.{2,25})(的|等)(.{2,15})(模块|功能|组件|系统|平台)(.{0,6})(开发|实现|设计)',
             r'主导\3\4的架构设计与落地，基于相关技术栈实现核心\4能力，支撑[业务场景待补]'),
            (r'负责(.{2,25})(的|等)(.{2,15})(模块|功能|组件|系统|平台)(.{0,6})(开发|实现|设计)',
             r'主导\3\4的设计与\6，落地核心业务能力，服务于[用户规模待补]'),
            (r'熟练使用(.{2,20})进行(.{2,20})',
             r'深度运用\1搭建\2体系，推动团队效率提升[量化待补]'),
            (r'配合团队完成(.{2,30})',
             r'推动团队交付\1，确保项目按时上线与质量达标[量化待补]'),
            (r'使用(.{2,20})(实现|完成|开发)(了?)(.{2,20})',
             r'基于\1构建\4系统/能力，\2[具体效果待补]'),
        ]
        for pattern, replacement in restructuring:
            new_result = re.sub(pattern, replacement, result, count=1)
            if new_result != result:
                result = new_result
                break
        else:
            # Phase 2: 简单动词替换（正则未匹配时的 fallback）
            word_replacements = [
                ("参与", "主导"),
                ("负责", "主导"),
                ("协助", "推动落地"),
                ("配合团队完成", "推动团队交付"),
                ("完成了", "设计并交付了"),
                ("熟练使用", "深度运用"),
                ("使用", "基于"),
                ("实现了", "独立实现了"),
                ("完成", "落地完成"),
            ]
            for weak, strong in word_replacements:
                if weak in result:
                    result = result.replace(weak, strong, 1)
                    break

        # Phase 3: 清理无效占位符并添加量化引导
        result = result.replace('[X%]', '[量化数据待补：如提升X%]')
        result = result.replace('[量化数据待补][量化数据待补：如提升X%]', '[量化数据待补：如提升X%]')

        # Phase 4: 确保有业务影响
        has_impact = any(kw in result for kw in ['提升', '降低', '减少', '增加', '优化',
                                                   '支撑', '服务', '实现', '落地', '交付'])
        if not has_impact:
            result += '，支撑[业务场景待补]'

        # Phase 5: 确保含量化占位符
        has_quant = any(kw in result for kw in ['量化', '%', '倍', '万', '千'])
        if not has_quant:
            result += ' [量化数据待补]'

        return result

    def _fallback_result(self, resume: ResumeData) -> dict:
        return {
            "verdict": "优化服务暂时不可用",
            "self_evaluation": resume.self_evaluation or "",
            "work_experience": list(resume.work_experience),
            "project_experience": list(resume.project_experience),
            "optimization_summary": "抱歉，优化服务暂时不可用，已保留原文。",
        }

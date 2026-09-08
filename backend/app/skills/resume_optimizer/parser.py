"""简历文本解析器 - 从原始文本中提取结构化简历信息"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ResumeData:
    """结构化简历数据"""
    name: str = ""                      # 姓名
    phone: str = ""                     # 电话
    email: str = ""                     # 邮箱
    age: str = ""                       # 年龄
    current_location: str = ""          # 现居城市
    job_objective: str = ""             # 求职意向
    desired_salary: str = ""            # 期望薪资

    education: List[dict] = field(default_factory=list)
    # [{school, degree, major, start, end, description}]

    work_experience: List[dict] = field(default_factory=list)
    # [{company, position, start, end, responsibilities: [str]}]

    project_experience: List[dict] = field(default_factory=list)
    # [{name, role, start, end, description, highlights: [str]}]

    skills: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    self_evaluation: str = ""           # 自我评价

    raw_text: str = ""                  # 原始文本

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "age": self.age,
            "current_location": self.current_location,
            "job_objective": self.job_objective,
            "desired_salary": self.desired_salary,
            "education": self.education,
            "work_experience": self.work_experience,
            "project_experience": self.project_experience,
            "skills": self.skills,
            "certifications": self.certifications,
            "self_evaluation": self.self_evaluation,
        }

    @classmethod
    def from_llm_dict(cls, data: dict, raw_text: str = "") -> "ResumeData":
        """从 LLM 返回的字典构建 ResumeData"""
        resume = cls(raw_text=raw_text)
        resume.name = str(data.get("name", "")).strip()
        resume.phone = str(data.get("phone", "")).strip()
        resume.email = str(data.get("email", "")).strip()
        resume.age = str(data.get("age", "")).strip()
        resume.current_location = str(data.get("current_location", "")).strip()
        resume.job_objective = str(data.get("job_objective", "")).strip()
        resume.desired_salary = str(data.get("desired_salary", "")).strip()
        resume.self_evaluation = str(data.get("self_evaluation", "")).strip()

        # 教育经历
        edu_list = data.get("education", [])
        if isinstance(edu_list, list):
            resume.education = [{k: str(v) if v else "" for k, v in item.items()} for item in edu_list if isinstance(item, dict)]

        # 工作经历
        work_list = data.get("work_experience", [])
        if isinstance(work_list, list):
            for item in work_list:
                if isinstance(item, dict):
                    entry = {k: str(v) if k != "responsibilities" else v for k, v in item.items()}
                    # 确保 responsibilities 是列表
                    if "responsibilities" in entry and isinstance(entry["responsibilities"], str):
                        entry["responsibilities"] = [s.strip() for s in entry["responsibilities"].split("\n") if s.strip()]
                    resume.work_experience.append(entry)

        # 项目经历
        proj_list = data.get("project_experience", [])
        if isinstance(proj_list, list):
            for item in proj_list:
                if isinstance(item, dict):
                    entry = {k: str(v) if k != "highlights" else v for k, v in item.items()}
                    # 确保 highlights 是列表
                    if "highlights" in entry and isinstance(entry["highlights"], str):
                        entry["highlights"] = [s.strip() for s in entry["highlights"].split("\n") if s.strip()]
                    resume.project_experience.append(entry)

        # 技能
        skills = data.get("skills", [])
        if isinstance(skills, list):
            resume.skills = [str(s).strip() for s in skills if s]
        elif isinstance(skills, str):
            resume.skills = [s.strip() for s in re.split(r"[,，、；;]", skills) if s.strip()]

        # 证书
        certs = data.get("certifications", [])
        if isinstance(certs, list):
            resume.certifications = [str(c).strip() for c in certs if c]
        elif isinstance(certs, str):
            resume.certifications = [c.strip() for c in re.split(r"[,，、；;]", certs) if c.strip()]

        return resume


RESUME_PARSE_PROMPT = """你是专业的简历信息提取专家。请从以下简历文本中提取结构化信息。

## 提取规则
1. 姓名、电话、邮箱精确匹配原文
2. 教育经历：提取学校、学历、专业、起止时间，description 填写论文/课题/荣誉等补充信息
3. 工作经历：提取公司名、职位、起止时间，responsibilities 拆分为独立的 bullet point 列表（每条用简短语句描述一条核心职责或成果）
4. 项目经历：提取项目名、角色、起止时间，description 用1-2句话描述项目背景，highlights 拆分为独立 bullet point
5. 技能：列出所有技术栈和专业技能
6. 自我评价：保留原文自我评价段落
7. 某信息缺失则对应字段留空字符串 ""

## 输出格式
严格返回 JSON，不要多余文字：

{
  "name": "",
  "phone": "",
  "email": "",
  "age": "",
  "current_location": "",
  "job_objective": "",
  "desired_salary": "",
  "education": [
    {"school": "", "degree": "", "major": "", "start": "", "end": "", "description": ""}
  ],
  "work_experience": [
    {"company": "", "position": "", "start": "", "end": "", "responsibilities": [""]}
  ],
  "project_experience": [
    {"name": "", "role": "", "start": "", "end": "", "description": "", "highlights": [""]}
  ],
  "skills": [""],
  "certifications": [""],
  "self_evaluation": ""
}"""


# ---- 解析+优化 合并 Prompt (一次 LLM 调用完成两步) ----
PARSE_AND_OPTIMIZE_PROMPT = """你是资深简历审计官，需要同时完成「信息提取」和「审计优化」两步。

## ⚠️ 最重要的规则
parsed 中的文本必须与简历原文逐字一致！
- responsibilities 和 highlights 必须照抄原文，一个字都不要改、不要加、不要删！
- 不要在 parsed 中做任何优化、改写、重组或添加占位符！
- parsed 是"存档副本"，优化工作只在第二部分进行！
- 如果你在 parsed 中已经改写了，那对比就毫无意义，用户会觉得优化没用！

## 第一部分：信息提取（存入 parsed 字段）
1. 姓名、电话、邮箱精确匹配原文
2. 教育经历：提取学校、学历、专业、起止时间
3. 工作经历：提取公司名、职位、起止时间，responsibilities 照抄原文 bullet point
4. 项目经历：提取项目名、角色、起止时间，highlights 照抄原文 bullet point，description 照抄原文
5. 技能：列出所有技术栈
6. 某信息缺失则留空 ""
7. 再次强调：parsed 中所有文本字段必须与简历原文逐字一致！

## 第二部分：审计优化（存入外层 work_experience / project_experience）
你必须对原文进行实质性改写，绝对不能只是复制原文然后加 [X%] ！

### 改写规则（每条必须遵守）：
1. **结构重组**：不要保留原文的句式结构，必须用全新的表达方式重写
2. **强动词替换**："负责/参与/协助/完成" → "主导/设计/重构/落地/推动/搭建"
3. **量化注入**：补充具体的业务指标占位符，如 [日活X万] [响应时间降至Xms] [覆盖X%场景]
4. **STAR 公式**：为了[目标/挑战]，我[关键动作]，最终[可量化/可感知结果]
5. **产物导向**：写清交付了什么系统/能力 → 谁在用 → 带来什么变化
6. **项目描述**：补充系统定位和服务对象（原文如果没有则推断并标注待确认）
7. **不编造具体数字**：但必须用量化占位符引导用户补充

### ❌ 错误示范（零优化，简单复制+加占位符）：
原文："参与基于 SpringBoot 的线上商城项目开发，独立负责商品检索、商品管理、移动支付模块"
❌ 优化后："参与基于 SpringBoot 的线上商城项目开发，独立负责商品检索、商品管理、移动支付模块 [X%]"
（只是复制原文加了个 [X%]，根本不算优化！）

❌ 优化后："主导基于 SpringBoot 的线上商城项目开发，独立负责商品检索、商品管理、移动支付模块，最终提升系统性能 [X%]"
（只改了一个动词+加了占位符，整体结构和原文一样，不算优化！）

### ✅ 正确示范（实质性改写，结构和表达完全不同）：
原文："参与基于 SpringBoot 的线上商城项目开发，独立负责商品检索、商品管理、移动支付模块"
✅ 优化后："主导线上商城三大核心模块（检索/管理/支付）的架构设计与落地，基于 SpringBoot + MyBatis 构建商品检索引擎与支付系统，支撑 [X万+] SKU 查询与 [X千+] 日订单处理 [业务规模待补]"

原文："熟练使用 Git 进行代码版本管理、迭代开发与持续优化"
✅ 优化后："搭建 Git 分支管理规范与 CI/CD 流程，推动团队从手动部署到自动化发布，发布效率提升 [X%]，线上故障回滚时间缩短至 [X分钟]"

原文："构建私有知识库，实现基于知识库的精准问答"
✅ 优化后："设计并搭建私有知识库体系，整合 [X篇] 文档与 FAQ，基于向量检索实现精准问答，知识命中率 [X%]，覆盖 [X%] 用户常见问题"

### 再次强调：优化后的每条 bullet 必须——
1. 与原文结构和表达方式完全不同
2. 比原文更具体、更有冲击力
3. 不是简单替换动词+加占位符

## 输出格式
严格返回 JSON，不要多余文字：

{
  "parsed": {
    "name": "", "phone": "", "email": "", "age": "",
    "current_location": "", "job_objective": "", "desired_salary": "",
    "education": [{"school":"", "degree":"", "major":"", "start":"", "end":"", "description":""}],
    "work_experience": [{"company":"", "position":"", "start":"", "end":"", "responsibilities":["照抄原文"]}],
    "project_experience": [{"name":"", "role":"", "start":"", "end":"", "description":"照抄原文", "highlights":["照抄原文"]}],
    "skills": [""], "certifications": [""], "self_evaluation": ""
  },
  "verdict": "一句话结论：最致命问题 + 最大亮点",
  "self_evaluation": "优化后自我评价(80-150字，公式：定位+年限+核心领域+最强成果)",
  "work_experience": [
    {"company":"原文","position":"原文","start":"原文","end":"原文","responsibilities":["实质性改写后的bullet，结构和表达必须与原文完全不同"]}
  ],
  "project_experience": [
    {"name":"原文","role":"原文","start":"原文","end":"原文","description":"1-2句项目背景(系统定位+服务对象+业务问题)","highlights":["实质性改写后的亮点，结构和表达必须与原文完全不同"]}
  ],
  "optimization_summary": "3-5条具体建议，每条格式：问题→影响→修改建议"
}"""


class LLMResumeParser:
    """使用 LLM 解析简历——更准确，支持任意格式"""

    _client = None
    _model = None
    _parse_model = None  # 解析专用小模型

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            from app.core.config import create_openai_client
            # 简历优化模型（大模型，保证优化质量）
            cls._client, cls._model = create_openai_client("resume")
            # 解析只需信息提取，用小模型即可（速度快3-5倍）
            _, cls._parse_model = create_openai_client("parse")
        return cls._client, cls._model, cls._parse_model

    @classmethod
    def parse(cls, text: str, max_chars: int = 16000) -> ResumeData:
        """使用 LLM 从原始文本中提取结构化简历信息（小模型）"""
        truncated = text[:max_chars]

        try:
            client, model, parse_model = cls._get_client()
            response = client.chat.completions.create(
                model=parse_model,
                messages=[
                    {"role": "system", "content": RESUME_PARSE_PROMPT},
                    {"role": "user", "content": f"## 简历文本\n\n{truncated}"},
                ],
                max_tokens=4096,
                temperature=0.1,
            )
            result_text = (response.choices[0].message.content or "").strip()

            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if not json_match:
                raise RuntimeError("LLM 返回中未找到 JSON")

            parsed = json.loads(json_match.group())

            # 清理及修复
            if isinstance(parsed, dict):
                return ResumeData.from_llm_dict(parsed, raw_text=text)

            raise RuntimeError("LLM 返回不是 JSON 对象")

        except Exception as e:
            raise RuntimeError(f"LLM 简历解析失败: {e}")

    @classmethod
    def parse_and_optimize(cls, text: str, target_position: str = "", max_chars: int = 16000, _attempt: int = 0) -> tuple:
        """
        单次 LLM 调用同时完成解析 + 优化，比分两次调用快一倍。

        Returns:
            (ResumeData, optimized_dict) 元组
            optimized_dict 包含 "_true_original" 字段，存储从原文提取的真正原始文本
        """
        truncated = text[:max_chars]

        try:
            client, model, parse_model = cls._get_client()
            user_content = f"## 简历文本\n\n{truncated}"
            if target_position:
                user_content += f"\n\n【目标岗位】{target_position}"

            # 重试时添加强烈警告 + 提高温度
            if _attempt > 0:
                user_content = (
                    "⚠️ 上一次优化结果与原文几乎完全相同，只是简单复制了原文！\n"
                    "请务必对每条内容进行实质性改写——改变句式结构、补充业务影响、使用强动词！\n"
                    "不要只是替换一个动词然后加 [X%] 占位符！\n\n" + user_content
                )

            temperature = 0.6 if _attempt == 0 else 0.85

            response = client.chat.completions.create(
                model=model,  # 合并调用用大模型，保证优化质量
                messages=[
                    {"role": "system", "content": PARSE_AND_OPTIMIZE_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=6144,
                temperature=temperature,
            )
            result_text = (response.choices[0].message.content or "").strip()

            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if not json_match:
                raise RuntimeError("LLM 返回中未找到 JSON")

            parsed = json.loads(json_match.group())

            if not isinstance(parsed, dict):
                raise RuntimeError("LLM 返回不是 JSON 对象")

            # 提取 parsed 子对象构建 ResumeData
            parsed_section = parsed.get("parsed", parsed)  # 兼容：如果 LLM 没分两层
            resume_data = ResumeData.from_llm_dict(parsed_section, raw_text=text)

            # 构建 optimized dict
            optimized = {
                "verdict": parsed.get("verdict", ""),
                "self_evaluation": parsed.get("self_evaluation", ""),
                "work_experience": parsed.get("work_experience", []),
                "project_experience": parsed.get("project_experience", []),
                "optimization_summary": parsed.get("optimization_summary", ""),
            }

            # 用正则解析器提取真正的原文，用于对比展示
            try:
                true_original = ResumeParser._do_parse(text)
                optimized["_true_original"] = {
                    "work_experience": true_original.work_experience,
                    "project_experience": true_original.project_experience,
                }
            except Exception:
                pass  # 正则解析失败不影响主流程

            # 检查优化结果是否与原文过于相似，最多重试1次
            if _attempt == 0 and cls._check_too_similar(resume_data, optimized):
                print("[Parser] 优化结果与原文相似度过高，正在重试(提高温度)...")
                return cls.parse_and_optimize(text, target_position, max_chars, _attempt=1)

            return resume_data, optimized

        except Exception as e:
            raise RuntimeError(f"LLM 解析+优化失败: {e}")

    @classmethod
    def _check_too_similar(cls, resume: ResumeData, optimized: dict, threshold: float = 0.4) -> bool:
        """检查优化结果是否与原文过于相似（超过 threshold 比例的 bullet 相似）"""
        from .optimizer import ResumeOptimizer
        total, similar = 0, 0

        # 检查工作经历
        for i, opt_exp in enumerate(optimized.get("work_experience", [])):
            orig_exp = resume.work_experience[i] if i < len(resume.work_experience) else {}
            # 优先使用 true_original
            true_orig = optimized.get("_true_original", {}).get("work_experience", [])
            if i < len(true_orig):
                orig_resp = true_orig[i].get("responsibilities", [])
            else:
                orig_resp = orig_exp.get("responsibilities", [])

            opt_resp = opt_exp.get("responsibilities", [])
            for j, opt in enumerate(opt_resp):
                if j < len(orig_resp) and orig_resp[j]:
                    total += 1
                    if ResumeOptimizer._is_near_duplicate(opt, orig_resp[j]):
                        similar += 1

        # 检查项目经历
        for i, opt_proj in enumerate(optimized.get("project_experience", [])):
            true_orig = optimized.get("_true_original", {}).get("project_experience", [])
            if i < len(true_orig):
                orig_hl = true_orig[i].get("highlights", [])
            else:
                orig_proj = resume.project_experience[i] if i < len(resume.project_experience) else {}
                orig_hl = orig_proj.get("highlights", [])

            opt_hl = opt_proj.get("highlights", [])
            for j, opt in enumerate(opt_hl):
                if j < len(orig_hl) and orig_hl[j]:
                    total += 1
                    if ResumeOptimizer._is_near_duplicate(opt, orig_hl[j]):
                        similar += 1

        if total == 0:
            return False
        ratio = similar / total
        print(f"[Parser] 相似度检查: {similar}/{total} = {ratio:.0%}")
        return ratio > threshold


class ResumeParser:
    """简历解析器（默认使用 LLM，正则作为 fallback）"""

    # ---- 章节标题关键词 ----
    PERSONAL_HEADERS = ["个人信息", "基本信息", "个人资料"]
    OBJECTIVE_HEADERS = ["求职意向", "期望职位", "期望岗位", "求职目标"]
    EDUCATION_HEADERS = ["教育经历", "教育背景", "学历信息"]
    WORK_HEADERS = ["工作经历", "工作经验", "工作履历", "职业经历", "实习经历"]
    PROJECT_HEADERS = ["项目经历", "项目经验", "项目背景"]
    SKILLS_HEADERS = ["专业技能", "技能", "技术栈", "能力", "掌握技能"]
    CERT_HEADERS = ["证书", "资格证书", "语言能力", "获奖", "荣誉"]
    SELF_EVAL_HEADERS = ["自我评价", "个人评价", "自我介绍", "个人优势"]

    @classmethod
    def parse(cls, text: str) -> ResumeData:
        """从原始文本中解析简历数据——优先使用 LLM，失败时 fallback 正则"""
        import traceback as tb

        # 先尝试 LLM 解析
        try:
            return LLMResumeParser.parse(text)
        except Exception as llm_err:
            print(f"[Parser] LLM 解析失败({llm_err})，使用正则 fallback")

        # 正则 fallback
        try:
            return cls._do_parse(text)
        except Exception as e:
            tb.print_exc()
            raise RuntimeError(f"[Parser.{tb.extract_tb(e.__traceback__)[-1].name}] {e}") from e

    @classmethod
    def _do_parse(cls, text: str) -> ResumeData:
        data = ResumeData(raw_text=text)

        # 先提取个人信息（姓名、电话、邮箱等，通常在简历开头）
        try:
            cls._extract_personal_info(text, data)
        except Exception:
            pass

        # 分章节
        try:
            sections = cls._split_sections(text)
        except Exception:
            sections = [("全文", text)]

        for section_title, section_text in sections:
            if section_title is None or section_text is None:
                continue
            title_clean = section_title.replace(" ", "")
            try:
                if any(h in title_clean for h in cls.EDUCATION_HEADERS):
                    data.education = cls._extract_education(section_text)
                elif any(h in title_clean for h in cls.WORK_HEADERS):
                    data.work_experience = cls._extract_work_experience(section_text)
                elif any(h in title_clean for h in cls.PROJECT_HEADERS):
                    data.project_experience = cls._extract_project_experience(section_text)
                elif any(h in title_clean for h in cls.SKILLS_HEADERS):
                    data.skills = cls._extract_skills(section_text)
                elif any(h in title_clean for h in cls.CERT_HEADERS):
                    data.certifications = cls._extract_items(section_text)
                elif any(h in title_clean for h in cls.OBJECTIVE_HEADERS):
                    cls._extract_objective(section_text, data)
                elif any(h in title_clean for h in cls.SELF_EVAL_HEADERS):
                    if section_text:
                        data.self_evaluation = section_text.strip()
            except Exception:
                # 单个 section 解析失败不影响其他 section
                pass

        # 兜底：如果没有解析到教育/工作，尝试全文扫描
        if not data.education:
            try:
                data.education = cls._find_education_global(text)
            except Exception:
                pass
        if not data.work_experience:
            try:
                data.work_experience = cls._find_work_global(text)
            except Exception:
                pass

        # 如果依然没有技能，从 OCR 文本全局提取
        if not data.skills and len(text) > 50:
            data.skills = cls._extract_skills(text)

        return data

    @classmethod
    def _extract_personal_info(cls, text: str, data: ResumeData):
        """提取个人信息"""
        # 手机号
        phone_match = re.search(r"1[3-9]\d{9}", text)
        if phone_match:
            data.phone = phone_match.group(0)

        # 邮箱
        email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        if email_match:
            data.email = email_match.group(0)

        # 年龄
        age_match = re.search(r"(\d{2})\s*岁", text)
        if age_match:
            data.age = age_match.group(1)

        # 姓名 (前几行中 2-4 个汉字的词，不包含标点)
        first_lines = text.split("\n")[:6]
        for line in first_lines:
            line = line.strip()
            # 匹配 2-4 个汉字的姓名（不在关键词行中）
            name_match = re.match(r"^([\u4e00-\u9fa5]{2,4})$", line)
            if name_match:
                name = name_match.group(1)
                # 过滤掉常见非姓名关键词
                skip_words = {"个人信息", "基本信息", "求职意向", "教育经历", "工作经历",
                              "项目经历", "自我评价", "专业技能", "联系方式"}
                if name not in skip_words:
                    data.name = name
                    break

    @classmethod
    def _extract_objective(cls, text: str, data: ResumeData):
        """提取求职意向"""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            line = line.replace(" ", "")
            if "期望薪资" in line:
                data.desired_salary = line.split("期望薪资")[-1].strip().lstrip("：:：")
            if "期望城市" in line or "工作地点" in line:
                data.current_location = line.split("城市")[-1].split("地点")[-1].strip().lstrip("：:：")
        if not data.job_objective and lines:
            first_line = lines[0].replace(" ", "")
            if not any(k in first_line for k in ["薪资", "城市", "地点"]):
                data.job_objective = first_line.strip().lstrip("：:：")

    @classmethod
    def _extract_education(cls, text: str) -> List[dict]:
        """提取教育经历"""
        results = []
        # 每个教育经历块：学校 → 学历 → 专业 → 时间
        entries = re.split(r"\n(?=\d{4}|\d{2}\s*年|[A-Z\u4e00-\u9fa5]{2,}(?:大学|学院))", text)
        for entry in entries:
            if entry is None:
                continue
            entry = entry.strip()
            if not entry or len(entry) < 6:
                continue
            item = {"school": "", "degree": "", "major": "", "start": "", "end": "", "description": ""}
            # 学校
            school_match = re.search(r"([\u4e00-\u9fa5]{2,}(大学|学院|研究所))", entry)
            if school_match:
                item["school"] = school_match.group(0)
            # 学历
            degree_match = re.search(r"(本科|硕士|博士|大专|学士|研究生|MBA)", entry)
            if degree_match:
                item["degree"] = degree_match.group(0)
            # 专业
            major_match = re.search(r"专业[：:]?\s*([\u4e00-\u9fa5A-Za-z]+)", entry)
            if major_match:
                item["major"] = major_match.group(1)
            # 时间
            time_match = re.search(r"(\d{4}\.?\d{0,2})\s*[-–—至到]\s*(\d{4}\.?\d{0,2}|至今|现在)", entry)
            if time_match:
                item["start"] = time_match.group(1)
                item["end"] = time_match.group(2)
            if item["school"] or item["degree"] or item["major"]:
                results.append(item)
        return results

    @classmethod
    def _extract_work_experience(cls, text: str) -> List[dict]:
        """提取工作经历"""
        results = []
        # 按公司名或时间分割
        entries = re.split(
            r"\n(?=\d{4}\.\d{1,2}\s*[-–—至到]|\d{4}\s*年)"
            r"|(?<=\n)(?=[\u4e00-\u9fa5]{2,}(?:公司|集团|科技|网络|信息|有限))",
            text,
        )
        for entry in entries:
            if entry is None:
                continue
            entry = entry.strip()
            if not entry or len(entry) < 8:
                continue
            item = {"company": "", "position": "", "start": "", "end": "", "responsibilities": []}
            # 公司名
            company_match = re.search(r"([\u4e00-\u9fa5A-Za-z]{2,}(公司|集团|科技|网络|信息|有限|技术))", entry)
            if company_match:
                item["company"] = company_match.group(0)
            # 职位
            position_patterns = [
                r"(工程师|经理|主管|总监|专员|助理|实习生|开发|测试|产品|运营|设计|前端|后端|架构|数据)",
                r"(主管|经理|总监|负责人|组长)",
            ]
            for pat in position_patterns:
                pos_match = re.search(pat, entry)
                if pos_match:
                    item["position"] = pos_match.group(0)
                    break
            # 时间
            time_match = re.search(r"(\d{4}\.?\d{0,2})\s*[-–—至到]\s*(\d{4}\.?\d{0,2}|至今|现在)", entry)
            if time_match:
                item["start"] = time_match.group(1)
                item["end"] = time_match.group(2)
            # 工作职责
            resp_text = entry
            for replace_kw in [item["company"], item["position"], item["start"], item["end"]]:
                if replace_kw:
                    resp_text = resp_text.replace(replace_kw, " ")
            # 提取要点
            bullet_lines = re.findall(r"[•·●\-➢✓✔️☑\d+]+[\.\)、\s]?\s*(.+)", resp_text)
            if bullet_lines:
                item["responsibilities"] = [l.strip() for l in bullet_lines if len(l.strip()) > 3]
            else:
                # 没有列表符号，按句号分句
                sentences = re.split(r"[。；;]", resp_text)
                item["responsibilities"] = [s.strip() for s in sentences if len(s.strip()) > 5]
            if item["company"] or item["position"]:
                results.append(item)
        return results

    @classmethod
    def _extract_project_experience(cls, text: str) -> List[dict]:
        """提取项目经历"""
        results = []
        entries = re.split(r"\n(?=[\u4e00-\u9fa5A-Za-z]{2,}(?:项目|系统|平台))|\n(?=\d{4})", text)
        for entry in entries:
            if entry is None:
                continue
            entry = entry.strip()
            if not entry or len(entry) < 8:
                continue
            item = {"name": "", "role": "", "start": "", "end": "", "description": "", "highlights": []}
            # 项目名
            name_match = re.match(r"^[\u4e00-\u9fa5A-Za-z0-9\s]{2,30}$", entry.split("\n")[0])
            if name_match:
                item["name"] = name_match.group(0).strip()
            # 角色
            role_match = re.search(r"(负责|担任|角色)[：:]\s*(.+)", entry)
            if role_match:
                item["role"] = role_match.group(2).strip()
            # 时间
            time_match = re.search(r"(\d{4}\.?\d{0,2})\s*[-–—至到]\s*(\d{4}\.?\d{0,2}|至今)", entry)
            if time_match:
                item["start"] = time_match.group(1)
                item["end"] = time_match.group(2)
            # 要点
            bullet_lines = re.findall(r"[•·●\-➢✓✔️☑\d+]+[\.\)、\s]?\s*(.+)", entry)
            item["highlights"] = [l.strip() for l in bullet_lines if len(l.strip()) > 5]
            if item["name"]:
                results.append(item)
        return results

    @classmethod
    def _extract_skills(cls, text: str) -> List[str]:
        """提取技能列表"""
        skills = []
        # 按常见分隔符拆分
        parts = re.split(r"[，,、；;●•·\n]", text)
        for p in parts:
            p = p.strip()
            if p and len(p) > 1:
                # 去掉标点
                p = re.sub(r"^[：:：\s]+", "", p)
                if p and p not in ["专业技能", "技能", "技术栈"]:
                    skills.append(p)
        return skills[:20]  # 最多提取20个

    @classmethod
    def _extract_items(cls, text: str) -> List[str]:
        """提取列表项（证书等）"""
        items = []
        parts = re.split(r"[，,、；;●•·\n]", text)
        for p in parts:
            p = p.strip().lstrip("：:：")
            if p and len(p) > 2:
                skip = {"证书", "资格证书", "获奖", "荣誉", "语言能力"}
                if p not in skip:
                    items.append(p)
        return items[:10]

    @classmethod
    def _split_sections(cls, text: str) -> List[tuple]:
        """将简历文本按章节标题分割"""
        all_headers = (
            cls.PERSONAL_HEADERS + cls.OBJECTIVE_HEADERS + cls.EDUCATION_HEADERS +
            cls.WORK_HEADERS + cls.PROJECT_HEADERS + cls.SKILLS_HEADERS +
            cls.CERT_HEADERS + cls.SELF_EVAL_HEADERS
        )
        # 构建正则：匹配章节标题行
        pattern = "|".join(re.escape(h) for h in sorted(all_headers, key=len, reverse=True))
        # 找到所有章节标题的位置
        matches = list(re.finditer(rf"(?:^|\n)\s*({pattern})\s*[：:\n]", text, re.MULTILINE))
        if not matches:
            return [("全文", text)]

        sections = []
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            sections.append((title, content))
        return sections

    # ---- 兜底扫描 ----
    @classmethod
    def _find_education_global(cls, text: str) -> List[dict]:
        """全局搜索教育信息"""
        edu_block = re.search(r"(教育经历|教育背景|学历信息)[：:\s]*([\s\S]{10,200})", text)
        if edu_block:
            return cls._extract_education(edu_block.group(2))
        return []

    @classmethod
    def _find_work_global(cls, text: str) -> List[dict]:
        """全局搜索工作信息"""
        work_block = re.search(r"(工作经历|工作经验|工作履历)[：:\s]*([\s\S]{10,500})", text)
        if work_block:
            return cls._extract_work_experience(work_block.group(2))
        return []

"""简历与JD关键词匹配引擎 - 提取关键词、计算匹配度、分析重合度"""

import json
import os
import re
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional


# ---- 技术关键词词典（按类别组织） ----
TECH_KEYWORDS: Dict[str, Set[str]] = {
    # 编程语言
    "编程语言": {
        "python", "java", "javascript", "typescript", "go", "golang", "rust",
        "c++", "cpp", "c#", "csharp", "php", "ruby", "swift", "kotlin",
        "scala", "dart", "elixir", "clojure", "haskell", "lua", "perl",
        "r", "matlab", "shell", "bash", "powershell",
    },
    # 前端技术
    "前端技术": {
        "react", "vue", "angular", "svelte", "next.js", "nuxt", "webpack",
        "vite", "babel", "eslint", "css", "scss", "sass", "less", "tailwind",
        "bootstrap", "jquery", "html5", "html", "dom", "redux", "mobx",
        "zustand", "pinia", "vuex", "react native", "flutter", "electron",
        "小程序", "微信小程序", "uniapp", "taro", "three.js", "d3.js",
    },
    # 后端技术
    "后端技术": {
        "spring", "springboot", "spring cloud", "mybatis", "django", "flask",
        "fastapi", "gin", "express", "nestjs", "koa", "node.js", "nodejs",
        "deno", "graphql", "restful", "rest api", "grpc", "微服务", "microservice",
        "消息队列", "kafka", "rabbitmq", "redis", "soa", "rpc",
    },
    # 数据库
    "数据库": {
        "mysql", "postgresql", "mongodb", "redis", "elasticsearch", "oracle",
        "sql server", "sqlite", "cassandra", "dynamodb", "neo4j", "hbase",
        "tidb", "clickhouse", "doris", "starrocks", "influxdb", "prometheus",
        "数据库", "sql", "nosql", "数据仓库", "数据湖", "etl",
    },
    # 云原生/DevOps
    "云原生与DevOps": {
        "docker", "kubernetes", "k8s", "jenkins", "gitlab ci", "github actions",
        "terraform", "ansible", "prometheus", "grafana", "elk", "nginx",
        "haproxy", "envoy", "istio", "helm", "argocd", "serverless",
        "aws", "azure", "gcp", "阿里云", "腾讯云", "华为云", "云原生",
        "devops", "cicd", "ci/cd", "持续集成", "持续部署",
    },
    # 大数据/AI
    "大数据与AI": {
        "hadoop", "spark", "flink", "hive", "kafka", "airflow",
        "tensorflow", "pytorch", "keras", "scikit-learn", "机器学习",
        "深度学习", "nlp", "自然语言处理", "计算机视觉", "cv", "推荐系统",
        "大模型", "llm", "langchain", "transformer", "gpt", "bert",
        "数据挖掘", "数据科学", "pandas", "numpy", "数据分析",
    },
    # 移动端
    "移动端": {
        "android", "ios", "swift", "kotlin", "flutter", "react native",
        "小程序", "app", "移动端", "hybrid", "weex",
    },
    # 通用软技能
    "软技能": {
        "团队管理", "项目管理", "沟通", "领导力", "敏捷", "scrum",
        "团队协作", "跨部门", "需求分析", "架构设计", "技术方案",
        "代码审查", "code review", "性能优化", "问题解决", "创新",
        "自驱", "抗压", "owner", "ownership",
    },
    # 行业领域
    "行业领域": {
        "金融", "电商", "游戏", "社交", "教育", "医疗", "汽车",
        "物联网", "iot", "区块链", "web3", "saas", "paas", "b端",
        "c端", "to b", "to c", "出海", "国际化",
    },
}

# 学历关键词
EDUCATION_LEVELS = {
    "博士": 5, "硕士": 4, "本科": 3, "大专": 2, "高中": 1,
    "phd": 5, "master": 4, "bachelor": 3,
}

# 软技能/通用能力关键词
SOFT_SKILLS = {
    "沟通能力", "团队协作", "项目管理", "领导力", "抗压能力",
    "学习能力", "自驱力", "owner意识", "owner", "ownership",
    "逻辑思维", "分析能力", "解决问题的能力", "创新", "执行力",
    "时间管理", "多任务", "跨部门沟通", "推动能力", "落地能力",
}


@dataclass
class KeywordExtractResult:
    """从文本中提取的关键词集合"""
    tech_keywords: Set[str] = field(default_factory=set)
    soft_skills: Set[str] = field(default_factory=set)
    education_level: int = 0           # 最高学历等级
    education_text: str = ""           # 学历原文
    experience_years: float = 0.0      # 经验年限
    cert_keywords: Set[str] = field(default_factory=set)
    other_keywords: Set[str] = field(default_factory=set)
    all_keywords: Set[str] = field(default_factory=set)  # 所有规范化关键词


@dataclass
class MatchResult:
    """匹配结果"""
    # 整体得分
    overall_score: float = 0.0          # 0-100
    score_level: str = ""               # 极高/高/中等/较低/低

    # 关键词维度
    total_jd_keywords: int = 0
    total_resume_keywords: int = 0
    matched_keywords: List[str] = field(default_factory=list)
    matched_count: int = 0
    unmatched_jd_keywords: List[str] = field(default_factory=list)

    # 分类维度
    tech_match_score: float = 0.0
    soft_skill_score: float = 0.0
    education_match: bool = False
    experience_match: bool = False

    # 分类明细
    category_scores: Dict[str, Dict] = field(default_factory=dict)
    # {category_name: {"jd_count": int, "resume_count": int, "matched": int, "score": float}}

    # 简历亮点
    resume_highlights: List[str] = field(default_factory=list)

    # 改进建议
    suggestions: List[str] = field(default_factory=list)


class KeywordExtractor:
    """关键词提取器"""

    @classmethod
    def extract_from_text(cls, text: str) -> KeywordExtractResult:
        """从原始文本直接提取关键词——当结构化解析失败时的兜底方案"""
        result = KeywordExtractResult()
        text_lower = text.lower()

        # 匹配技术词典
        for category, keywords in TECH_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    result.tech_keywords.add(kw)

        # 匹配软技能
        for skill in SOFT_SKILLS:
            if skill in text_lower or skill.replace("能力", "") in text_lower:
                result.soft_skills.add(skill)

        # 提取学历
        for level, score in sorted(EDUCATION_LEVELS.items(), key=lambda x: -x[1]):
            if level in text_lower:
                result.education_level = max(result.education_level, score)
                break

        # 估算经验年限
        exp_match = re.search(r'(\d+)\s*年', text)
        if exp_match:
            result.experience_years = float(exp_match.group(1))

        # 提取证书
        cert_matches = re.findall(r'(?:持有|拥有|获得|具备)\s*([\u4e00-\u9fa5A-Za-z/+]+(?:证书|认证)?)', text)
        for cert in cert_matches:
            result.cert_keywords.add(cert.strip().lower())

        # 构建关键词集合
        all_text_parts = [text_lower]
        for cat_kw in TECH_KEYWORDS.values():
            all_text_parts.extend(cat_kw)
        combined = " ".join(all_text_parts)
        result.all_keywords = cls._build_all_keywords(result)

        return result

    @classmethod
    def extract_from_jd_text(cls, text: str) -> KeywordExtractResult:
        """从原始JD文本直接提取关键词——当JD正则解析失败时的兜底"""
        result = KeywordExtractResult()
        text_lower = text.lower()

        for category, keywords in TECH_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    result.tech_keywords.add(kw)

        for skill in SOFT_SKILLS:
            if skill in text_lower or skill.replace("能力", "") in text_lower:
                result.soft_skills.add(skill)

        for level, score in EDUCATION_LEVELS.items():
            if level in text_lower:
                result.education_level = max(result.education_level, score)
                break

        exp_match = re.search(r'(\d+)\s*年(?:以上|及以上|经验)', text_lower)
        if not exp_match:
            exp_match = re.search(r'(\d+)[-~至到]\s*(\d+)\s*年', text_lower)
        if exp_match:
            result.experience_years = float(exp_match.group(1))

        result.all_keywords = cls._build_all_keywords(result)
        return result

    @classmethod
    def extract_from_resume(cls, resume_data: dict) -> KeywordExtractResult:
        """从解析后的简历数据中提取关键词"""
        result = KeywordExtractResult()

        all_text_parts = []

        # 1. 提取技能关键词
        skills = resume_data.get("skills", [])
        if isinstance(skills, list):
            for skill in skills:
                skill_lower = str(skill).strip().lower()
                if not skill_lower:
                    continue
                all_text_parts.append(skill_lower)
                # 匹配技术词典
                matched_cat = cls._match_tech_keyword(skill_lower)
                if matched_cat:
                    result.tech_keywords.add(skill_lower)
                elif skill_lower in SOFT_SKILLS or any(s in skill_lower for s in SOFT_SKILLS):
                    result.soft_skills.add(skill_lower)
                else:
                    result.other_keywords.add(skill_lower)

        # 2. 从工作经历提取关键词
        work_exp = resume_data.get("work_experience", [])
        if isinstance(work_exp, list):
            for exp in work_exp:
                if isinstance(exp, dict):
                    resp_list = exp.get("responsibilities", [])
                    if isinstance(resp_list, list):
                        for resp in resp_list:
                            resp_text = str(resp).lower()
                            all_text_parts.append(resp_text)
                    company = str(exp.get("company", "")).lower()
                    position = str(exp.get("position", "")).lower()
                    all_text_parts.append(company)
                    all_text_parts.append(position)

        # 从工作描述中提取技术关键词
        combined_text = " ".join(all_text_parts)
        for category, keywords in TECH_KEYWORDS.items():
            for kw in keywords:
                if kw in combined_text:
                    result.tech_keywords.add(kw)

        # 从工作描述中提取软技能
        for skill in SOFT_SKILLS:
            if skill in combined_text or skill.replace("能力", "") in combined_text:
                result.soft_skills.add(skill)

        # 3. 提取学历信息
        education = resume_data.get("education", [])
        if isinstance(education, list) and education:
            for edu in education:
                if isinstance(edu, dict):
                    edu_text = f"{edu.get('degree', '')} {edu.get('major', '')}".lower()
                    result.education_text = edu_text
                    for level, score in EDUCATION_LEVELS.items():
                        if level in edu.get("degree", ""):
                            result.education_level = max(result.education_level, score)
                            break
                    # 专业名称作为关键词
                    major = edu.get("major", "")
                    if major:
                        result.other_keywords.add(major.lower())

        # 4. 估算经验年限（从工作经历时间段计算）
        if isinstance(work_exp, list):
            for exp in work_exp:
                if isinstance(exp, dict):
                    years = cls._estimate_years(
                        str(exp.get("start", "")), str(exp.get("end", ""))
                    )
                    result.experience_years += years

        # 5. 提取证书
        certs = resume_data.get("certifications", [])
        if isinstance(certs, list):
            for cert in certs:
                cert_str = str(cert).strip().lower()
                if cert_str and len(cert_str) > 2:
                    result.cert_keywords.add(cert_str)

        # 6. 从自我评价中提取关键词
        self_eval = resume_data.get("self_evaluation", "")
        if self_eval:
            self_eval_lower = str(self_eval).lower()
            for category, keywords in TECH_KEYWORDS.items():
                for kw in keywords:
                    if kw in self_eval_lower:
                        result.tech_keywords.add(kw)
            for skill in SOFT_SKILLS:
                if skill in self_eval_lower:
                    result.soft_skills.add(skill)

        # 7. 构建全量关键词集合
        result.all_keywords = cls._build_all_keywords(result)

        return result

    @classmethod
    def extract_from_jd(cls, jd_data: dict, jd_text: str = "") -> KeywordExtractResult:
        """从解析后的JD数据中提取关键词"""
        result = KeywordExtractResult()

        combined_text = jd_text.lower() if jd_text else ""

        # 1. 从职责和要求中提取关键词
        responsibilities = jd_data.get("responsibilities", [])
        requirements = jd_data.get("requirements", [])

        all_items = []
        if isinstance(responsibilities, list):
            all_items.extend(responsibilities)
        if isinstance(requirements, list):
            all_items.extend(requirements)

        for item in all_items:
            item_text = str(item).lower()
            combined_text += " " + item_text

        # 也从 job_title 提取
        job_title = str(jd_data.get("job_title", "")).lower()
        combined_text += " " + job_title

        # 2. 匹配技术词典
        for category, keywords in TECH_KEYWORDS.items():
            for kw in keywords:
                if kw in combined_text:
                    result.tech_keywords.add(kw)

        # 3. 提取软技能
        for skill in SOFT_SKILLS:
            if skill in combined_text or skill.replace("能力", "") in combined_text:
                result.soft_skills.add(skill)

        # 4. 从单独的要求列表中提取学历要求
        if isinstance(requirements, list):
            req_text = " ".join(str(r) for r in requirements).lower()
        else:
            req_text = combined_text

        for level, score in EDUCATION_LEVELS.items():
            if level in req_text:
                result.education_level = max(result.education_level, score)
                result.education_text = level

        # 5. 提取经验要求
        education_req = str(jd_data.get("education", ""))
        experience_req = str(jd_data.get("experience", ""))
        all_req = req_text + " " + education_req + " " + experience_req

        # 匹配X年以上经验
        exp_patterns = [
            r"(\d+)\s*年(?:以上|及以上|经验|工作)",
            r"(\d+)[-~至到]\s*(\d+)\s*年",
            r"经验(\d+)[-~至到]*(\d*)年",
        ]
        for pattern in exp_patterns:
            match = re.search(pattern, all_req)
            if match:
                years = float(match.group(1))
                result.experience_years = max(result.experience_years, years)
                break

        # 6. 提取行业关键词和通用要求
        # 从JD文本中提取一些通用关键词（不在技术词典中的）
        other_patterns = [
            r"(熟悉|精通|了解|掌握)\s*([\u4e00-\u9fa5a-zA-Z/+]+)",
            r"(具备|拥有|持有)\s*([\u4e00-\u9fa5a-zA-Z/+]+?)(?:能力|经验|证书)",
        ]
        for pattern in other_patterns:
            for m in re.finditer(pattern, all_req):
                kw = m.group(2).strip().lower()
                if kw and len(kw) > 1 and kw not in result.tech_keywords and kw not in result.soft_skills:
                    result.other_keywords.add(kw)

        # 构建全量关键词
        result.all_keywords = cls._build_all_keywords(result)

        return result

    @classmethod
    def _match_tech_keyword(cls, word: str) -> Optional[str]:
        """匹配技术关键词所属分类"""
        word_lower = word.lower().strip()
        for category, keywords in TECH_KEYWORDS.items():
            if word_lower in keywords:
                return category
        return None

    @classmethod
    def _estimate_years(cls, start: str, end: str) -> float:
        """估算时间段的年数"""
        try:
            import datetime
            current_year = datetime.datetime.now().year

            def parse_year(s: str) -> Optional[int]:
                s = s.strip()
                if not s or s in ("至今", "现在", "present", "now"):
                    return current_year
                match = re.search(r"(\d{4})", s)
                if match:
                    return int(match.group(1))
                return None

            start_year = parse_year(start)
            end_year = parse_year(end)

            if start_year and end_year:
                return max(0.0, float(end_year - start_year))
        except Exception:
            pass
        return 0.0

    @classmethod
    def _build_all_keywords(cls, result: KeywordExtractResult) -> Set[str]:
        """构建全量归一化关键词集合"""
        all_kw = set()

        # 技术关键词保持原样（已经是小写）
        all_kw.update(result.tech_keywords)

        # 软技能关键词
        all_kw.update(result.soft_skills)

        # 其他关键词
        all_kw.update(result.other_keywords)

        return all_kw


class ResumeJDMatcher:
    """简历-JD匹配引擎"""

    @classmethod
    def match(
        cls,
        resume_keywords: KeywordExtractResult,
        jd_keywords: KeywordExtractResult,
    ) -> MatchResult:
        """计算简历和JD的关键词匹配度"""
        result = MatchResult()

        # ---- 1. 核心关键词匹配 ----
        jd_all = jd_keywords.all_keywords
        resume_all = resume_keywords.all_keywords

        result.total_jd_keywords = len(jd_all)
        result.total_resume_keywords = len(resume_all)

        matched = jd_all & resume_all
        result.matched_keywords = sorted(matched)
        result.matched_count = len(matched)

        unmatched = jd_all - resume_all
        result.unmatched_jd_keywords = sorted(unmatched)

        # ---- 2. 分类维度匹配 ----
        category_scores = {}

        # 按 TECH_KEYWORDS 分类计算
        for category, keywords in TECH_KEYWORDS.items():
            jd_cat = jd_keywords.tech_keywords & keywords
            resume_cat = resume_keywords.tech_keywords & keywords

            jd_count = len(jd_cat)
            resume_count = len(resume_cat)
            matched_count = len(jd_cat & resume_cat)

            if jd_count > 0:
                score = round(matched_count / jd_count * 100, 1)
            else:
                score = 100.0 if resume_count == 0 else 0.0  # JD没要求则默认满分

            category_scores[category] = {
                "jd_count": jd_count,
                "resume_count": resume_count,
                "matched_count": matched_count,
                "score": score,
                "jd_keywords": sorted(jd_cat),
                "resume_keywords": sorted(resume_cat),
                "matched_keywords": sorted(jd_cat & resume_cat),
            }

        result.category_scores = category_scores

        # 技术维度得分
        tech_jd_count = len(jd_keywords.tech_keywords)
        if tech_jd_count > 0:
            tech_matched = len(jd_keywords.tech_keywords & resume_keywords.tech_keywords)
            result.tech_match_score = round(tech_matched / tech_jd_count * 100, 1)
        else:
            result.tech_match_score = 100.0

        # 软技能得分
        jd_soft_count = len(jd_keywords.soft_skills)
        if jd_soft_count > 0:
            soft_matched = len(jd_keywords.soft_skills & resume_keywords.soft_skills)
            result.soft_skill_score = round(soft_matched / jd_soft_count * 100, 1)
        else:
            result.soft_skill_score = 100.0

        # 学历匹配
        if jd_keywords.education_level > 0:
            result.education_match = resume_keywords.education_level >= jd_keywords.education_level
        else:
            result.education_match = True  # JD没要求学历则默认满足

        # 经验匹配
        if jd_keywords.experience_years > 0:
            result.experience_match = resume_keywords.experience_years >= jd_keywords.experience_years
        else:
            result.experience_match = True

        # ---- 3. 综合评分 ----
        result.overall_score = cls._calculate_overall_score(result, jd_keywords)

        # 评分等级
        if result.overall_score >= 90:
            result.score_level = "极高"
        elif result.overall_score >= 75:
            result.score_level = "高"
        elif result.overall_score >= 60:
            result.score_level = "中等"
        elif result.overall_score >= 40:
            result.score_level = "较低"
        else:
            result.score_level = "低"

        # ---- 4. 简历亮点 ----
        highlights = []
        # 找出简历有而JD也有的核心技术关键词
        highlight_cats = ["编程语言", "后端技术", "前端技术", "数据库", "云原生与DevOps"]
        for cat in highlight_cats:
            if cat in category_scores:
                cs = category_scores[cat]
                if cs["matched_count"] >= 3:
                    highlights.append(
                        f"在「{cat}」方面，有 {cs['matched_count']} 项技能与岗位要求匹配"
                    )
        result.resume_highlights = highlights[:5]

        # ---- 5. 改进建议 ----
        suggestions = []
        if not result.education_match and jd_keywords.education_level > 0:
            suggestions.append(
                f"学历要求不满足（JD要求{jd_keywords.education_text or '更高学历'}），"
                f"建议在简历中突出与学历要求相关的资质或项目经验"
            )
        if not result.experience_match and jd_keywords.experience_years > 0:
            suggestions.append(
                f"经验年限不足（JD要求约{int(jd_keywords.experience_years)}年），"
                f"建议通过高质量项目经历弥补年限差距"
            )

        # 缺失的关键技术
        missing_tech = sorted(jd_keywords.tech_keywords - resume_keywords.tech_keywords)
        if missing_tech:
            priority_tech = list(missing_tech)[:5]
            suggestions.append(
                f"简历中缺失以下JD要求的技术关键词：{', '.join(priority_tech)}"
                f"{' 等' if len(missing_tech) > 5 else ''}，"
                f"建议在技能列表或项目经历中补充相关内容"
            )

        # 软技能建议
        missing_soft = sorted(jd_keywords.soft_skills - resume_keywords.soft_skills)
        if missing_soft:
            suggestions.append(
                f"可考虑在自我评价中补充这些软技能：{', '.join(list(missing_soft)[:3])}"
            )

        result.suggestions = suggestions

        return result

    @classmethod
    def _calculate_overall_score(
        cls, match_result: MatchResult, jd_keywords: KeywordExtractResult
    ) -> float:
        """计算综合匹配分（0-100）"""
        weights = {
            "keyword_overlap": 0.40,     # 关键词重叠率
            "tech_match": 0.30,          # 技术匹配度
            "soft_skill": 0.10,          # 软技能匹配度
            "education": 0.10,           # 学历匹配
            "experience": 0.10,          # 经验匹配
        }

        # 关键词重叠得分
        if match_result.total_jd_keywords > 0:
            kw_score = match_result.matched_count / match_result.total_jd_keywords * 100
        else:
            kw_score = 100.0

        # 加权总分
        total = (
            weights["keyword_overlap"] * kw_score
            + weights["tech_match"] * match_result.tech_match_score
            + weights["soft_skill"] * match_result.soft_skill_score
            + weights["education"] * (100.0 if match_result.education_match else 30.0)
            + weights["experience"] * (100.0 if match_result.experience_match else 40.0)
        )

        return round(total, 1)


# ---- OCR 关键词搜索评分引擎 ----


class OCRKeywordMatcher:
    """
    基于 JD 关键词对 OCR 识别文本进行搜索评分。

    流程：
    1. 从 JD 文本提取关键词（使用 KeywordExtractor）
    2. 将 PDF 简历转为图片后 OCR 识别得到文本
    3. 逐关键词在 OCR 文本中搜索，按匹配率评分
    """

    @classmethod
    def match(
        cls,
        jd_keywords: "KeywordExtractResult",
        ocr_text: str,
        jd_title: str = "",
        resume_name: str = "",
    ) -> "MatchResult":
        """
        用 JD 关键词在 OCR 简历文本中搜索并评分。

        Args:
            jd_keywords: 从 JD 提取的关键词集合
            ocr_text: OCR 识别出的简历文本
            jd_title: 岗位名称（选填）
            resume_name: 候选人姓名（选填）

        Returns:
            MatchResult 匹配结果
        """
        result = MatchResult()
        ocr_lower = ocr_text.lower()

        # ---- 1. 逐关键词在 OCR 文本中搜索 ----
        matched_kw: List[str] = []
        partial_kw: List[str] = []   # 部分匹配（多词关键词中部分词出现）
        unmatched_kw: List[str] = []

        jd_all = jd_keywords.all_keywords
        result.total_jd_keywords = len(jd_all)
        result.total_resume_keywords = 0  # OCR 模式下不统计简历关键词数

        for kw in sorted(jd_all):
            kw_lower = kw.lower().strip()
            if not kw_lower:
                continue

            match_level = cls._search_keyword(kw_lower, ocr_lower)
            if match_level == "exact":
                matched_kw.append(kw)
            elif match_level == "partial":
                partial_kw.append(kw)
            else:
                unmatched_kw.append(kw)

        result.matched_keywords = matched_kw
        result.unmatched_jd_keywords = unmatched_kw
        result.matched_count = len(matched_kw)

        # ---- 2. 按技术分类维度评分 ----
        category_scores = {}
        for category, cat_keywords in TECH_KEYWORDS.items():
            jd_cat = jd_keywords.tech_keywords & cat_keywords
            jd_count = len(jd_cat)

            if jd_count == 0:
                category_scores[category] = {
                    "jd_count": 0,
                    "resume_count": 0,
                    "matched_count": 0,
                    "score": 100.0,
                    "jd_keywords": [],
                    "resume_keywords": [],
                    "matched_keywords": [],
                }
                continue

            cat_matched = [k for k in jd_cat if k in matched_kw]
            cat_partial = [k for k in jd_cat if k in partial_kw]

            effective_matched = len(cat_matched) + len(cat_partial) * 0.5
            score = round(effective_matched / jd_count * 100, 1)

            category_scores[category] = {
                "jd_count": jd_count,
                "resume_count": 0,  # OCR 模式下不计
                "matched_count": len(cat_matched) + len(cat_partial),
                "score": min(100.0, score),
                "jd_keywords": sorted(jd_cat),
                "resume_keywords": [],
                "matched_keywords": sorted(cat_matched),
            }

        result.category_scores = category_scores

        # ---- 3. 技术维度得分（加权） ----
        tech_jd_count = len(jd_keywords.tech_keywords)
        if tech_jd_count > 0:
            tech_matched = sum(
                1.0 for k in jd_keywords.tech_keywords if k in matched_kw
            ) + sum(
                0.5 for k in jd_keywords.tech_keywords if k in partial_kw
            )
            result.tech_match_score = round(tech_matched / tech_jd_count * 100, 1)
        else:
            result.tech_match_score = 100.0

        # ---- 4. 软技能得分 ----
        jd_soft_count = len(jd_keywords.soft_skills)
        if jd_soft_count > 0:
            soft_matched = sum(
                1.0 for k in jd_keywords.soft_skills if k in matched_kw
            ) + sum(
                0.5 for k in jd_keywords.soft_skills if k in partial_kw
            )
            result.soft_skill_score = round(soft_matched / jd_soft_count * 100, 1)
        else:
            result.soft_skill_score = 100.0

        # ---- 5. 学历与经验（从 OCR 文本估算） ----
        resume_kw = KeywordExtractor.extract_from_text(ocr_text)

        if jd_keywords.education_level > 0:
            result.education_match = resume_kw.education_level >= jd_keywords.education_level
        else:
            result.education_match = True

        if jd_keywords.experience_years > 0:
            result.experience_match = resume_kw.experience_years >= jd_keywords.experience_years
        else:
            result.experience_match = True

        # ---- 6. 综合评分 ----
        result.overall_score = cls._calculate_overall_score(result, jd_keywords)
        result.score_level = cls._score_level(result.overall_score)

        # ---- 7. 简历亮点 ----
        highlights = []
        highlight_cats = ["编程语言", "后端技术", "前端技术", "数据库", "云原生与DevOps"]
        for cat in highlight_cats:
            if cat in category_scores:
                cs = category_scores[cat]
                matched_c = cs.get("matched_count", 0)
                if matched_c >= 3:
                    highlights.append(
                        f"在「{cat}」方面，OCR 识别文本中有 {matched_c} 项技能与岗位要求匹配"
                    )
        result.resume_highlights = highlights[:5]

        # ---- 8. 改进建议 ----
        suggestions = []
        if not result.education_match and jd_keywords.education_level > 0:
            suggestions.append(
                f"学历要求不满足（JD 要求 {jd_keywords.education_text or '更高学历'}），"
                "建议在简历中突出相关资质或项目经验"
            )
        if not result.experience_match and jd_keywords.experience_years > 0:
            suggestions.append(
                f"经验年限不足（JD 要求约 {int(jd_keywords.experience_years)} 年），"
                "建议通过高质量项目经历弥补年限差距"
            )

        missing_tech = sorted(
            jd_keywords.tech_keywords
            - set(matched_kw)
            - set(partial_kw)
        )
        if missing_tech:
            priority_tech = missing_tech[:5]
            suggestions.append(
                f"OCR 简历文本中缺失以下 JD 要求的技术关键词："
                f"{', '.join(priority_tech)}"
                f"{' 等' if len(missing_tech) > 5 else ''}，"
                "建议在简历中补充或确保 OCR 识别完整"
            )

        missing_soft = sorted(
            jd_keywords.soft_skills
            - set(matched_kw)
            - set(partial_kw)
        )
        if missing_soft:
            suggestions.append(
                f"可考虑在简历中补充这些软技能：{', '.join(missing_soft[:3])}"
            )

        # 如果部分匹配较多，提醒 OCR 质量
        if len(partial_kw) > len(matched_kw) * 0.5:
            suggestions.append(
                "注意：较多关键词仅部分匹配，可能是 OCR 识别不够准确，"
                "建议检查 PDF 清晰度或使用截图方式上传"
            )

        result.suggestions = suggestions
        result.resume_highlights += partial_kw[:3]  # 额外: 部分匹配的关键词

        return result

    @classmethod
    def _search_keyword(cls, keyword: str, text_lower: str) -> str:
        """
        在文本中搜索关键词，返回匹配级别。

        Returns:
            "exact"  - 完全匹配（关键词整体在文本中找到）
            "partial" - 部分匹配（多词关键词的部分词在文本中找到）
            "none"   - 未找到
        """
        if not keyword:
            return "none"

        # 精确匹配
        if keyword in text_lower:
            return "exact"

        # 对多词关键词做分词匹配
        if " " in keyword or "·" in keyword:
            tokens = cls._tokenize(keyword)
            if not tokens:
                return "none"
            found_count = sum(1 for t in tokens if t in text_lower)
            # 超过一半的词出现 → 部分匹配
            if found_count >= len(tokens) / 2:
                return "partial"

        # 尝试去掉常见修饰词后匹配
        # e.g. "熟悉docker" → "docker"
        stripped = re.sub(
            r'^(熟悉|精通|了解|掌握|具备|拥有|持有|有)\s*',
            '', keyword
        )
        if stripped != keyword and stripped in text_lower:
            return "exact"

        return "none"

    @classmethod
    def _tokenize(cls, keyword: str) -> List[str]:
        """将多词关键词拆分为 token 列表，过滤短词"""
        tokens = re.split(r'[\s·/]+', keyword)
        return [t for t in tokens if len(t) >= 2]

    @classmethod
    def _calculate_overall_score(
        cls, result: "MatchResult", jd_keywords: "KeywordExtractResult"
    ) -> float:
        """计算 OCR 匹配综合分"""
        weights = {
            "keyword_overlap": 0.40,
            "tech_match": 0.30,
            "soft_skill": 0.10,
            "education": 0.10,
            "experience": 0.10,
        }

        if result.total_jd_keywords > 0:
            kw_score = result.matched_count / result.total_jd_keywords * 100
        else:
            kw_score = 100.0

        total = (
            weights["keyword_overlap"] * kw_score
            + weights["tech_match"] * result.tech_match_score
            + weights["soft_skill"] * result.soft_skill_score
            + weights["education"] * (100.0 if result.education_match else 30.0)
            + weights["experience"] * (100.0 if result.experience_match else 40.0)
        )

        return round(total, 1)

    @staticmethod
    def _score_level(score: float) -> str:
        if score >= 90:
            return "极高"
        elif score >= 75:
            return "高"
        elif score >= 60:
            return "中等"
        elif score >= 40:
            return "较低"
        return "低"


# ---- LLM 智能匹配引擎（内置核心） ----

# 导入类型（避免循环引用）
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.skills.resume_optimizer.parser import ResumeData
    from app.skills.jd_parser.parser import JDParsedResult


MATCH_SYSTEM_PROMPT = """你是资深HR与招聘专家，专精于简历与岗位JD的深度匹配分析。
请严格按以下五个维度逐一分析，给出评分和详细理由，最后输出结构化JSON。

---

## 评分标准（每个维度 0-100 分）

### 维度一：技术栈与硬技能匹配（权重 35%）
评分规则：
- 逐项对比JD技术要求与简历技能清单
- 每项匹配+15分，部分匹配（相关但非同一技术）+8分，缺失+0分
- 最终归一化到0-100: score = min(100, 实际匹配总分/基准分x100)
- 关注：编程语言、框架、数据库、云原生、中间件、AI/大数据工具

### 维度二：工作经验与项目复杂度（权重 30%）
评分规则：
- 工作年限是否满足JD要求（满足40分，每多一年+5，上限60）
- 项目复杂度与JD描述的匹配度（简单0-10，中等10-20，复杂20-30，高复杂30-40，总分40）
- 行业/业务领域相关性（完全无关0，部分相关5-10，高度相关10-15，加分项上限15）
- 总分上限100

### 维度三：学历与专业背景（权重 10%）
评分规则：
- 学历等级：博士=100，硕士=80，本科=60，大专=40，其他=20
- 专业相关度：完全匹配JD要求+20（上限100），不相关-20，JD未要求则不扣分
- JD未明确要求学历则默认80

### 维度四：软技能与综合素质（权重 15%）
评分规则：
- 从简历的自我评价、工作描述中推断软技能
- 与JD要求的软技能比对：完全匹配80-100，部分匹配50-79，基本不匹配20-49

### 维度五：综合印象（权重 10%）
- 简历完整度、表达质量、亮点突出度
- 加分项：证书、获奖、开源贡献、行业影响力等

---

## 综合得分计算
综合分 = 维度一x0.35 + 维度二x0.30 + 维度三x0.10 + 维度四x0.15 + 维度五x0.10

## 评分等级
- 90-100：极高匹配 - 可直接进入面试
- 75-89：高匹配 - 大概率通过简历筛选
- 60-74：中等匹配 - 有竞争力但需突出某些点
- 40-59：较低匹配 - 建议针对性修改简历
- 0-39：低匹配 - 与该岗位差距较大

---

## 输出格式（严格JSON，不要任何额外文字）

{
  "overall_score": 75,
  "score_level": "高",
  "summary": "一句话总结匹配情况，突出最大亮点与最需补足之处",
  "dimension_scores": {
    "tech_stack": {"score": 80, "weight": 35, "comment": "核心技能Python/Django/MySQL均匹配，但缺少Kubernetes经验"},
    "experience": {"score": 70, "weight": 30, "comment": "5年经验满足3年要求，项目以电商为主，与JD金融方向略有差异"},
    "education": {"score": 80, "weight": 10, "comment": "本科学历满足要求，计算机专业对口"},
    "soft_skills": {"score": 65, "weight": 15, "comment": "技术能力突出，但管理经验在简历中体现不足"},
    "overall_quality": {"score": 60, "weight": 10, "comment": "简历整体完整，但部分描述缺乏量化数据"}
  },
  "detail_analysis": {
    "tech_stack": {
      "matched": [{"keyword": "Python", "level": "精通", "evidence": "5年后端开发经验"}],
      "partial": [{"keyword": "Docker", "level": "了解", "evidence": "项目中使用过容器化部署"}],
      "missing": ["Kubernetes", "CI/CD流水线", "微服务架构"]
    },
    "experience": {
      "years_required": 3,
      "years_actual": 5,
      "project_complexity": "中等",
      "industry_match": "部分相关（电商 vs 金融）"
    },
    "education": {
      "required": "本科及以上",
      "actual": "本科 计算机科学与技术",
      "match": true
    }
  },
  "matched_keywords": ["Python", "Django", "MySQL", "Docker", "Redis", "Git"],
  "unmatched_keywords": ["Kubernetes", "CI/CD", "微服务", "Flink"],
  "highlights": [
    "Python和Django技术栈与JD高度匹配，具备5年深度使用经验",
    "有大流量高并发项目经验，满足JD对系统性能优化的要求"
  ],
  "suggestions": [
    "【高优先级】补充Kubernetes/容器编排经验，这是JD的硬性要求",
    "【中优先级】项目描述中增加量化数据（如QPS、数据量级、团队规模）",
    "【低优先级】自我评价中强调团队管理和跨部门协作经验"
  ],
  "education_match": true,
  "experience_match": true,
  "tech_match_score": 80,
  "soft_skill_score": 65,
  "category_scores": {
    "编程语言": {"jd_count": 2, "resume_count": 2, "matched_count": 2, "score": 100.0},
    "后端技术": {"jd_count": 4, "resume_count": 3, "matched_count": 2, "score": 50.0},
    "数据库": {"jd_count": 3, "resume_count": 2, "matched_count": 2, "score": 66.7},
    "云原生与DevOps": {"jd_count": 3, "resume_count": 1, "matched_count": 1, "score": 33.3}
  },
  "total_jd_keywords": 12,
  "total_resume_keywords": 8,
  "matched_count": 6
}"""


class LLMMatcher:
    """
    内置LLM匹配引擎 - 直接将简历和JD按维度分段传给大模型，
    按明确的评分标准逐维度分析并输出结构化结果。

    这是匹配功能的主路径，不依赖硬编码关键词词典。
    """

    _client = None
    _model = None

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            from app.core.config import create_openai_client
            cls._client, cls._model = create_openai_client("match")
        return cls._client, cls._model

    @classmethod
    def match(
        cls,
        resume_text: str = "",
        jd_text: str = "",
        resume_data: object = None,
        jd_parsed: object = None,
        resume_name: str = "",
        jd_title: str = "",
        max_chars_per_section: int = 4000,
    ) -> Optional[MatchResult]:
        """
        使用LLM进行简历-JD分维度深度匹配分析。

        Args:
            resume_text: 完整简历原始文本
            jd_text: 完整JD原始文本
            resume_data: 结构化解析后的ResumeData（优先使用）
            jd_parsed: 结构化解析后的JDParsedResult（优先使用）
            resume_name: 候选人姓名
            jd_title: 岗位名称
            max_chars_per_section: 每个分段的文本截断长度

        Returns:
            MatchResult 或 None
        """
        user_prompt = cls._build_segmented_prompt(
            resume_text=resume_text,
            jd_text=jd_text,
            resume_data=resume_data,
            jd_parsed=jd_parsed,
            resume_name=resume_name,
            jd_title=jd_title,
            max_chars=max_chars_per_section,
        )

        try:
            client, model = cls._get_client()
            print(f"[LLMMatcher] 调用模型 {model}，prompt长度 {len(user_prompt)} 字符...")

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": MATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=20000,
                temperature=0.1,
                extra_body={"reasoning_effort": "none"},  # DeepSeek v4 关思考：超长思考致 content 空返回
            )
            result_text = (response.choices[0].message.content or "").strip()

            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if not json_match:
                print(f"[LLMMatcher] 未找到JSON，原始返回前300字: {result_text[:300]}")
                return None

            data = json.loads(json_match.group())
            return cls._build_result(data)

        except Exception as e:
            print(f"[LLMMatcher] LLM调用失败: {e}")
            return None

    @classmethod
    def _build_segmented_prompt(
        cls,
        resume_text: str,
        jd_text: str,
        resume_data: object,
        jd_parsed: object,
        resume_name: str,
        jd_title: str,
        max_chars: int,
    ) -> str:
        """构建结构化分段prompt - 按维度组织简历和JD内容"""

        parts = []

        name_tag = f" - {resume_name}" if resume_name else ""
        jd_tag = f" - {jd_title}" if jd_title else ""
        parts.append(f"# 简历与JD匹配分析任务{name_tag} x{jd_tag}\n")

        parts.append("## 分段一：候选人简历\n")
        if resume_data is not None:
            parts.append(cls._fmt_resume_sections(resume_data, max_chars))
        else:
            parts.append(resume_text[:max_chars])

        parts.append("\n## 分段二：目标岗位JD\n")
        if jd_parsed is not None:
            parts.append(cls._fmt_jd_sections(jd_parsed, max_chars))
        else:
            parts.append(jd_text[:max_chars])

        parts.append("""
## 分段三：逐维度对比分析指令

请严格按照system prompt中的五个维度和评分标准，逐一分析并给出分数：

1. 维度一：技术栈与硬技能匹配 - 逐项对比JD的技术要求与简历的技能清单
2. 维度二：工作经验与项目复杂度 - 对比工作年限、项目复杂度、行业相关性
3. 维度三：学历与专业背景 - 对比学历等级和专业匹配度
4. 维度四：软技能与综合素质 - 对比沟通、管理、协作等软性能力
5. 维度五：综合印象 - 简历完整度、亮点突出度、加分项

每个维度给出具体分数、评分依据（what matched / what's missing），
然后按权重计算综合得分。

请直接输出JSON，不要任何其他内容。""")

        return "\n".join(parts)

    @classmethod
    def _fmt_resume_sections(cls, resume_data, max_chars: int) -> str:
        """将ResumeData格式化为分段文本"""
        lines = []
        total = [0]

        def add(text: str):
            if total[0] >= max_chars:
                return
            truncated = text[:max_chars - total[0]] if total[0] + len(text) > max_chars else text
            lines.append(truncated)
            total[0] += len(truncated)

        rd = resume_data

        basic = []
        if rd.name:
            basic.append(f"姓名: {rd.name}")
        if rd.job_objective:
            basic.append(f"求职意向: {rd.job_objective}")
        if rd.current_location:
            basic.append(f"所在地: {rd.current_location}")
        if basic:
            add("### 基本信息\n" + "\n".join(basic) + "\n")

        if rd.self_evaluation:
            add(f"### 自我评价\n{rd.self_evaluation[:500]}\n")

        if rd.skills:
            skill_text = "### 技能清单\n" + "、".join(str(s) for s in rd.skills[:30])
            add(skill_text + "\n")

        if rd.work_experience:
            add(f"### 工作经历（共{len(rd.work_experience)}段）\n")
            for i, exp in enumerate(rd.work_experience[:5], 1):
                if total[0] >= max_chars:
                    break
                block = f"[{i}] {exp.get('company', '')} | {exp.get('position', '')} | {exp.get('start', '')}-{exp.get('end', '')}\n"
                for r in exp.get("responsibilities", [])[:5]:
                    block += f"  - {r}\n"
                add(block)

        if rd.project_experience:
            add(f"### 项目经历（共{len(rd.project_experience)}个）\n")
            for i, proj in enumerate(rd.project_experience[:5], 1):
                if total[0] >= max_chars:
                    break
                block = f"[{i}] {proj.get('name', '')}"
                if proj.get("role"):
                    block += f" | 角色: {proj['role']}"
                block += "\n"
                if proj.get("description"):
                    block += f"  描述: {proj['description'][:200]}\n"
                for h in proj.get("highlights", [])[:3]:
                    block += f"  - {h}\n"
                add(block)

        if rd.education:
            add("### 教育背景\n")
            for edu in rd.education[:3]:
                add(f"- {edu.get('school', '')} | {edu.get('degree', '')} | {edu.get('major', '')} | {edu.get('start', '')}-{edu.get('end', '')}\n")

        return "\n".join(lines)

    @classmethod
    def _fmt_jd_sections(cls, jd_parsed, max_chars: int) -> str:
        """将JDParsedResult格式化为分段文本"""
        lines = []
        total = [0]

        def add(text: str):
            if total[0] >= max_chars:
                return
            truncated = text[:max_chars - total[0]] if total[0] + len(text) > max_chars else text
            lines.append(truncated)
            total[0] += len(truncated)

        jd = jd_parsed

        basic = []
        if jd.job_title:
            basic.append(f"岗位: {jd.job_title}")
        if jd.company_name:
            basic.append(f"公司: {jd.company_name}")
        if jd.location:
            basic.append(f"地点: {jd.location}")
        if jd.salary:
            basic.append(f"薪资: {jd.salary}")
        if basic:
            add("### 基本信息\n" + "\n".join(basic) + "\n")

        req_meta = []
        if jd.education:
            req_meta.append(f"学历要求: {jd.education}")
        if jd.experience:
            req_meta.append(f"经验要求: {jd.experience}")
        if req_meta:
            add("### 硬性条件\n" + "\n".join(req_meta) + "\n")

        if jd.responsibilities:
            add(f"### 岗位职责（{len(jd.responsibilities)}条）\n")
            for i, r in enumerate(jd.responsibilities[:15], 1):
                add(f"{i}. {r}\n")

        if jd.requirements:
            add(f"### 任职要求（{len(jd.requirements)}条）\n")
            for i, r in enumerate(jd.requirements[:15], 1):
                add(f"{i}. {r}\n")

        return "\n".join(lines)

    @classmethod
    def _build_result(cls, data: dict) -> MatchResult:
        """将LLM返回的字典转换为MatchResult"""
        result = MatchResult()

        result.overall_score = float(data.get("overall_score", 0))
        result.score_level = str(data.get("score_level", "中等"))

        dim_scores = data.get("dimension_scores", {})
        if isinstance(dim_scores, dict):
            tech = dim_scores.get("tech_stack", {})
            soft = dim_scores.get("soft_skills", {})
            if isinstance(tech, dict):
                result.tech_match_score = float(tech.get("score", 50))
            if isinstance(soft, dict):
                result.soft_skill_score = float(soft.get("score", 50))

        if "tech_match_score" in data:
            result.tech_match_score = float(data["tech_match_score"])
        if "soft_skill_score" in data:
            result.soft_skill_score = float(data["soft_skill_score"])

        result.education_match = bool(data.get("education_match", True))
        result.experience_match = bool(data.get("experience_match", True))

        matched = data.get("matched_keywords", [])
        if isinstance(matched, list):
            result.matched_keywords = [str(k).strip() for k in matched if k]
        result.matched_count = len(result.matched_keywords) or int(data.get("matched_count", 0))

        unmatched = data.get("unmatched_keywords", [])
        if isinstance(unmatched, list):
            result.unmatched_jd_keywords = [str(k).strip() for k in unmatched if k]

        result.total_jd_keywords = int(data.get("total_jd_keywords",
            result.matched_count + len(result.unmatched_jd_keywords)))
        result.total_resume_keywords = int(data.get("total_resume_keywords", 0))

        cat_scores = data.get("category_scores", {})
        if isinstance(cat_scores, dict):
            result.category_scores = cat_scores

        highlights = data.get("highlights", [])
        if isinstance(highlights, list):
            result.resume_highlights = [str(h).strip() for h in highlights if h]
        elif isinstance(highlights, str):
            result.resume_highlights = [line.strip() for line in highlights.split("\n") if line.strip()]

        suggestions = data.get("suggestions", [])
        if isinstance(suggestions, list):
            result.suggestions = [str(s).strip() for s in suggestions if s]
        elif isinstance(suggestions, str):
            result.suggestions = [s.strip() for s in suggestions.split("\n") if s.strip()]

        return result

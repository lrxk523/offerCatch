"""JD 文本解析器 - 清洗排版、提取结构化字段、区分职责/要求"""

import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

from app.skills.common.text_cleaner import JDTextCleaner


@dataclass
class JDParsedResult:
    """JD 解析结果"""
    # 核心字段
    job_title: str = ""               # 岗位名称
    location: str = ""                # 工作地点
    salary: str = ""                  # 薪资范围
    responsibilities: List[str] = field(default_factory=list)  # 岗位职责
    requirements: List[str] = field(default_factory=list)      # 任职要求

    # 扩展字段
    company_name: str = ""            # 公司名称
    experience: str = ""              # 经验要求
    education: str = ""               # 学历要求
    benefits: List[str] = field(default_factory=list)          # 福利待遇
    other_info: str = ""              # 其他补充信息

    # 元数据
    raw_text_preview: str = ""        # 原始文本预览
    cleaned_text: str = ""            # 清洗后的完整文本
    parse_confidence: float = 0.0     # 解析置信度


class JDSectionSplitter:
    """JD 段落分割器 - 自动区分「职责」「要求」等区块"""

    # 职责段落的标题关键词
    RESPONSIBILITY_HEADERS = [
        "岗位职责", "工作职责", "职责描述", "工作内容",
        "职位描述", "岗位描述", "工作描述", "职位职责",
        "主要职责", "职责范围", "您将负责", "你需要做",
        "responsibilities", "job description", "duties",
        "主要工作", "岗位工作",
    ]

    # 要求段落的标题关键词
    REQUIREMENT_HEADERS = [
        "任职要求", "岗位要求", "职位要求", "任职资格",
        "能力要求", "招聘要求", "我们需要", "希望你",
        "基本要求", "必备条件", "资格要求", "岗位条件",
        "requirements", "qualifications", "任职条件",
        "技能要求", "经验要求", "我们需要你", "希望你具备",
        "职位要求", "基础要求", "核心要求",
    ]

    # 薪资相关关键词
    SALARY_HEADERS = [
        "薪资", "薪酬", "待遇", "薪资待遇", "薪酬福利",
        "薪资范围", "薪酬范围", "月薪", "年薪",
        "salary", "compensation",
    ]

    # 地点关键词
    LOCATION_HEADERS = [
        "工作地点", "工作地址", "办公地点", "上班地点",
        "地点", "地址", "location", "办公地址",
    ]

    # 福利关键词
    BENEFIT_HEADERS = [
        "福利", "福利待遇", "公司福利", "员工福利",
        "benefits", "perks", "我们提供",
    ]

    # 学历关键词
    EDUCATION_KEYWORDS = [
        "本科", "硕士", "博士", "大专", "学历",
        "本科及以上", "硕士及以上", "统招本科",
        "学士", "硕士", "博士",
    ]

    # 经验关键词
    EXPERIENCE_KEYWORDS = [
        "年以上", "年经验", "年工作经验", "年相关经验",
        "应届", "实习", "毕业生",
    ]

    @classmethod
    def split(cls, cleaned_text: str) -> Dict[str, any]:
        """将清洗后的文本分割为结构化区块"""
        lines = cleaned_text.split("\n")

        sections = {
            "header": [],       # 标题区 (岗位名/公司等)
            "responsibility": [],
            "requirement": [],
            "salary": [],
            "location": [],
            "benefit": [],
            "other": [],
        }

        current_section = "header"
        current_header_text = ""

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 检查是否是区块标题
            section_type = cls._detect_section(stripped)
            if section_type:
                current_section = section_type
                current_header_text = stripped
                continue

            # 检查是否是列表项
            is_list_item = bool(re.match(r"^[\d]+[\.\)、]|^[-•·●○◆◇▪▸►✓✔☑]", stripped))

            # 去除列表标记
            clean_line = re.sub(r"^[\d]+[\.\)、]\s*", "", stripped)
            clean_line = re.sub(r"^[-•·●○◆◇▪▸►✓✔☑]\s*", "", clean_line)

            sections[current_section].append({
                "raw": stripped,
                "clean": clean_line,
                "is_list_item": is_list_item,
                "section": current_section,
            })

        return sections

    @classmethod
    def _detect_section(cls, line: str) -> Optional[str]:
        """检测该行属于哪个区块类型（模糊匹配，容忍 OCR 噪声）"""
        line_lower = line.lower().strip()
        # 移除空格，OCR 可能在中文词间插入空格
        line_compact = line_lower.replace(" ", "")

        # 先精确匹配
        for header in cls.REQUIREMENT_HEADERS:
            if header in line_compact:
                return "requirement"
        for header in cls.RESPONSIBILITY_HEADERS:
            if header in line_compact:
                return "responsibility"
        for header in cls.SALARY_HEADERS:
            if header in line_compact:
                return "salary"
        for header in cls.LOCATION_HEADERS:
            if header in line_compact:
                return "location"
        for header in cls.BENEFIT_HEADERS:
            if header in line_compact:
                return "benefit"

        # 模糊匹配：标题关键词可能被 OCR 拆开
        if "岗位" in line_compact or "职位" in line_compact:
            if "职责" in line_compact or "描述" in line_compact or "内容" in line_compact:
                return "responsibility"
            if "要求" in line_compact or "资格" in line_compact or "条件" in line_compact:
                return "requirement"
        if "任职" in line_compact and ("要求" in line_compact or "资格" in line_compact):
            return "requirement"
        if "工作" in line_compact and "内容" in line_compact:
            return "responsibility"

        return None


class JDExtractor:
    """JD 信息提取器 - 从结构化区块中提取关键字段"""

    @classmethod
    def extract(cls, cleaned_text: str, sections: Dict[str, any]) -> JDParsedResult:
        result = JDParsedResult()
        result.cleaned_text = cleaned_text
        result.raw_text_preview = cleaned_text[:500]

        # 1. 提取岗位名称
        result.job_title = cls._extract_job_title(cleaned_text, sections)

        # 2. 提取地点
        result.location = cls._extract_location(cleaned_text, sections)

        # 3. 提取薪资
        result.salary = cls._extract_salary(cleaned_text, sections)

        # 4. 提取公司名称
        result.company_name = cls._extract_company(cleaned_text, sections)

        # 5. 提取岗位职责
        result.responsibilities = cls._extract_list_items(sections.get("responsibility", []))

        # 6. 提取任职要求
        result.requirements = cls._extract_list_items(sections.get("requirement", []))

        # 7. 提取福利
        result.benefits = cls._extract_list_items(sections.get("benefit", []))

        # 8. 提取学历要求
        result.education = cls._extract_education(cleaned_text)

        # 9. 提取经验要求
        result.experience = cls._extract_experience(cleaned_text)

        # 10. 计算置信度
        result.parse_confidence = cls._calculate_confidence(result)

        return result

    @classmethod
    def _extract_job_title(cls, text: str, sections: Dict) -> str:
        """提取岗位名称"""
        lines = text.split("\n")

        # 策略1: 查找明确的岗位名关键词
        title_patterns = [
            r"^(?:职位|岗位|招聘)[：:]\s*(.+)$",
            r"^(?:职位名称|岗位名称|招聘岗位)[：:]\s*(.+)$",
        ]
        for pattern in title_patterns:
            for line in lines:
                match = re.search(pattern, line)
                if match:
                    return match.group(1).strip()

        # 策略2: 前几行中出现常见的岗位后缀
        job_suffixes = [
            "工程师", "经理", "总监", "主管", "专员", "助理",
            "设计师", "分析师", "运营", "开发", "架构师", "顾问",
            "产品经理", "项目经理", "实习生", "管培生",
            "developer", "engineer", "manager", "designer",
        ]

        for line in lines[:15]:
            line = line.strip()
            if len(line) > 30 or len(line) < 2:
                continue
            for suffix in job_suffixes:
                if suffix in line:
                    return line

        # 策略3: 第一行作为候选
        for line in lines[:5]:
            line = line.strip()
            if 2 <= len(line) <= 40 and not line.startswith(("公司", "【")):
                return line

        return ""

    @classmethod
    def _extract_location(cls, text: str, sections: Dict) -> str:
        """提取工作地点"""
        # 策略1: 从 location 区块提取
        loc_items = sections.get("location", [])
        for item in loc_items:
            return item["clean"]

        # 策略2: 正则匹配
        patterns = [
            r"(?:工作地点|工作地址|办公地点|地点|地址)[：:]\s*(.+?)(?:\n|$)",
            r"(?:base[：:]\s*)(.+?)(?:\n|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # 策略3: 城市名匹配
        cities = [
            "北京", "上海", "深圳", "广州", "杭州", "成都", "南京",
            "武汉", "西安", "苏州", "重庆", "长沙", "天津", "郑州",
            "东莞", "青岛", "厦门", "合肥", "佛山", "济南", "福州",
            "大连", "珠海", "无锡", "宁波",
        ]
        for city in cities:
            # 匹配 "城市·区域" 或 "城市-区域" 格式
            match = re.search(rf"{city}[·\-]?\S*区?", text[:500])
            if match:
                return match.group(0)

        return ""

    @classmethod
    def _extract_salary(cls, text: str, sections: Dict) -> str:
        """提取薪资"""
        # 策略1: 从 salary 区块提取
        sal_items = sections.get("salary", [])
        for item in sal_items:
            return item["clean"]

        # 策略2: 正则匹配
        patterns = [
            # 月薪格式: 15k-25k, 15-25K, 15K-25K
            r"(\d{1,3}\s*[kK]\s*[-~至到]\s*\d{1,3}\s*[kK])",
            # 数字格式: 15000-25000
            r"(\d{4,6}\s*[-~至到]\s*\d{4,6})",
            # 年薪格式: 20-40万
            r"(\d{1,3}\s*[-~至到]\s*\d{1,3}\s*万)",
            # 月薪范围: 15k-25k·14薪
            r"(\d{1,3}\s*[kK]\s*[-~至到]\s*\d{1,3}\s*[kK]\s*[·•]\s*\d{1,2}\s*薪)",
            # 薪资关键字开头
            r"(?:薪资|薪酬|月薪|年薪)[：:]\s*(.+?)(?:\n|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text[:1000])
            if match:
                return match.group(1).strip() if match.lastindex else match.group(0).strip()

        return ""

    @classmethod
    def _extract_company(cls, text: str, sections: Dict) -> str:
        """提取公司名称"""
        patterns = [
            r"(?:公司|企业)[：:]\s*(.+?)(?:\n|$)",
            r"【(.+?)】",
        ]
        for pattern in patterns:
            match = re.search(pattern, text[:500])
            if match:
                return match.group(1).strip()
        return ""

    @classmethod
    def _extract_list_items(cls, items: List[Dict]) -> List[str]:
        """从区块 items 中提取纯文本列表"""
        result = []
        for item in items:
            text = item["clean"]
            # 跳过区块标题本身
            if cls._is_section_header(text):
                continue
            if len(text) >= 3:
                result.append(text)
        return result

    @classmethod
    def _is_section_header(cls, text: str) -> bool:
        """判断是否是区块标题"""
        text_lower = text.lower().strip()
        all_headers = (
            JDSectionSplitter.RESPONSIBILITY_HEADERS
            + JDSectionSplitter.REQUIREMENT_HEADERS
            + JDSectionSplitter.SALARY_HEADERS
            + JDSectionSplitter.LOCATION_HEADERS
            + JDSectionSplitter.BENEFIT_HEADERS
        )
        return text_lower in all_headers

    @classmethod
    def _extract_education(cls, text: str) -> str:
        """提取学历要求 -- 以关键词为中心取短句"""
        delimiters = "，,。\n；;"
        for kw in JDSectionSplitter.EDUCATION_KEYWORDS:
            match = re.search(kw, text)
            if not match:
                continue
            start = match.start()
            end = match.end()

            # 向左找最近的分隔符
            left = max(text.rfind(c, 0, start) for c in delimiters)
            if left == -1:
                left = max(0, start - 30)

            # 向右找最近的分隔符
            right = -1
            for c in delimiters:
                p = text.find(c, end)
                if p != -1 and (right == -1 or p < right):
                    right = p
            if right == -1:
                right = min(len(text), end + 30)

            snippet = text[left + 1:right].strip()
            if len(snippet) > 3:
                return snippet
        return ""

    @classmethod
    def _extract_experience(cls, text: str) -> str:
        """提取经验要求 -- 以关键词为中心取短句"""
        delimiters = "，,。\n；;"
        for kw in JDSectionSplitter.EXPERIENCE_KEYWORDS:
            match = re.search(kw, text)
            if not match:
                continue
            start = match.start()
            end = match.end()

            left = max(text.rfind(c, 0, start) for c in delimiters)
            if left == -1:
                left = max(0, start - 30)

            right = -1
            for c in delimiters:
                p = text.find(c, end)
                if p != -1 and (right == -1 or p < right):
                    right = p
            if right == -1:
                right = min(len(text), end + 30)

            snippet = text[left + 1:right].strip()
            if len(snippet) > 3:
                return snippet
        return ""

    @classmethod
    def _calculate_confidence(cls, result: JDParsedResult) -> float:
        """根据提取结果的完整度计算置信度"""
        score = 0.0
        weights = {
            "job_title": 0.20,
            "responsibilities": 0.25,
            "requirements": 0.25,
            "location": 0.10,
            "salary": 0.10,
            "education": 0.05,
            "experience": 0.05,
        }
        for field, weight in weights.items():
            value = getattr(result, field)
            if value:
                if isinstance(value, list):
                    score += weight * min(len(value) / 5, 1.0)
                elif isinstance(value, str):
                    score += weight
        return round(score, 2)

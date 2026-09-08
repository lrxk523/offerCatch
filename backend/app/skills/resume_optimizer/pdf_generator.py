"""简历 PDF 生成器 - 将优化后的简历数据渲染为专业排版的 PDF 文件"""

import os
import uuid
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ---- 中文字体注册 ----
def _register_chinese_font():
    """注册中文字体，优先使用系统字体"""
    font_paths = [
        ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
        ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
        ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
        ("SimSun", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        ("SimSun", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        ("SimSun", "/System/Library/Fonts/PingFang.ttc"),
    ]
    for name, path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                continue
    # 兜底：尝试任何可用中文字体
    font_dir = "C:/Windows/Fonts"
    if os.path.exists(font_dir):
        for f in os.listdir(font_dir):
            if f.endswith((".ttf", ".ttc")) and any(
                k in f.lower() for k in ["hei", "song", "kai", "ming", "fang", "yuan"]
            ):
                try:
                    path = os.path.join(font_dir, f)
                    pdfmetrics.registerFont(TTFont("ChineseFont", path))
                    return "ChineseFont"
                except Exception:
                    continue
    return "Helvetica"  # 最终兜底


_FONT_NAME = _register_chinese_font()


# ---- 样式定义 ----
ACCENT = HexColor("#1a56db")      # 深蓝主色
ACCENT_LIGHT = HexColor("#e8f0fe")
DARK = HexColor("#1f2937")
GRAY = HexColor("#6b7280")
LIGHT_GRAY = HexColor("#e5e7eb")
BG_GRAY = HexColor("#f9fafb")


def _style(name: str, **kwargs) -> ParagraphStyle:
    """快速创建 ParagraphStyle"""
    defaults = {
        "fontName": _FONT_NAME,
        "fontSize": 10,
        "leading": 16,
        "textColor": DARK,
        "alignment": TA_LEFT,
    }
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


# 预定义样式
STYLE_NAME = _style("Name", fontSize=22, leading=28, textColor=ACCENT, alignment=TA_CENTER)
STYLE_TARGET = _style("Target", fontSize=11, leading=16, textColor=GRAY, alignment=TA_CENTER)
STYLE_SECTION = _style("Section", fontSize=13, leading=18, textColor=ACCENT, spaceBefore=12, spaceAfter=4)
STYLE_BODY = _style("Body", fontSize=9.5, leading=15, textColor=DARK)
STYLE_BODY_SMALL = _style("BodySmall", fontSize=9, leading=14, textColor=DARK)
STYLE_INFO = _style("Info", fontSize=9.5, leading=14, textColor=GRAY)
STYLE_BULLET = _style("Bullet", fontSize=9.5, leading=15, textColor=DARK, leftIndent=12, bulletIndent=4, spaceAfter=2)
STYLE_COMPANY = _style("Company", fontSize=10.5, leading=16, textColor=DARK)
STYLE_DATE = _style("Date", fontSize=9, leading=14, textColor=GRAY)
STYLE_POSITION = _style("Position", fontSize=9.5, leading=14, textColor=ACCENT)


class ResumePDFGenerator:
    """简历 PDF 生成器"""

    OUTPUT_DIR = "static/pdf"

    @classmethod
    def generate(cls, data: dict, optimized: dict = None) -> str:
        """
        生成 PDF 简历文件。
        返回 PDF 文件的访问路径（相对 web 根目录）。
        """
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)

        filename = f"resume_{uuid.uuid4().hex[:12]}.pdf"
        filepath = os.path.join(cls.OUTPUT_DIR, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            title="优化简历",
            author="OfferCatch",
        )

        story = []
        original = data.get("original", data) if data else {}
        optimized = optimized or {}

        # ---- 个人信息 ----
        cls._add_header(story, original)
        cls._add_divider(story)

        # ---- 求职意向 ----
        cls._add_job_objective(story, original)

        # ---- 教育经历 ----
        cls._add_education(story, original)

        # ---- 工作经历 ----
        cls._add_work_experience(story, optimized or data or {})

        # ---- 项目经历 ----
        cls._add_project_experience(story, optimized or data or {})

        # ---- 技能 ----
        cls._add_skills(story, original)

        # ---- 证书 ----
        cls._add_certifications(story, original)

        # ---- 自我评价 ----
        cls._add_self_evaluation(story, optimized or data or {})

        doc.build(story)
        return f"/pdf/{filename}"

    @classmethod
    def _add_header(cls, story: list, data: dict):
        """个人信息头部"""
        name = data.get("name", "未命名")
        story.append(Paragraph(name, STYLE_NAME))
        story.append(Spacer(1, 2 * mm))

        contact_parts = []
        if data.get("phone"):
            contact_parts.append(f"📱 {data['phone']}")
        if data.get("email"):
            contact_parts.append(f"✉ {data['email']}")
        if data.get("age"):
            contact_parts.append(f"{data['age']}岁")
        if data.get("current_location"):
            contact_parts.append(f"📍 {data['current_location']}")
        contact_line = "  ·  ".join(contact_parts)
        story.append(Paragraph(contact_line, STYLE_INFO))
        story.append(Spacer(1, 6 * mm))

    @classmethod
    def _add_divider(cls, story: list):
        story.append(HRFlowable(
            width="100%",
            thickness=1,
            color=LIGHT_GRAY,
            spaceBefore=2,
            spaceAfter=8,
        ))

    @classmethod
    def _add_section_title(cls, story: list, title: str):
        story.append(Paragraph(title, STYLE_SECTION))
        story.append(HRFlowable(
            width="100%",
            thickness=1,
            color=ACCENT_LIGHT,
            spaceBefore=1,
            spaceAfter=4,
        ))

    @classmethod
    def _add_job_objective(cls, story: list, data: dict):
        objective = data.get("job_objective", "")
        salary = data.get("desired_salary", "")
        location = data.get("current_location", "")
        if not objective and not salary:
            return
        cls._add_section_title(story, "求职意向")
        parts = []
        if objective:
            parts.append(f"意向岗位：{objective}")
        if salary:
            parts.append(f"期望薪资：{salary}")
        if location:
            parts.append(f"期望城市：{location}")
        story.append(Paragraph("  ·  ".join(parts), STYLE_BODY))
        story.append(Spacer(1, 4 * mm))

    @classmethod
    def _add_education(cls, story: list, data: dict):
        edu_list = data.get("education", [])
        if not edu_list:
            return
        cls._add_section_title(story, "教育经历")
        for edu in edu_list:
            line = ""
            if edu.get("school"):
                line += edu["school"]
            if edu.get("degree"):
                line += f"  |  {edu['degree']}"
            if edu.get("major"):
                line += f"  ·  {edu['major']}"
            if edu.get("start") or edu.get("end"):
                time_str = f"{edu.get('start', '')} - {edu.get('end', '')}"
                line += f"  |  {time_str}"
            story.append(Paragraph(line, STYLE_BODY_SMALL))
        story.append(Spacer(1, 4 * mm))

    @classmethod
    def _add_work_experience(cls, story: list, data: dict):
        exp_list = data.get("work_experience", [])
        if not exp_list:
            return
        cls._add_section_title(story, "工作经历")
        for exp in exp_list:
            # 公司 & 时间
            company = exp.get("company", "")
            position = exp.get("position", "")
            start = exp.get("start", "")
            end = exp.get("end", "")

            header_text = company
            if position:
                header_text += f"  |  {position}"
            if start or end:
                header_text += f"  |  {start} - {end}"
            story.append(Paragraph(header_text, STYLE_COMPANY))

            # 职责
            resp_list = exp.get("responsibilities", [])
            if resp_list:
                for resp in resp_list:
                    if resp:
                        story.append(Paragraph(f"● {resp}", STYLE_BULLET))
            story.append(Spacer(1, 2 * mm))

    @classmethod
    def _add_project_experience(cls, story: list, data: dict):
        proj_list = data.get("project_experience", [])
        if not proj_list:
            return
        cls._add_section_title(story, "项目经历")
        for proj in proj_list:
            name = proj.get("name", "")
            role = proj.get("role", "")
            start = proj.get("start", "")
            end = proj.get("end", "")

            header = name
            if role:
                header += f"  |  {role}"
            if start or end:
                header += f"  |  {start} - {end}"
            story.append(Paragraph(header, STYLE_COMPANY))

            highlights = proj.get("highlights", [])
            if highlights:
                for hl in highlights:
                    if hl:
                        story.append(Paragraph(f"● {hl}", STYLE_BULLET))
            story.append(Spacer(1, 2 * mm))

    @classmethod
    def _add_skills(cls, story: list, data: dict):
        skills = data.get("skills", []) or []
        if not skills:
            return
        cls._add_section_title(story, "专业技能")
        skill_text = "  ·  ".join(str(s) for s in skills if s)
        story.append(Paragraph(skill_text, STYLE_BODY_SMALL))
        story.append(Spacer(1, 4 * mm))

    @classmethod
    def _add_certifications(cls, story: list, data: dict):
        certs = data.get("certifications", [])
        if not certs:
            return
        cls._add_section_title(story, "证书与荣誉")
        cert_text = "  ·  ".join(certs)
        story.append(Paragraph(cert_text, STYLE_BODY_SMALL))
        story.append(Spacer(1, 4 * mm))

    @classmethod
    def _add_self_evaluation(cls, story: list, data: dict):
        eval_text = data.get("self_evaluation", "")
        if not eval_text:
            return
        cls._add_section_title(story, "自我评价")
        story.append(Paragraph(eval_text, STYLE_BODY))

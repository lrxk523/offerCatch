"""可视化引擎 - 生成简历与JD匹配度可视化HTML报告"""

import json
import math
from typing import Dict, List

from .matcher import MatchResult


class MatchVisualizer:
    """匹配度可视化引擎 - 生成精美的HTML报告"""

    # 配色方案
    COLORS = {
        "primary": "#4F46E5",        # 靛蓝
        "primary_light": "#818CF8",
        "success": "#10B981",        # 翠绿
        "success_light": "#6EE7B7",
        "warning": "#F59E0B",       # 琥珀
        "warning_light": "#FCD34D",
        "danger": "#EF4444",         # 红色
        "danger_light": "#FCA5A5",
        "bg": "#F8FAFC",
        "card_bg": "#FFFFFF",
        "text": "#1E293B",
        "text_secondary": "#64748B",
        "border": "#E2E8F0",
        "matched": "#10B981",
        "missing": "#F59E0B",
    }

    @classmethod
    def generate(cls, result: MatchResult, resume_name: str = "", jd_title: str = "") -> str:
        """生成完整的可视化HTML报告"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>简历与JD匹配度分析报告</title>
<style>
{cls._generate_css()}
</style>
</head>
<body>
<div class="container">
  {cls._generate_header(result, resume_name, jd_title)}
  {cls._generate_score_circle(result)}
  {cls._generate_dimension_scores(result)}
  {cls._generate_keyword_analysis(result)}
  {cls._generate_category_chart(result)}
  {cls._generate_highlights_and_suggestions(result)}
</div>
<script>
{cls._generate_js()}
</script>
</body>
</html>"""

    @classmethod
    def _generate_css(cls) -> str:
        return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", "Helvetica Neue", sans-serif;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  padding: 24px 16px 60px;
  color: #1E293B;
}
.container {
  max-width: 880px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ---- 卡片组件 ---- */
.card {
  background: #FFFFFF;
  border-radius: 16px;
  padding: 28px 32px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.04);
  transition: transform 0.2s;
}
.card:hover { transform: translateY(-2px); }
.card-title {
  font-size: 18px;
  font-weight: 700;
  color: #1E293B;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-title .icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

/* ---- 头部 ---- */
.header {
  text-align: center;
  color: #FFFFFF;
}
.header h1 {
  font-size: 28px;
  font-weight: 800;
  margin-bottom: 4px;
}
.header .subtitle {
  font-size: 14px;
  opacity: 0.85;
}
.header .meta {
  margin-top: 12px;
  display: flex;
  justify-content: center;
  gap: 16px;
  flex-wrap: wrap;
}
.header .tag {
  background: rgba(255,255,255,0.2);
  backdrop-filter: blur(10px);
  padding: 4px 14px;
  border-radius: 20px;
  font-size: 13px;
}

/* ---- 得分环 ---- */
.score-section {
  display: flex;
  align-items: center;
  gap: 40px;
  flex-wrap: wrap;
  justify-content: center;
}
.score-circle-wrapper {
  position: relative;
  width: 160px;
  height: 160px;
  flex-shrink: 0;
}
.score-circle {
  transform: rotate(-90deg);
}
.score-circle .bg { fill: none; stroke: #E2E8F0; stroke-width: 12; }
.score-circle .fill { fill: none; stroke-width: 12; stroke-linecap: round; }
.score-value {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}
.score-value .number {
  font-size: 40px;
  font-weight: 800;
  line-height: 1;
}
.score-value .level {
  font-size: 13px;
  margin-top: 2px;
}
.score-summary {
  flex: 1;
  min-width: 240px;
}
.score-summary .stat-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #F1F5F9;
  font-size: 14px;
}
.score-summary .stat-row:last-child { border-bottom: none; }
.score-summary .stat-label { color: #64748B; }
.score-summary .stat-value { font-weight: 600; }

/* ---- 维度分数条 ---- */
.dimension-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.dim-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dim-header {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 500;
}
.dim-header .name { color: #475569; }
.dim-header .val { font-weight: 700; }
.dim-bar {
  height: 8px;
  border-radius: 4px;
  background: #E2E8F0;
  overflow: hidden;
}
.dim-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 1s ease-out;
}

/* ---- 关键词分析 ---- */
.kw-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.kw-panel h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.kw-panel .count-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.kw-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.kw-tag {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.kw-tag.matched {
  background: #D1FAE5;
  color: #065F46;
  border: 1px solid #A7F3D0;
}
.kw-tag.unmatched {
  background: #FEF3C7;
  color: #92400E;
  border: 1px solid #FDE68A;
}

/* ---- 分类图表 ---- */
.cat-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cat-table th {
  text-align: left;
  padding: 10px 12px;
  background: #F8FAFC;
  font-weight: 600;
  color: #475569;
  border-bottom: 2px solid #E2E8F0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.cat-table td { padding: 10px 12px; border-bottom: 1px solid #F1F5F9; }
.cat-bar-wrapper { display: flex; align-items: center; gap: 8px; }
.cat-bar-bg {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #E2E8F0;
  min-width: 80px;
}
.cat-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 1s ease-out;
}
.cat-bar-text { font-weight: 600; min-width: 38px; text-align: right; font-size: 12px; }

/* ---- 亮点与建议 ---- */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.highlight-item {
  padding: 10px 14px;
  background: #F0FDF4;
  border-radius: 8px;
  font-size: 13px;
  color: #065F46;
  margin-bottom: 8px;
  border-left: 3px solid #10B981;
}
.suggestion-item {
  padding: 10px 14px;
  background: #FFF7ED;
  border-radius: 8px;
  font-size: 13px;
  color: #9A3412;
  margin-bottom: 8px;
  border-left: 3px solid #F97316;
}

/* 响应式 */
@media (max-width: 640px) {
  .dimension-grid, .kw-layout, .two-col { grid-template-columns: 1fr; }
  .score-section { flex-direction: column; text-align: center; }
  .card { padding: 20px 18px; }
}
"""

    @classmethod
    def _generate_header(cls, result: MatchResult, resume_name: str, jd_title: str) -> str:
        title = f"{resume_name} × {jd_title}" if resume_name and jd_title else "简历与岗位匹配度分析"
        return f"""
<div class="header">
  <h1>📊 简历与JD匹配度分析</h1>
  <p class="subtitle">{title}</p>
  <div class="meta">
    <span class="tag">📄 简历关键词: {result.total_resume_keywords} 个</span>
    <span class="tag">📋 JD关键词: {result.total_jd_keywords} 个</span>
    <span class="tag">✅ 匹配: {result.matched_count} 个</span>
  </div>
</div>"""

    @classmethod
    def _generate_score_circle(cls, result: MatchResult) -> str:
        score = result.overall_score
        circumference = 2 * math.pi * 54

        # 颜色
        if score >= 75:
            color = cls.COLORS["success"]
        elif score >= 60:
            color = cls.COLORS["warning"]
        else:
            color = cls.COLORS["danger"]

        dash_offset = circumference * (1 - score / 100)

        level_emoji = {
            "极高": "🏆", "高": "🎯", "中等": "📌", "较低": "⚠️", "低": "❌",
        }.get(result.score_level, "")

        return f"""
<div class="card">
  <div class="card-title">
    <span class="icon" style="background:#EEF2FF;color:#4F46E5;">🎯</span>
    综合匹配度
  </div>
  <div class="score-section">
    <div class="score-circle-wrapper">
      <svg class="score-circle" width="160" height="160" viewBox="0 0 120 120">
        <circle class="bg" cx="60" cy="60" r="54"></circle>
        <circle class="fill" cx="60" cy="60" r="54"
          stroke="{color}"
          stroke-dasharray="{circumference}"
          stroke-dashoffset="{dash_offset}">
          <animate attributeName="stroke-dashoffset" from="{circumference}" to="{dash_offset}" dur="1s" fill="freeze"/>
        </circle>
      </svg>
      <div class="score-value">
        <div class="number" style="color:{color}">{score}</div>
        <div class="level">{level_emoji} {result.score_level}匹配</div>
      </div>
    </div>
    <div class="score-summary">
      <div class="stat-row">
        <span class="stat-label">📋 JD关键词总数</span>
        <span class="stat-value">{result.total_jd_keywords}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">✅ 简历匹配关键词</span>
        <span class="stat-value" style="color:#10B981">{result.matched_count}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">⚠️ 简历缺失关键词</span>
        <span class="stat-value" style="color:#F59E0B">{len(result.unmatched_jd_keywords)}</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">🔧 技术匹配度</span>
        <span class="stat-value">{result.tech_match_score}%</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">🎓 学历匹配</span>
        <span class="stat-value" style="color:{'#10B981' if result.education_match else '#EF4444'}">
          {'✅ 满足' if result.education_match else '❌ 不满足'}
        </span>
      </div>
      <div class="stat-row">
        <span class="stat-label">⏱️ 经验匹配</span>
        <span class="stat-value" style="color:{'#10B981' if result.experience_match else '#EF4444'}">
          {'✅ 满足' if result.experience_match else '❌ 不满足'}
        </span>
      </div>
    </div>
  </div>
</div>"""

    @classmethod
    def _generate_dimension_scores(cls, result: MatchResult) -> str:
        dimensions = [
            ("技术栈匹配", result.tech_match_score, "#4F46E5"),
            ("软技能匹配", result.soft_skill_score, "#8B5CF6"),
            ("学历匹配", 100 if result.education_match else 30, "#10B981"),
            ("经验匹配", 100 if result.experience_match else 40, "#F59E0B"),
        ]

        items = ""
        for name, score, color in dimensions:
            items += f"""
    <div class="dim-item">
      <div class="dim-header">
        <span class="name">{name}</span>
        <span class="val">{int(score)}%</span>
      </div>
      <div class="dim-bar">
        <div class="dim-fill" style="width:{score}%;background:{color};"></div>
      </div>
    </div>"""

        return f"""
<div class="card">
  <div class="card-title">
    <span class="icon" style="background:#F0FDF4;color:#10B981;">📈</span>
    维度分析
  </div>
  <div class="dimension-grid">{items}</div>
</div>"""

    @classmethod
    def _generate_keyword_analysis(cls, result: MatchResult) -> str:
        matched_tags = ""
        for kw in result.matched_keywords[:30]:
            matched_tags += f'<span class="kw-tag matched">{kw}</span>'

        unmatched_tags = ""
        for kw in result.unmatched_jd_keywords[:30]:
            unmatched_tags += f'<span class="kw-tag unmatched">{kw}</span>'

        more_matched = f'<span class="kw-tag matched">... 还有 {result.matched_count - 30} 个</span>' if result.matched_count > 30 else ""
        more_unmatched = f'<span class="kw-tag unmatched">... 还有 {len(result.unmatched_jd_keywords) - 30} 个</span>' if len(result.unmatched_jd_keywords) > 30 else ""

        return f"""
<div class="card">
  <div class="card-title">
    <span class="icon" style="background:#FFF7ED;color:#F97316;">🔑</span>
    关键词重合分析
  </div>
  <div class="kw-layout">
    <div class="kw-panel">
      <h3>
        ✅ 已匹配关键词
        <span class="count-badge" style="background:#D1FAE5;color:#065F46;">{result.matched_count}</span>
      </h3>
      <div class="kw-list">{matched_tags}{more_matched}</div>
    </div>
    <div class="kw-panel">
      <h3>
        ⚠️ 缺失关键词
        <span class="count-badge" style="background:#FEF3C7;color:#92400E;">{len(result.unmatched_jd_keywords)}</span>
      </h3>
      <div class="kw-list">{unmatched_tags}{more_unmatched}</div>
    </div>
  </div>
</div>"""

    @classmethod
    def _generate_category_chart(cls, result: MatchResult) -> str:
        rows = ""
        # 只显示JD有要求的分类
        for cat_name, cs in result.category_scores.items():
            if cs["jd_count"] == 0:
                continue
            score = cs["score"]
            if score >= 80:
                color = cls.COLORS["success"]
            elif score >= 50:
                color = cls.COLORS["warning"]
            else:
                color = cls.COLORS["danger"]

            rows += f"""
    <tr>
      <td style="font-weight:600">{cat_name}</td>
      <td style="color:#64748B;font-size:12px">JD要求 {cs['jd_count']} 项</td>
      <td>
        <div class="cat-bar-wrapper">
          <div class="cat-bar-bg">
            <div class="cat-bar-fill" style="width:{score}%;background:{color}"></div>
          </div>
          <span class="cat-bar-text" style="color:{color}">{score}%</span>
        </div>
      </td>
      <td style="font-size:12px;color:#64748B">匹配 {cs['matched_count']}/{cs['jd_count']}</td>
    </tr>"""

        return f"""
<div class="card">
  <div class="card-title">
    <span class="icon" style="background:#EEF2FF;color:#4F46E5;">📊</span>
    技术分类匹配明细
  </div>
  <div style="overflow-x:auto">
    <table class="cat-table">
      <thead>
        <tr><th>技术分类</th><th>要求</th><th>匹配率</th><th>详情</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>"""

    @classmethod
    def _generate_highlights_and_suggestions(cls, result: MatchResult) -> str:
        highlights_html = ""
        if result.resume_highlights:
            for h in result.resume_highlights:
                highlights_html += f'<div class="highlight-item">✅ {h}</div>'
        else:
            highlights_html = '<div class="highlight-item">✅ 持续优化简历，增加与目标岗位相关的关键词</div>'

        suggestions_html = ""
        if result.suggestions:
            for s in result.suggestions:
                suggestions_html += f'<div class="suggestion-item">💡 {s}</div>'
        else:
            suggestions_html = '<div class="suggestion-item">💡 你的简历与JD匹配度很高，继续保持！</div>'

        return f"""
<div class="card">
  <div class="card-title">
    <span class="icon" style="background:#FEF2F2;color:#EF4444;">💡</span>
    亮点与改进建议
  </div>
  <div class="two-col">
    <div>
      <h3 style="font-size:14px;font-weight:600;margin-bottom:12px;color:#065F46">🌟 匹配亮点</h3>
      {highlights_html}
    </div>
    <div>
      <h3 style="font-size:14px;font-weight:600;margin-bottom:12px;color:#9A3412">📝 改进建议</h3>
      {suggestions_html}
    </div>
  </div>
</div>"""

    @classmethod
    def _generate_js(cls) -> str:
        return """
// 入场动画
document.addEventListener('DOMContentLoaded', () => {
  const cards = document.querySelectorAll('.card');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
        }, i * 80);
      }
    });
  }, { threshold: 0.1 });

  cards.forEach(card => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(20px)';
    card.style.transition = 'all 0.4s ease-out';
    observer.observe(card);
  });
});
"""

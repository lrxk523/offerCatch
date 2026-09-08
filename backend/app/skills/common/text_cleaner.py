"""文本清洗工具 - 去噪音、格式化、还原排版"""
# 本文件是从 skills/jd_parser/parser.py 迁移到公共层的通用文本清洗器。
# 所有模块应从此处导入 JDTextCleaner，勿再从 jd_parser.parser 导入。

import re
from typing import List


class JDTextCleaner:
    """JD/简历 文本清洗器 — 去除招聘网站噪音、格式化排版"""

    # 常见噪音模式
    NOISE_PATTERNS = [
        r"分享到.*",
        r"举报.*",
        r"收藏.*",
        r"发布时间.*",
        r"浏览.*次",
        r"投递.*份",
        r"聊天意愿.*",
        r"回复率.*",
        r"在线.*小时前",
        r"发布于.*",
        r"^\s*\d+人已读\s*$",
        r"^\s*沟通中\s*$",
        r"^\s*立即沟通\s*$",
        r"^\s*投递简历\s*$",
        r"^\s*申请职位\s*$",
        r"^\s*分享\s*$",
        r"^\s*收藏\s*$",
        r"^\s*举报\s*$",
        r"已读$",
        r"未读$",
        r"^\d+\.?\d*[万亿]?\s*(次|人|条).*$",
        r"^(Boss|HR|招聘官|HRBP).*(在线|离线|刚刚活跃).*$",
    ]

    # 社交媒体/APP 噪音关键词
    APP_NOISE = [
        "BOSS直聘", "智联招聘", "前程无忧", "拉勾网", "猎聘",
        "打开App", "扫码下载", "点击查看", "立即沟通",
        "招聘者", "发布于", "在线简历", "附件简历",
        "打招呼", "感兴趣", "聊一聊",
    ]

    @classmethod
    def clean(cls, raw_text: str) -> str:
        """清洗 OCR 提取的原始文本"""
        text = raw_text

        # 1. 去除重复空格和制表符
        text = re.sub(r"[ \t]+", " ", text)

        # 2. 合并多个空行为单个空行
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 3. 去除行首行尾空白
        lines = [line.strip() for line in text.split("\n")]

        # 4. 过滤噪音行
        cleaned_lines = []
        for line in lines:
            if not line:
                cleaned_lines.append(line)
                continue

            # 跳过纯数字/标点行
            if re.match(r"^[\d\s\.,;:!?。，、；：！？…—–·-]+$", line):
                continue

            # 跳过噪音模式
            is_noise = False
            for pattern in cls.NOISE_PATTERNS:
                if re.match(pattern, line, re.IGNORECASE):
                    is_noise = True
                    break

            # 跳过 APP 噪音
            if not is_noise:
                for noise_word in cls.APP_NOISE:
                    if noise_word in line and len(line) < 20:
                        is_noise = True
                        break

            if not is_noise:
                cleaned_lines.append(line)

        text = "\n".join(cleaned_lines)

        # 5. 去除连续空行
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 6. 去除首尾空行
        text = text.strip()

        return text

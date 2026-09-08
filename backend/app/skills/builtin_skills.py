"""内置示例 Skills"""

import json
import re
import fnmatch
import datetime
import asyncio
from pathlib import Path
from app.agent.skill import Skill, SkillResult


class WeatherSkill(Skill):
    """天气查询 Skill"""
    name = "get_weather"
    description = "查询指定城市的天气信息"
    keywords = ["天气", "weather", "气温", "下雨", "晴天"]
    triggers = ["天气", "天气怎么样", "查天气"]

    async def execute(self, city: str = "北京", **kwargs) -> SkillResult:
        # 模拟天气查询
        await asyncio.sleep(0.3)
        conditions = ["晴", "多云", "小雨", "阴天"]
        import random
        condition = random.choice(conditions)
        temp = random.randint(15, 35)
        return SkillResult(
            success=True,
            data={
                "city": city,
                "temperature": temp,
                "condition": condition,
                "humidity": random.randint(30, 90),
            },
            message=f"{city}天气：{condition}，温度{temp}°C",
        )

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称，如 北京、上海、深圳",
                        },
                    },
                    "required": ["city"],
                },
            },
        }


class CalculatorSkill(Skill):
    """数学计算 Skill"""
    name = "calculate"
    description = "执行数学计算表达式"
    keywords = ["计算", "算", "等于", "数学", "+", "-", "*", "/"]
    triggers = ["计算", "帮我算"]

    async def execute(self, expression: str = "", **kwargs) -> SkillResult:
        await asyncio.sleep(0.1)
        try:
            # 安全计算（仅允许数学表达式）
            allowed = set("0123456789+-*/().%^ ")
            sanitized = "".join(c for c in expression if c in allowed)
            result = eval(sanitized, {"__builtins__": {}}, {})
            return SkillResult(
                success=True,
                data={"expression": expression, "result": result},
                message=f"{expression} = {result}",
            )
        except Exception as e:
            return SkillResult(success=False, message=f"计算失败: {str(e)}")

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "数学表达式，如 2+3*4, (10-5)/2",
                        },
                    },
                    "required": ["expression"],
                },
            },
        }


class TimeSkill(Skill):
    """时间查询 Skill"""
    name = "get_time"
    description = "获取当前日期和时间"
    keywords = ["时间", "几点", "日期", "今天几号", "现在"]
    triggers = ["现在几点", "今天日期", "当前时间"]

    async def execute(self, timezone: str = "Asia/Shanghai", **kwargs) -> SkillResult:
        now = datetime.datetime.now()
        return SkillResult(
            success=True,
            data={
                "datetime": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
                "timezone": timezone,
            },
            message=f"现在是 {now.strftime('%Y年%m月%d日 %H:%M:%S')}，{['周一', '周二', '周三', '周四', '周五', '周六', '周日'][now.weekday()]}",
        )

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {
                            "type": "string",
                            "description": "时区，如 Asia/Shanghai",
                        },
                    },
                },
            },
        }


class FileReaderSkill(Skill):
    """文件读取 Skill"""
    name = "read_file"
    description = "读取项目 data 目录下的本地文件内容"
    keywords = ["读文件", "打开文件", "查看文件", "文件内容"]
    triggers = ["读文件", "读取文件"]

    # 允许读取的根目录白名单（相对项目根）
    _ALLOWED_ROOTS = [
        "data",
        "backend/data",
        "uploads",
        "backend/uploads",
    ]
    # 禁止读取的敏感文件名（无论路径）
    _SENSITIVE_NAMES = [
        ".env", ".env.local", ".env.production",
        "id_rsa", "id_ed25519", "*.pem", "*.key",
        "config.yaml", "config.yml", "settings.py",
    ]

    def _resolve_safe_path(self, filepath: str) -> str:
        """校验路径在允许根目录内，返回规范化绝对路径。越权抛 ValueError。"""
        raw = filepath.replace("\\", "/").strip()
        if not raw or raw.startswith(("/", "~")):
            raise ValueError(f"仅允许读取项目 data/uploads 目录内的相对路径: {filepath}")
        # 协议前缀 / Windows 盘符 / UNC 一律拒绝
        if re.match(r"^[a-zA-Z][:\\\\]", raw) or raw.startswith(("//", "\\\\")):
            raise ValueError(f"不允许绝对路径/盘符: {filepath}")
        parts = [p for p in raw.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise ValueError(f"不允许路径穿越: {filepath}")
        proj_root = Path(__file__).resolve().parent.parent.parent.parent  # app/skills → 项目根
        candidate = (proj_root / raw).resolve()
        # 必须在某个允许根目录内
        for root in self._ALLOWED_ROOTS:
            allowed = (proj_root / root).resolve()
            try:
                candidate.relative_to(allowed)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"仅允许读取项目 data/uploads 目录内文件: {filepath}")
        # 敏感文件名拦截
        name = candidate.name.lower()
        if any(
            fnmatch.fnmatch(name, pat)
            for pat in [p.lower() for p in self._SENSITIVE_NAMES]
        ):
            raise ValueError(f"禁止读取敏感文件: {candidate.name}")
        if not candidate.is_file():
            raise FileNotFoundError(filepath)
        return str(candidate)

    async def execute(self, filepath: str = "", **kwargs) -> SkillResult:
        try:
            safe_path = self._resolve_safe_path(filepath)
            with open(safe_path, "r", encoding="utf-8") as f:
                content = f.read()
            return SkillResult(
                success=True,
                data={"filepath": filepath, "content": content[:2000]},
                message=f"文件 {filepath} 读取成功 ({len(content)} 字符)",
            )
        except ValueError as e:
            return SkillResult(success=False, message=str(e))
        except FileNotFoundError:
            return SkillResult(success=False, message=f"文件不存在: {filepath}")
        except Exception as e:
            return SkillResult(success=False, message=str(e))

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "文件的绝对路径或相对路径",
                        },
                    },
                    "required": ["filepath"],
                },
            },
        }


class EchoSkill(Skill):
    """回显 Skill - 最简单的示例，用于测试"""
    name = "echo"
    description = "回显用户输入，用于测试"
    keywords = ["echo", "回显", "复读", "重复"]
    triggers = ["复读", "重复我说"]

    async def execute(self, message: str = "", **kwargs) -> SkillResult:
        return SkillResult(
            success=True,
            data={"echo": message},
            message=f"Echo: {message}",
        )

    def tool_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "需要回显的消息内容",
                        },
                    },
                    "required": ["message"],
                },
            },
        }

# 扩展指南 - 添加自定义 Skill & Workflow

## 项目结构

```
offerCatch/
├── backend/                # 后端（import 起点 = backend/，见「运行」节）
│   ├── app/
│   │   ├── main.py         # FastAPI 入口（uvicorn app.main:app）
│   │   ├── cli.py          # CLI 交互入口（python -m app.cli）
│   │   ├── api/v1/         # 路由层（chat / jd / resume / match）
│   │   ├── core/config.py  # LLM 多提供商配置
│   │   ├── db/             # Redis 封装（redis_client / chat_history / resume_store）
│   │   ├── schemas/        # 请求体 DTO
│   │   ├── services/       # agent_runtime：Agent 池 + OCR 懒加载单例
│   │   ├── agent/          # 核心引擎
│   │   │   ├── __init__.py
│   │   │   ├── skill.py    #   Skill 基类 + 注册中心
│   │   │   ├── workflow.py #   Workflow 引擎 + 注册中心
│   │   │   └── engine.py   #   Agent 核心 (LLM 集成)
│   │   ├── skills/         # 自定义 Skill 目录
│   │   │   ├── __init__.py
│   │   │   ├── common/     #   ◀ 公共能力层 (OCR, 文本清洗等)
│   │   │   │   ├── ocr.py          #   OCR 引擎 (PaddleOCR/EasyOCR/Tesseract)
│   │   │   │   └── text_cleaner.py #   通用文本清洗去噪音
│   │   │   ├── builtin_skills.py   #   内置示例 (参考用)
│   │   │   ├── jd_parser/          #   JD 解析 (OCR → 清洗 → 结构化)
│   │   │   ├── resume_optimizer/   #   简历优化 (解析 → LLM 审计 → STAR 改写 → PDF)
│   │   │   └── resume_jd_matcher/  #   匹配度分析 (关键词 → LLM 打分 → 可视化)
│   │   └── workflows/      # 自定义 Workflow 目录
│   │       ├── __init__.py
│   │       └── builtin_workflows.py
│   ├── tests/              # 测试脚本
│   ├── requirements.txt
│   └── pyproject.toml
├── front/                  # 前端静态页（后端伺服）
├── Dockerfile / docker-compose.yml
└── EXTENSION_GUIDE.md      # 本文档
```

---

## 如何添加一个 Skill

### 第 1 步：创建 Skill 类

在 `app/skills/` 目录下创建文件，如 `app/skills/my_skills.py`：

```python
from app.agent.skill import Skill, SkillResult

class TranslateSkill(Skill):
    name = "translate"
    description = "翻译文本到指定语言"
    keywords = ["翻译", "translate", "译"]
    triggers = ["翻译", "帮我翻译"]

    async def execute(self, text: str = "", target_lang: str = "中文", **kwargs) -> SkillResult:
        # 这里实现你的翻译逻辑
        # 可以调用外部 API、本地模型等
        translated = f"[{text}] -> ({target_lang})"  # 示例
        return SkillResult(
            success=True,
            data={"original": text, "translated": translated, "target_lang": target_lang},
            message=f"翻译结果: {translated}",
        )

    def tool_schema(self):
        """返回 OpenAI function calling 格式的 schema"""
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
                            "description": "需要翻译的文本",
                        },
                        "target_lang": {
                            "type": "string",
                            "description": "目标语言，如 中文、英文、日文",
                        },
                    },
                    "required": ["text"],
                },
            },
        }
```

### 第 2 步：注册到 Agent

在 `backend/app/cli.py` 的 `build_agent()` 中添加（或仿照 `app/services/agent_runtime.py` 的 `_get_base_agent()`）：

```python
from app.skills.my_skills import TranslateSkill

agent.register_skill(TranslateSkill())
```

---

## 如何添加一个 Workflow

### 方式 1：用 SkillStep 编排现有 Skill

```python
from app.agent.workflow import Workflow, SkillStep
from app.skills.my_skills import TranslateSkill
from app.skills.builtin_skills import WeatherSkill

def create_translate_weather_workflow():
    """先翻译城市名再查天气"""
    wf = Workflow(
        name="translate_weather",
        description="将城市名翻译后查询天气"
    )
    wf.add_step(SkillStep(
        TranslateSkill(),
        step_name="translate_city",
        input_map={"text": "city_name"}
    ))
    wf.add_step(SkillStep(
        WeatherSkill(),
        step_name="check_weather",
        input_map={"city": "__result_translate_city.data.translated"}
    ))
    return wf
```

### 方式 2：自定义 WorkflowStep

```python
from app.agent.workflow import WorkflowStep, WorkflowContext, StepResult, StepStatus

class CustomStep(WorkflowStep):
    name = "my_custom_step"

    async def run(self, ctx: WorkflowContext) -> StepResult:
        # 从上下文获取数据
        user_data = ctx.get("some_key", "default_value")

        # 执行自定义逻辑
        result = do_something(user_data)

        # 写入上下文供后续步骤使用
        ctx.set("output_key", result)

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output=result,
        )
```

### 方式 3：条件分支

```python
from app.agent.workflow import ConditionalStep, SkillStep

async def is_weekend(ctx: WorkflowContext):
    import datetime
    return datetime.datetime.now().weekday() >= 5

weekend_step = SkillStep(LeisureSkill(), step_name="weekend_activity")
weekday_step = SkillStep(WorkSkill(), step_name="workday_activity")

conditional = ConditionalStep(
    condition=is_weekend,
    true_step=weekend_step,
    false_step=weekday_step,
    step_name="time_based_router",
)
```

---

## Skill 关键接口说明

| 属性/方法 | 说明 |
|---|---|
| `name` | 唯一标识，会作为 function name 注册到 LLM |
| `description` | 描述，LLM 据此决定何时调用 |
| `keywords` | 匹配关键词 (备选路由) |
| `triggers` | 触发短语 (备选路由) |
| `execute(**kwargs)` | **必须实现**，核心执行逻辑 |
| `tool_schema()` | **必须实现**，返回 function calling schema |
| `match(user_input)` | 可选重写，自定义匹配逻辑 |

## Workflow 关键接口说明

| 类/方法 | 说明 |
|---|---|
| `Workflow(name, desc)` | 创建工作流 |
| `.add_step(step)` | 添加步骤，支持链式调用 |
| `.on_error(strategy)` | 错误策略: "stop"/"continue" |
| `SkillStep(skill, name, input_map)` | 将 Skill 包装为步骤 |
| `ConditionalStep(cond, true, false)` | 条件分支步骤 |
| `WorkflowContext` | 步骤间共享的上下文 |

---

## 运行

```bash
# 安装依赖（backend/ 是 import 起点）
cd backend
pip install -r requirements.txt

# 配置 API key
# 运行目录（backend/）需有一份 .env（本地已复制根目录 .env 到 backend/.env）
# 编辑 .env 填入 OPENAI_API_KEY

# 启动 Web 服务（FastAPI + SSE，端口 7860）
uvicorn app.main:app --reload
# 或：python -m app.cli  （CLI 交互模式）
```

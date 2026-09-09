"""对话智能体入口 - CLI 交互模式"""

import asyncio
import sys
from app.agent import Agent, AgentConfig
from app.skills.jd_parser import JDParseSkill
from app.skills.resume_optimizer import ResumeOptimizeSkill
from app.skills.resume_jd_matcher import ResumeJDMatcherSkill
from app.workflows.jd_workflow import create_jd_parse_workflow


def build_agent() -> Agent:
    """构建并配置 Agent 实例"""
    config = AgentConfig(
        system_prompt=(
            "你是一个 AI 求职助手，名叫 OfferCatch。"
            "当用户说「帮我解析这个 JD」「帮我分析这个职位」或粘贴岗位描述文本时，"
            "请调用 parse_jd 工具（将文本传给 text 参数）来提取结构化的岗位信息。"
            "当用户说「优化简历」「帮我改简历」并提供简历内容时，请调用 optimize_resume 工具。"
            "当用户说「匹配度分析」「简历匹配」或需要对比简历和JD时，"
            "请调用 match_resume_jd 工具来生成匹配度可视化分析报告。"
            "调用工具后，将结果用自然语言呈现给用户，不要输出 JSON。"
            "请始终用中文回复。"
        ),
        temperature=0.7,
    )
    agent = Agent(config)

    # 注册求职领域 Skills
    agent.register_skill(JDParseSkill())
    agent.register_skill(ResumeOptimizeSkill())
    agent.register_skill(ResumeJDMatcherSkill())

    # 注册 Workflow
    agent.register_workflow(create_jd_parse_workflow())

    return agent


async def interactive_mode(agent: Agent):
    """交互式对话模式"""
    print("\n" + "=" * 60)
    print("  OfferCatch 对话智能体")
    print("  输入 /help 查看命令 | /exit 退出")
    print("=" * 60)

    agent.print_status()

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        # 内置命令
        if user_input.startswith("/"):
            await handle_command(agent, user_input)
            continue

        # 对话
        print("助手: ", end="", flush=True)
        try:
            full_response = []
            async for chunk in agent.chat_stream(user_input):
                print(chunk, end="", flush=True)
                full_response.append(chunk)
            print()
        except Exception as e:
            print(f"\n[错误] {e}")


async def handle_command(agent: Agent, cmd: str):
    """处理斜杠命令"""
    parts = cmd.split()
    command = parts[0].lower()

    if command == "/exit" or command == "/quit":
        print("再见！")
        sys.exit(0)

    elif command == "/help":
        print("""
可用命令:
  /help          - 显示帮助
  /status        - 查看 Agent 状态
  /skills        - 列出所有 Skill
  /workflows     - 列出所有 Workflow
  /clear         - 清空对话历史
  /skill <name>  - 查看 Skill 详情
  /jd <path>     - 快速解析 JD 截图 (传入图片路径)
  /jdtext <text> - 快速解析 JD 文本
  /run <wf>      - 手动执行工作流
  /exit          - 退出
        """)

    elif command == "/status":
        agent.print_status()

    elif command == "/skills":
        skills = agent.skills.list_all()
        if not skills:
            print("暂无已注册的 Skill")
        else:
            print(f"\n已注册 Skill ({len(skills)}):")
            for s in skills:
                print(f"  • {s['name']}: {s['description']}")
                print(f"    关键词: {', '.join(s['keywords'])}")

    elif command == "/workflows":
        wfs = agent.workflows.list_all()
        if not wfs:
            print("暂无已注册的 Workflow")
        else:
            print(f"\n已注册 Workflow ({len(wfs)}):")
            for w in wfs:
                print(f"  • {w['name']}: {w['description']} ({w['steps_count']} 步)")

    elif command == "/clear":
        agent.clear_history()
        print("对话历史已清空")

    elif command == "/skill" and len(parts) > 1:
        name = parts[1]
        skill = agent.skills.get(name)
        if skill:
            info = skill.to_dict()
            print(f"\nSkill: {info['name']}")
            print(f"  描述: {info['description']}")
            print(f"  关键词: {', '.join(info['keywords'])}")
            print(f"  触发词: {', '.join(info['triggers'])}")
        else:
            print(f"未找到 Skill: {name}")

    elif command == "/run" and len(parts) > 1:
        name = parts[1]
        # 提取额外参数，如 /run daily_brief city=上海
        ctx = {}
        for arg in parts[2:]:
            if "=" in arg:
                k, v = arg.split("=", 1)
                ctx[k] = v
        print(f"执行工作流: {name} ...")
        try:
            results = await agent.invoke_workflow(name, ctx)
            if results is None:
                print(f"未找到工作流: {name}")
            else:
                for r in results:
                    status_icon = "✓" if r.status.value == "completed" else "✗"
                    print(f"  {status_icon} [{r.status.value}] {r.step_name}")
                    if r.output:
                        print(f"    -> {r.output.message}")
                    if r.error:
                        print(f"    -> 错误: {r.error}")
        except Exception as e:
            print(f"执行失败: {e}")

    elif command == "/jd" and len(parts) > 1:
        image_path = parts[1]
        print(f"正在解析 JD 截图: {image_path} ...")
        try:
            result = await agent.invoke_skill("parse_jd", image_path=image_path)
            if result:
                print(result.message)
            else:
                print("解析失败")
        except Exception as e:
            print(f"解析失败: {e}")

    elif command == "/jdtext" and len(parts) > 1:
        jd_text = " ".join(parts[1:])
        print("正在解析 JD 文本 ...")
        try:
            result = await agent.invoke_skill("parse_jd", text=jd_text)
            if result:
                print(result.message)
            else:
                print("解析失败")
        except Exception as e:
            print(f"解析失败: {e}")

    else:
        print(f"未知命令: {command}，输入 /help 查看帮助")


# ---- 入口 ----

if __name__ == "__main__":
    agent = build_agent()
    asyncio.run(interactive_mode(agent))

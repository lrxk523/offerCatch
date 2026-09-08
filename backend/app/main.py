"""OfferCatch FastAPI 应用入口

启动方式（二选一）：
    方式A：直接运行本文件（任意目录都行）
        python backend/app/main.py
    方式B：从 backend 目录以模块方式启动（开发常用，带热重载）
        cd backend
        uvicorn app.main:app --reload
"""

import sys
from pathlib import Path
# 关键：把 backend/（本文件的上上级目录）加入模块搜索路径。
# 否则直接 `python app/main.py` 时，Python 找不到 app 这个包，会报
# ModuleNotFoundError: No module named 'app'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn

from app.api.v1 import chat, jd, resume, match
from app.services.agent_runtime import get_agent

app = FastAPI(title="OfferCatch", description="智能对话助手")

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = (Path(__file__).resolve().parents[2] / "front") / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/front/{file_path:path}")
async def serve_static(file_path: str):
    front_dir = Path(__file__).resolve().parents[2] / "front"
    full_path = front_dir / file_path
    if full_path.exists() and full_path.is_file():
        return FileResponse(str(full_path))
    return JSONResponse({"error": "Not found"}, status_code=404)




# ---- 路由装配 ----
app.include_router(chat.router)
app.include_router(jd.router)
app.include_router(resume.router)
app.include_router(match.router)

if __name__ == "__main__":
    get_agent()  # 预初始化

    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")


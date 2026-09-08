FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（OCR + PDF 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装 Python 包
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 7860

# 启动（从 backend 目录以模块方式启动，import 起点 = backend/）
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]

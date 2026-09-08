"""简历接口：/api/resume/optimize-file|optimize-text (SSE)、GET /api/resume/{id}"""

import base64
import json
import traceback
import uuid
from io import BytesIO

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse

from app.schemas.request import JDTextRequest
from app.db.resume_store import save_resume, get_resume
from app.services.agent_runtime import get_agent, _get_ocr_engine

router = APIRouter(prefix="/api", tags=["resume"])

@router.post("/resume/optimize-file")
async def optimize_resume_file(file: UploadFile = File(...), target_position: str = Form("")):
    agent = get_agent()
    filename = file.filename or ""

    async def generate():
        try:
            contents = await file.read()
            content_type = file.content_type or ""

            # 判断文件类型
            is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")

            extracted_text = ""
            total_pages = 1

            if is_pdf:
                # ---- PDF 路径 ----
                import fitz  # PyMuPDF
                from PIL import Image

                doc = fitz.open(stream=contents, filetype="pdf")
                total_pages = len(doc)

                # 发送进度：开始渲染
                yield _sse("progress", {"stage": "render", "message": f"正在渲染 PDF（共 {total_pages} 页）...", "page": 0, "total": total_pages})

                # 1. 将每页渲染为图片
                page_images = []
                for i, page in enumerate(doc):
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(BytesIO(pix.tobytes("png")))
                    page_images.append(img)
                doc.close()

                # 2. OCR 逐页识别，实时推送进度
                yield _sse("progress", {"stage": "ocr", "message": f"正在 OCR 识别...", "page": 0, "total": total_pages})
                ocr = await _get_ocr_engine()
                page_texts = []
                for i, img in enumerate(page_images):
                    text = await ocr.extract_text(img)
                    char_count = len(text.strip()) if text else 0
                    if text and text.strip():
                        page_texts.append(text.strip())
                    print(f"[PDF OCR] 第 {i+1}/{total_pages} 页: {char_count} 字符")
                    yield _sse("progress", {
                        "stage": "ocr",
                        "message": f"OCR 识别中... 第 {i+1}/{total_pages} 页（{char_count} 字）",
                        "page": i + 1,
                        "total": total_pages,
                    })

                pdf_text = "\n\n".join(page_texts)

                if not pdf_text.strip():
                    yield _sse("error", {"message": "PDF 图片 OCR 未能识别到文字内容。请确保 PDF 清晰可读，或尝试截图后上传图片。"})
                    return

                extracted_text = pdf_text

                # 3. LLM 优化
                yield _sse("progress", {"stage": "llm", "message": "正在 AI 分析优化简历...", "page": total_pages, "total": total_pages})
                result = await agent.invoke_skill(
                    "optimize_resume", text=pdf_text, target_position=target_position
                )
            else:
                # ---- 图片路径 ----
                yield _sse("progress", {"stage": "ocr", "message": "正在 OCR 识别图片...", "page": 0, "total": 1})
                image_b64 = base64.b64encode(contents).decode("utf-8")
                yield _sse("progress", {"stage": "llm", "message": "正在 AI 分析优化简历...", "page": 1, "total": 1})
                result = await agent.invoke_skill(
                    "optimize_resume", image_base64=image_b64, target_position=target_position
                )
                if result and result.success and result.data:
                    extracted_text = result.data.get("raw_text", "")

            if result and result.success:
                # ---- 存入 Redis ----
                resume_id = str(uuid.uuid4())[:8]
                try:
                    resume_meta = {
                        "filename": filename,
                        "type": "pdf" if is_pdf else "image",
                        "pages": total_pages if is_pdf else 1,
                    }
                    save_resume(
                        session_id=resume_id,
                        raw_text=extracted_text,
                        parsed=result.data.get("parsed"),
                        optimized=result.data.get("optimized"),
                        meta=resume_meta,
                    )
                    print(f"[Resume] 已存入 Redis, id={resume_id}")
                except Exception as store_err:
                    print(f"[Resume] Redis 存储失败: {store_err}")
                    resume_id = ""

                yield _sse("result", {
                    "success": True,
                    "data": result.data,
                    "raw_text": extracted_text,
                    "message": result.message,
                    "resume_id": resume_id,
                })
            else:
                yield _sse("error", {"message": result.message if result else "优化失败"})

        except Exception as e:
            traceback.print_exc()
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")

def _sse(event_type: str, data: dict) -> str:
    """生成 SSE 事件"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@router.post("/resume/optimize-text")
async def optimize_resume_text(req: JDTextRequest):
    agent = get_agent()

    async def generate():
        try:
            yield _sse("progress", {"stage": "llm", "message": "正在 AI 分析优化简历...", "page": 0, "total": 1})
            result = await agent.invoke_skill("optimize_resume", text=req.text)
            if result and result.success:
                # ---- 存入 Redis ----
                resume_id = str(uuid.uuid4())[:8]
                try:
                    save_resume(
                        session_id=resume_id,
                        raw_text=req.text,
                        parsed=result.data.get("parsed"),
                        optimized=result.data.get("optimized"),
                        meta={"type": "text"},
                    )
                    print(f"[Resume] 文本简历已存入 Redis, id={resume_id}")
                except Exception as store_err:
                    print(f"[Resume] Redis 存储失败: {store_err}")
                    resume_id = ""

                yield _sse("result", {
                    "success": True,
                    "data": result.data,
                    "raw_text": req.text,
                    "message": result.message,
                    "resume_id": resume_id,
                })
            else:
                yield _sse("error", {"message": result.message if result else "优化失败"})
        except Exception as e:
            traceback.print_exc()
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")

@router.get("/resume/{session_id}")
async def get_resume_data(session_id: str):
    """获取之前上传并存放在 Redis 中的简历数据"""
    try:
        data = get_resume(session_id)
        if not data:
            return JSONResponse({"success": False, "error": "未找到该简历，可能已过期"}, status_code=404)
        return JSONResponse({"success": True, "data": data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


"""简历接口：/api/resume/optimize-file|optimize-text (SSE)、GET /api/resume/{id}"""

import asyncio
import base64
import json
import traceback
import uuid

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
            result = None

            # ---- 0. 转录缓存：同一文件不重复识别 ----
            from app.skills.common.ocr_cache import file_md5, get_text_cache, set_text_cache
            fhash = file_md5(contents)
            cached = get_text_cache(fhash)

            if cached:
                extracted_text = cached
                yield _sse("progress", {"stage": "cache", "message": "检测到相同文件，使用缓存文本，跳过识别", "page": 0, "total": 1})
                yield _sse("progress", {"stage": "llm", "message": "正在 AI 分析优化简历...", "page": 1, "total": 1})
                result = None
                async for _kind, _a, _b in _invoke_optimize(
                    agent, text=extracted_text, target_position=target_position
                ):
                    if _kind == "progress":
                        yield _sse("progress", {"stage": _a, "message": _b, "page": 0, "total": 1})
                    elif _kind == "error":
                        yield _sse("error", {"message": str(_a)})
                        return
                    else:
                        result = _a
            elif is_pdf:
                # ---- PDF 路径：先试文字层，失败才渲染 OCR ----
                from app.skills.common.pdf_utils import pdf_to_text

                layer_text, kind = pdf_to_text(contents)

                if kind == "layer":
                    # 文字层直接可用，跳过 OCR（免费且准）
                    yield _sse("progress", {"stage": "extract", "message": f"检测到 PDF 文字层，直接提取文本（{len(layer_text)} 字）", "page": 0, "total": 1})
                    extracted_text = layer_text
                    set_text_cache(fhash, extracted_text)
                    yield _sse("progress", {"stage": "llm", "message": "正在 AI 分析优化简历...", "page": 1, "total": 1})
                    result = None
                    async for _kind, _a, _b in _invoke_optimize(
                        agent, text=extracted_text, target_position=target_position
                    ):
                        if _kind == "progress":
                            yield _sse("progress", {"stage": _a, "message": _b, "page": 0, "total": 1})
                        elif _kind == "error":
                            yield _sse("error", {"message": str(_a)})
                            return
                        else:
                            result = _a
                else:
                    # 扫描件：渲染每页为图片 → OCR/云转录
                    from app.skills.common.pdf_utils import render_pdf_pages

                    page_images, total_pages = render_pdf_pages(contents, dpi=200)

                    yield _sse("progress", {"stage": "render", "message": f"正在渲染 PDF（共 {total_pages} 页）...", "page": 0, "total": total_pages})
                    yield _sse("progress", {"stage": "ocr", "message": f"正在识别 PDF 内容...", "page": 0, "total": total_pages})

                    ocr = await _get_ocr_engine()
                    page_texts = []
                    for i, img in enumerate(page_images):
                        text = await ocr.extract_text(img)
                        char_count = len(text.strip()) if text else 0
                        if text and text.strip():
                            page_texts.append(text.strip())
                        print(f"[PDF OCR] 第 {i+1}/{total_pages} 页: {char_count} 字符 (引擎={ocr.engine_name})")
                        yield _sse("progress", {
                            "stage": "ocr",
                            "message": f"识别中... 第 {i+1}/{total_pages} 页（{char_count} 字）",
                            "page": i + 1,
                            "total": total_pages,
                        })

                    pdf_text = "\n\n".join(page_texts)

                    if not pdf_text.strip():
                        yield _sse("error", {"message": "PDF 识别未能获取文字内容。请确保 PDF 清晰可读，或尝试截图后上传图片。"})
                        return

                    extracted_text = pdf_text
                    set_text_cache(fhash, extracted_text)

                    yield _sse("progress", {"stage": "llm", "message": "正在 AI 分析优化简历...", "page": total_pages, "total": total_pages})
                    result = None
                    async for _kind, _a, _b in _invoke_optimize(
                        agent, text=pdf_text, target_position=target_position
                    ):
                        if _kind == "progress":
                            yield _sse("progress", {"stage": _a, "message": _b, "page": 0, "total": 1})
                        elif _kind == "error":
                            yield _sse("error", {"message": str(_a)})
                            return
                        else:
                            result = _a
            else:
                # ---- 图片路径：OCR/云转录后走 LLM（skill 内完成）----
                yield _sse("progress", {"stage": "ocr", "message": "正在识别图片内容...", "page": 0, "total": 1})
                image_b64 = base64.b64encode(contents).decode("utf-8")
                yield _sse("progress", {"stage": "llm", "message": "正在 AI 分析优化简历...", "page": 1, "total": 1})
                result = None
                async for _kind, _a, _b in _invoke_optimize(
                    agent, image_base64=image_b64, target_position=target_position
                ):
                    if _kind == "progress":
                        yield _sse("progress", {"stage": _a, "message": _b, "page": 0, "total": 1})
                    elif _kind == "error":
                        yield _sse("error", {"message": str(_a)})
                        return
                    else:
                        result = _a
                if result and result.success and result.data:
                    extracted_text = result.data.get("raw_text", "")
                    if extracted_text:
                        set_text_cache(fhash, extracted_text)

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


async def _invoke_optimize(agent, **kwargs):
    """调用 optimize_resume skill 并转发其 on_progress 阶段帧（异步队列桥接）。

    yield ("progress", stage, message) 逐阶段实时转发；结束 yield ("result", r, None)
    或 ("error", e, None)。调用方在 async for 中把 progress 帧转为 SSE 发给前端。
    """
    q: asyncio.Queue = asyncio.Queue()

    async def _on_progress(stage: str, message: str):
        await q.put(("progress", stage, message))

    async def _worker():
        try:
            r = await agent.invoke_skill("optimize_resume", on_progress=_on_progress, **kwargs)
            await q.put(("result", r, None))
        except Exception as e:
            await q.put(("error", e, None))

    asyncio.create_task(_worker())
    while True:
        kind, a, b = await q.get()
        yield (kind, a, b)
        if kind in ("result", "error"):
            return


@router.post("/resume/optimize-text")
async def optimize_resume_text(req: JDTextRequest):
    agent = get_agent()

    async def generate():
        try:
            yield _sse("progress", {"stage": "llm", "message": "正在 AI 分析优化简历...", "page": 0, "total": 1})
            result = None
            async for _kind, _a, _b in _invoke_optimize(agent, text=req.text):
                if _kind == "progress":
                    yield _sse("progress", {"stage": _a, "message": _b, "page": 0, "total": 1})
                elif _kind == "error":
                    yield _sse("error", {"message": str(_a)})
                    return
                else:
                    result = _a
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

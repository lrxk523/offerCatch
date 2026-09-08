"""匹配度接口：/api/match、/api/match/pdf"""

import traceback
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.schemas.request import MatchRequest
from app.db.resume_store import get_resume
from app.services.agent_runtime import get_agent, _get_ocr_engine

router = APIRouter(prefix="/api", tags=["match"])

@router.post("/match")
async def match_resume_jd(req: MatchRequest):
    agent = get_agent()
    resume_text = req.resume_text.strip()

    # 如果提供了 resume_id，从 Redis 拉取简历文本
    if req.resume_id and not resume_text:
        try:
            stored = get_resume(req.resume_id)
            if stored and stored.get("raw_text"):
                resume_text = stored["raw_text"]
                print(f"[Match] 从 Redis ({req.resume_id}) 加载简历, {len(resume_text)} 字符")
                if not req.resume_name:
                    parsed = stored.get("parsed", {})
                    req.resume_name = parsed.get("name", "") if isinstance(parsed, dict) else ""
            else:
                return JSONResponse({
                    "success": False,
                    "error": f"Redis 中未找到简历 (id={req.resume_id})，可能已过期",
                })
        except Exception as e:
            return JSONResponse({"success": False, "error": f"Redis 读取失败: {e}"})

    try:
        result = await agent.invoke_skill(
            "match_resume_jd",
            resume_text=resume_text,
            jd_text=req.jd_text,
            resume_name=req.resume_name,
            jd_title=req.jd_title,
        )
        if result and result.success:
            return JSONResponse({
                "success": True,
                "data": result.data,
                "message": result.message,
            })
        return JSONResponse({"success": False, "error": result.message if result else "分析失败"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@router.post("/match/pdf")
async def match_resume_pdf(
    file: UploadFile = File(...),
    jd_text: str = Form(""),
    jd_file: Optional[UploadFile] = None,
    resume_name: str = Form(""),
    jd_title: str = Form(""),
):
    """
    PDF 简历 + JD 匹配度分析（OCR 模式）。

    流程：
    1. JD 文本 → 提取关键词
    2. PDF 简历 → 逐页渲染为图片 → OCR 识别文本
    3. JD 关键词在 OCR 文本中搜索 → 评分
    """
    agent = get_agent()

    try:
        # ---- 1. 读取 PDF 文件 ----
        contents = await file.read()
        if not contents:
            return JSONResponse({"success": False, "error": "PDF 文件为空"}, status_code=400)

        # ---- 2. 处理 JD 输入 ----
        final_jd_text = jd_text.strip()

        # 如果上传了 JD 文件（图片/PDF），提取文本（带缓存）
        if jd_file is not None:
            try:
                jd_contents = await jd_file.read()
                jd_fname = (jd_file.filename or "").lower()
                jd_is_pdf = (jd_file.content_type == "application/pdf") or jd_fname.endswith(".pdf")

                if jd_contents:
                    from app.skills.common.ocr_cache import file_md5, get_text_cache, set_text_cache
                    jd_hash = file_md5(jd_contents)
                    jd_cached = get_text_cache(jd_hash)

                    if jd_cached:
                        final_jd_text = jd_cached.strip()
                        print(f"[Match-PDF] JD 文件命中缓存: {len(final_jd_text)} 字符")
                    else:
                        ocr_engine = await _get_ocr_engine()
                        if jd_is_pdf:
                            # JD PDF：先文字层，扫描件再渲染 OCR
                            from app.skills.common.pdf_utils import pdf_to_text, render_pdf_pages
                            layer_text, kind = pdf_to_text(jd_contents)
                            if kind == "layer" and layer_text.strip():
                                final_jd_text = layer_text.strip()
                                print(f"[Match-PDF] JD PDF 文字层: {len(final_jd_text)} 字符")
                            else:
                                imgs, _ = render_pdf_pages(jd_contents)
                                parts = []
                                for im in imgs:
                                    t = await ocr_engine.extract_text(im)
                                    if t and t.strip():
                                        parts.append(t.strip())
                                final_jd_text = "\n\n".join(parts).strip()
                                print(f"[Match-PDF] JD PDF 扫描OCR: {len(final_jd_text)} 字符")
                        else:
                            # JD 图片 → OCR/云转录
                            from PIL import Image as PILImage
                            jd_img = PILImage.open(BytesIO(jd_contents))
                            jd_ocr_text = await ocr_engine.extract_text(jd_img)
                            if jd_ocr_text and jd_ocr_text.strip():
                                final_jd_text = jd_ocr_text.strip()
                                print(f"[Match-PDF] JD 图片 OCR: {len(final_jd_text)} 字符 (引擎={ocr_engine.engine_name})")
                        if final_jd_text:
                            set_text_cache(jd_hash, final_jd_text)
            except Exception as e:
                print(f"[Match-PDF] JD 文件处理失败: {e}")

        if not final_jd_text or len(final_jd_text) < 20:
            return JSONResponse({
                "success": False,
                "error": "JD 内容太少，请提供完整的岗位描述文本或截图。",
            }, status_code=400)

        # ---- 3. PDF 简历 → 文字层优先，扫描件才 OCR ----
        from app.skills.common.pdf_utils import pdf_to_text, render_pdf_pages
        from app.skills.common.ocr_cache import file_md5 as _resume_md5, get_text_cache as _get_rcache, set_text_cache as _set_rcache
        from PIL import Image as PILImage

        resume_hash = _resume_md5(contents)
        resume_cached = _get_rcache(resume_hash)

        if resume_cached:
            ocr_full_text = resume_cached
            print(f"[Match-PDF] 简历命中缓存: {len(ocr_full_text)} 字符")
        else:
            layer_text, kind = pdf_to_text(contents)
            if kind == "layer" and layer_text.strip():
                # 文字层 PDF：直接使用，跳过渲染 OCR
                ocr_full_text = layer_text.strip()
                print(f"[Match-PDF] 简历文字层直接提取: {len(ocr_full_text)} 字符")
                _set_rcache(resume_hash, ocr_full_text)
            else:
                # 扫描件：逐页渲染 + OCR/云转录
                try:
                    doc = None
                    import fitz  # PyMuPDF
                    doc = fitz.open(stream=contents, filetype="pdf")
                    total_pages = len(doc)
                    if total_pages == 0:
                        doc.close()
                        return JSONResponse({
                            "success": False,
                            "error": "PDF 文件无页面内容。",
                        }, status_code=400)

                    print(f"[Match-PDF] PDF 共 {total_pages} 页，开始逐页识别...")

                    ocr_engine = await _get_ocr_engine()
                    page_texts = []
                    page_images = []

                    for page_num, page in enumerate(doc):
                        # 渲染为图片 (200 DPI)
                        pix = page.get_pixmap(dpi=200)
                        img = PILImage.open(BytesIO(pix.tobytes("png")))
                        page_images.append(img)

                        # OCR/云转录
                        text = await ocr_engine.extract_text(img)
                        if text and text.strip():
                            page_texts.append(text.strip())
                        print(f"[Match-PDF] 第 {page_num + 1}/{total_pages} 页: "
                              f"{len(text) if text else 0} 字符 (引擎={ocr_engine.engine_name})")

                    doc.close()

                    ocr_full_text = "\n\n".join(page_texts)

                    if not ocr_full_text.strip():
                        return JSONResponse({
                            "success": False,
                            "error": (
                                "PDF 图片 OCR 未能识别到文字内容。"
                                "请确保 PDF 清晰可读，或尝试截图后上传图片。"
                            ),
                        })

                    _set_rcache(resume_hash, ocr_full_text)
                except Exception as e:
                    import traceback as _tb
                    _tb.print_exc()
                    return JSONResponse({
                        "success": False,
                        "error": f"PDF 处理失败: {e}",
                    }, status_code=400)

        print(f"[Match-PDF] 简历文本就绪，共 {len(ocr_full_text)} 字符")

        # ---- 4. 调用 OCR 匹配引擎 ----
        result = await agent.invoke_skill(
            "match_resume_jd",
            mode="ocr",
            jd_text=final_jd_text,
            ocr_text=ocr_full_text,
            jd_title=jd_title.strip(),
            resume_name=resume_name.strip(),
        )

        if result and result.success:
            return JSONResponse({
                "success": True,
                "data": result.data,
                "message": result.message,
                "ocr_text": ocr_full_text,
            })
        return JSONResponse({
            "success": False,
            "error": result.message if result else "匹配分析失败",
        })

    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


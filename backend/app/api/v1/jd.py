"""JD 解析接口：/api/jd/parse-image、/api/jd/parse-text"""

import base64
import json

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

from app.schemas.request import JDTextRequest
from app.services.agent_runtime import get_agent
from app.db.redis_client import get_redis, _key

router = APIRouter(prefix="/api", tags=["jd"])

# JD 解析结果缓存 TTL：同一张 JD 截图二次上传不重复调用视觉模型
JD_CACHE_TTL = 86400


@router.post("/jd/parse-image")
async def parse_jd_image(file: UploadFile = File(...)):
    agent = get_agent()
    try:
        contents = await file.read()
        if not contents:
            return JSONResponse({"success": False, "error": "文件为空"}, status_code=400)

        # ---- 缓存：同一文件直接复用上次结构化结果 ----
        from app.skills.common.ocr_cache import file_md5
        fhash = file_md5(contents)
        try:
            r = get_redis()
            cached = r.get(_key(f"jd:{fhash}"))
        except Exception:
            cached = None

        if cached:
            try:
                cached_data = json.loads(cached)
                print(f"[JD] 命中缓存 (md5={fhash[:8]}...)")
                return JSONResponse({
                    "success": True,
                    "data": cached_data,
                    "cached": True,
                })
            except Exception:
                pass  # 缓存损坏则重新解析

        image_b64 = base64.b64encode(contents).decode("utf-8")
        result = await agent.invoke_skill("parse_jd", image_base64=image_b64)
        if result and result.success:
            # 写缓存（仅缓存结构化字段，不含 message 等展示文本）
            cache_data = {k: v for k, v in result.data.items() if k not in ("raw_text", "cleaned_text")}
            try:
                r.set(_key(f"jd:{fhash}"), json.dumps(cache_data, ensure_ascii=False), ex=JD_CACHE_TTL)
            except Exception as e:
                print(f"[JD] 缓存写入失败(忽略): {e}")

            return JSONResponse({
                "success": True,
                "data": result.data,
                "message": result.message,
            })
        return JSONResponse({"success": False, "error": result.message if result else "解析失败"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/jd/parse-text")
async def parse_jd_text(req: JDTextRequest):
    agent = get_agent()
    try:
        result = await agent.invoke_skill("parse_jd", text=req.text)
        if result and result.success:
            return JSONResponse({
                "success": True,
                "data": result.data,
                "raw_text": req.text,
                "message": result.message,
            })
        return JSONResponse({"success": False, "error": result.message if result else "解析失败"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

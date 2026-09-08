"""JD 解析接口：/api/jd/parse-image、/api/jd/parse-text"""

import base64

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

from app.schemas.request import JDTextRequest
from app.services.agent_runtime import get_agent

router = APIRouter(prefix="/api", tags=["jd"])

@router.post("/jd/parse-image")
async def parse_jd_image(file: UploadFile = File(...)):
    agent = get_agent()
    try:
        contents = await file.read()
        image_b64 = base64.b64encode(contents).decode("utf-8")
        result = await agent.invoke_skill("parse_jd", image_base64=image_b64)
        if result and result.success:
            return JSONResponse({
                "success": True,
                "data": result.data,
                "raw_text": result.data.get("raw_text", ""),
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


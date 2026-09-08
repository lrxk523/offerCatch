"""测试 PDF 简历上传 API 返回"""
import requests
import json
import sys

url = 'http://localhost:7860/api/resume/optimize-file'
pdf_path = r'static/pdf/寇宇坤-实施开发工程师-17709256932(1).pdf'

print('上传 PDF 简历中...')
try:
    with open(pdf_path, 'rb') as f:
        files = {'file': ('test.pdf', f, 'application/pdf')}
        data = {'target_position': '实施开发工程师'}
        resp = requests.post(url, files=files, data=data, timeout=300)
except Exception as e:
    print(f'请求异常: {e}')
    sys.exit(1)

print(f'状态码: {resp.status_code}')
print(f'响应长度: {len(resp.text)} 字符')

try:
    result = resp.json()
except:
    print(f'响应非 JSON: {resp.text[:500]}')
    sys.exit(1)

print(f'success: {result.get("success")}')

if result.get('success'):
    d = result.get('data', {})
    print(f'data keys: {list(d.keys())}')
    print(f'data type: {type(d)}')
    
    opt = d.get('optimized', {})
    print(f'optimized keys: {list(opt.keys()) if isinstance(opt, dict) else type(opt)}')
    print(f'work_experience: {len(opt.get("work_experience", [])) if isinstance(opt, dict) else "N/A"}')
    print(f'project_experience: {len(opt.get("project_experience", [])) if isinstance(opt, dict) else "N/A"}')
    
    # 打印完整 optimized 的一部分
    if isinstance(opt, dict):
        we = opt.get('work_experience', [])
        if we:
            print(f'\n--- 第一段工作经历 ---')
            print(json.dumps(we[0], ensure_ascii=False, indent=2)[:500])
        
        pe = opt.get('project_experience', [])
        if pe:
            print(f'\n--- 第一个项目经历 ---')
            print(json.dumps(pe[0], ensure_ascii=False, indent=2)[:500])
        
        summary = opt.get('optimization_summary', '')
        if summary:
            print(f'\n--- 优化建议 ---')
            print(str(summary)[:300])
    
    print(f'\nmessage: {str(result.get("message", ""))[:200]}')
    print(f'resume_id: {result.get("resume_id", "")}')
    print(f'raw_text 长度: {len(result.get("raw_text", ""))}')
else:
    print(f'error: {result.get("error")}')
    print(f'完整响应: {json.dumps(result, ensure_ascii=False)[:1000]}')

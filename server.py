#!/usr/bin/env python3
"""
飞书多维表格插件后端
基于新多维表格 LnP7bzkxbaP1sIsThMXc86hln95
"""

import json, os, subprocess, sys, time, threading
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# CORS 支持
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/api/<path:path>', methods=['OPTIONS'])
def options_handler(path):
    return '', 200

# ============ 配置 ============
APP_TOKEN = "LnP7bzkxbaP1sIsThMXc86hln95"
SUMMARY_TABLE = "tbl13zwiSdsfAzX9"
DETAIL_TABLES = {
    "土耳其": "tbljMyXVg2EOAo7x",
    "孟加拉": "tblzV0JmbyPpdAL3",
    "印度": "tblRnRCMjUC17EDO",
    "埃及": "tbls0KPnHW8mdOeS",
}
EAM_BASE_URL = "https://eam.asset.mioffice.cn/main.html"
EAM_PROFILES_DIR = os.path.join(os.path.expanduser("~"), ".cache", "eam-profiles")
os.makedirs(EAM_PROFILES_DIR, exist_ok=True)

# ============ 飞书 CLI ============
def feishu(args):
    cmd = ("feishu.cmd" if sys.platform == "win32" else "feishu")
    result = subprocess.run([cmd] + args, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except:
        return None

def bitable_records(table_id):
    data = feishu(["bitable", "records", APP_TOKEN, table_id, "--page-size", "500"])
    return data.get("records", []) if data else []

def bitable_update(table_id, record_id, fields):
    cmd = ["bitable", "update-record", APP_TOKEN, table_id, record_id, "--fields", json.dumps(fields, ensure_ascii=False)]
    return feishu(cmd)

def feishu_fields(table_id):
    data = feishu(["bitable", "fields", APP_TOKEN, table_id])
    return data.get("fields", []) if data else []

# ============ EAM API ============
def get_profile_dir(user_code):
    """获取用户的浏览器配置目录"""
    profile_dir = os.path.join(EAM_PROFILES_DIR, user_code)
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir

def eam_login(user_code, password):
    """EAM登录，保存会话"""
    try:
        from playwright.sync_api import sync_playwright
    except:
        return False, "未安装Playwright"
    profile_dir = get_profile_dir(user_code)
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(profile_dir, headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu", "--no-sandbox"
            ])
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(EAM_BASE_URL, wait_until="networkidle", timeout=30000)
            # 尝试登录
            page.fill('input[name="username"], input[placeholder*="用户"], input[placeholder*="账号"]', user_code)
            page.fill('input[name="password"], input[placeholder*="密码"]', password)
            page.click('button[type="submit"], input[type="submit"], .login-btn, .btn-login')
            page.wait_for_load_state("networkidle", timeout=10000)
            # 检查是否登录成功
            if "login" not in page.url.lower():
                ctx.close()
                return True, "登录成功"
            ctx.close()
            return False, "登录失败，请检查账号密码"
    except Exception as e:
        return False, str(e)

def get_eam_sns(user_code, project_code=None):
    """查询EAM SN列表"""
    try:
        from playwright.sync_api import sync_playwright
    except:
        return []
    profile_dir = get_profile_dir(user_code)
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(profile_dir, headless=True, args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu", "--no-sandbox"
            ])
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(f"{EAM_BASE_URL}?usercode={user_code}", wait_until="networkidle", timeout=30000)
            result = page.evaluate("""async (userId) => {
                const p = new URLSearchParams({eventcode:'query_data',funid:'queryevent',pagetype:'grid',query_funid:'proto_card_user',user_id:userId});
                const r = await fetch('https://eam.asset.mioffice.cn/jxs/common?'+p.toString(),{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','X-Requested-With':'XMLHttpRequest'},body:'start=0&limit=50'});
                return await r.json();
            }""", user_code)
            items = []
            for item in result.get("data", {}).get("root", []):
                sn = item.get("proto_card__device_code", "")
                pc = item.get("proto_card__project_code", "")
                if sn:
                    items.append({"sn": sn, "project_code": pc})
            ctx.close()
    except Exception as e:
        print(f"EAM查询失败: {e}")
        return []
    if project_code is not None:
        return [i["sn"] for i in items if i["project_code"] == project_code]
    return [i["sn"] for i in items]

# ============ 辅助函数 ============
def extract_text(val):
    if isinstance(val, list) and val:
        return val[0].get("text", str(val[0])) if isinstance(val[0], dict) else str(val[0])
    if isinstance(val, dict):
        return val.get("text", val.get("name", str(val)))
    return str(val) if val else ""

def extract_user_code(p_account):
    if isinstance(p_account, list) and p_account:
        p = p_account[0]
        if isinstance(p, dict):
            email = p.get("email", "")
            if "@" in email: return email.split("@")[0]
            name = p.get("name", "")
            if name: return name
            return ""
        return str(p)
    text = str(p_account).strip() if p_account else ""
    if text in ("None", "null", ""): return ""
    if "@" in text: return text.split("@")[0]
    return text

def extract_person_name(p_account):
    if isinstance(p_account, list) and p_account:
        p = p_account[0]
        if isinstance(p, dict):
            name = p.get("name", p.get("en_name", ""))
            if name: return name
            email = p.get("email", "")
            if "@" in email: return email.split("@")[0]
            return ""
        return str(p)
    text = str(p_account) if p_account else ""
    if text in ("None", "null"): return ""
    return text

def find_detail_table(country):
    return DETAIL_TABLES.get(country, "")

# ============ API 路由 ============
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    user_code = data.get("user_code", "").strip()
    password = data.get("password", "").strip()
    if not user_code or not password:
        return jsonify({"ok": False, "error": "请输入EAM账号和密码"})
    success, msg = eam_login(user_code, password)
    return jsonify({"ok": success, "message": msg, "user_code": user_code})

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "status": "running"})

@app.route("/api/overview")
def overview():
    records = bitable_records(SUMMARY_TABLE)
    total = matched = pending = overdue = 0
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for r in records:
        f = r.get("fields", {})
        pc = extract_text(f.get("项目代号", ""))
        if not pc or pc == "None": continue
        total += 1
        ms = extract_text(f.get("SN匹配状态", ""))
        if ms == "已匹配": matched += 1
        elif ms == "待匹配": pending += 1
        eta = f.get("ETA时间")
        if eta:
            try:
                if isinstance(eta, str):
                    eta_dt = datetime.fromisoformat(eta.replace("Z", "+00:00")).replace(tzinfo=None)
                elif isinstance(eta, (int, float)):
                    eta_dt = datetime.fromtimestamp(eta / 1000)
                else:
                    eta_dt = None
                if eta_dt and eta_dt.date() < today.date() and ms != "已匹配":
                    overdue += 1
            except: pass
    return jsonify({"ok": True, "total": total, "matched": matched, "pending": pending, "overdue": overdue})

@app.route("/api/projects")
def projects():
    records = bitable_records(SUMMARY_TABLE)
    project_list = []
    for r in records:
        f = r.get("fields", {})
        pc = extract_text(f.get("项目代号", ""))
        if not pc or pc == "None": continue
        co = extract_text(f.get("本地产国家", "")) if f.get("本地产国家") else "未分配"
        ms = extract_text(f.get("SN匹配状态", ""))
        person = extract_person_name(f.get("P账号挂账人", ""))
        table_id = find_detail_table(co)
        bitable_sns = [str(rr["fields"]["SN"]) for rr in bitable_records(table_id) if rr["fields"].get("SN")] if table_id else []
        project_list.append({
            "id": r["record_id"],
            "name": pc,
            "country": co,
            "status": ms or "未检查",
            "person": person,
            "sn_count": len(bitable_sns),
        })
    return jsonify({"ok": True, "projects": project_list})

@app.route("/api/check/<record_id>")
def api_check(record_id):
    # 优先使用请求中的 user_code，否则从多维表格读取
    user_code = request.args.get("user_code", "").strip()
    records = bitable_records(SUMMARY_TABLE)
    rec = next((r for r in records if r.get("record_id") == record_id), None)
    if not rec: return jsonify({"ok": False, "error": "记录不存在"})
    f = rec.get("fields", {})
    pc = extract_text(f.get("项目代号", ""))
    co = extract_text(f.get("本地产国家", "")) if f.get("本地产国家") else ""
    if not user_code:
        user_code = extract_user_code(f.get("P账号挂账人", ""))
    if not user_code: return jsonify({"ok": False, "error": "无P账号"})
    table_id = find_detail_table(co)
    if not table_id: return jsonify({"ok": False, "error": f"{co}无明细表"})
    bitable_sns = [str(r["fields"]["SN"]) for r in bitable_records(table_id) if r["fields"].get("SN")]
    if not bitable_sns: return jsonify({"ok": False, "error": f"{co}无SN数据"})
    eam_sns = get_eam_sns(user_code, pc)
    b, e = set(bitable_sns), set(eam_sns)
    missing = sorted(b - e)
    matched_list = sorted(b & e)
    extra = sorted(e - b)
    new_status = "已匹配" if not missing else "待匹配"
    bitable_update(SUMMARY_TABLE, record_id, {
        "SN匹配状态": new_status,
        "SN匹配数": len(matched_list),
        "EAM SN数": len(e),
        "缺失SN数": len(missing),
    })
    return jsonify({
        "ok": True, "status": new_status,
        "matched": len(matched_list), "missing": len(missing),
        "total_bitable": len(b), "total_eam": len(e),
        "matched_list": matched_list, "missing_list": missing, "extra_list": extra,
    })

@app.route("/api/check-all")
def api_check_all():
    user_code = request.args.get("user_code", "").strip()
    records = bitable_records(SUMMARY_TABLE)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    checked = 0
    for rec in records:
        f = rec.get("fields", {})
        eta = f.get("ETA时间")
        if not eta: continue
        try:
            if isinstance(eta, str):
                eta_dt = datetime.fromisoformat(eta.replace("Z", "+00:00")).replace(tzinfo=None)
            elif isinstance(eta, (int, float)):
                eta_dt = datetime.fromtimestamp(eta / 1000)
            else:
                continue
        except: continue
        if (eta_dt + timedelta(days=2)).date() != today.date(): continue
        rid = rec["record_id"]
        pc = extract_text(f.get("项目代号", ""))
        co = extract_text(f.get("本地产国家", "")) if f.get("本地产国家") else ""
        if not user_code:
            user_code = extract_user_code(f.get("P账号挂账人", ""))
        if not user_code: continue
        table_id = find_detail_table(co)
        if not table_id: continue
        bitable_sns = [str(r["fields"]["SN"]) for r in bitable_records(table_id) if r["fields"].get("SN")]
        if not bitable_sns: continue
        eam_sns = get_eam_sns(user_code, pc)
        missing = set(bitable_sns) - set(eam_sns)
        matched_list = list(set(bitable_sns) & set(eam_sns))
        new_status = "已匹配" if not missing else "待匹配"
        bitable_update(SUMMARY_TABLE, rid, {
            "SN匹配状态": new_status,
            "SN匹配数": len(matched_list),
            "EAM SN数": len(eam_sns),
            "缺失SN数": len(missing),
        })
        checked += 1
    return jsonify({"ok": True, "checked": checked})

from datetime import timedelta

if __name__ == "__main__":
    print("=== SN管理面板插件后端 ===")
    print("访问: http://localhost:80")
    app.run(host="0.0.0.0", port=80, debug=False)

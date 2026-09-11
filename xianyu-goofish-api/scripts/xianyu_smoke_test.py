#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闲鱼/Goofish MTOP 与 IM WebSocket smoke 测试工具。只输出状态摘要，不打印 Cookie、sign 或 accessToken。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import random
import time
import urllib.parse
import uuid
from http.cookies import SimpleCookie
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

try:
    import requests
except ImportError as exc:
    raise SystemExit("缺少 requests，请先安装：python -m pip install requests") from exc

SIGN_APP_KEY = "34839810"
WS_APP_KEY = "444e9908a51d1cb236a27862abc769c9"
BASE_HEADERS = {
    "accept": "application/json",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://www.goofish.com",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://www.goofish.com/",
    "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Google Chrome\";v=\"133\", \"Chromium\";v=\"133\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
}

API_ENDPOINTS = {
    "login_status": ("mtop.taobao.idlemessage.pc.loginuser.get", "1.0", "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.loginuser.get/1.0/"),
    "token": ("mtop.taobao.idlemessage.pc.login.token", "1.0", "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/"),
    "profile": ("mtop.idle.web.user.page.nav", "1.0", "https://h5api.m.goofish.com/h5/mtop.idle.web.user.page.nav/1.0/"),
    "item_list": ("mtop.idle.web.xyh.item.list", "1.0", "https://h5api.m.goofish.com/h5/mtop.idle.web.xyh.item.list/1.0/"),
    "item_detail": ("mtop.taobao.idle.pc.detail", "1.0", "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"),
    "sold_orders": ("mtop.taobao.idle.trade.merchant.sold.get", "1.0", "https://h5api.m.goofish.com/h5/mtop.taobao.idle.trade.merchant.sold.get/1.0/"),
}


def read_cookie(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def parse_cookie_pairs(cookie: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        if name:
            pairs.append((name, value))
    return pairs


def cookie_dict(cookie: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for name, value in parse_cookie_pairs(cookie):
        result[name] = value
    return result


def cookie_value_ordered(cookie: str, key: str) -> str:
    for name, value in parse_cookie_pairs(cookie):
        if name == key:
            return value
    return ""


def merge_set_cookie(cookie: str, response: requests.Response) -> str:
    jar = cookie_dict(cookie)
    raw_values: List[str] = []
    if hasattr(response.raw, "headers"):
        try:
            raw_values = list(response.raw.headers.getlist("Set-Cookie"))
        except Exception:
            raw_values = []
    if not raw_values:
        header = response.headers.get("Set-Cookie", "")
        if header:
            raw_values = [header]
    for raw in raw_values:
        parsed = SimpleCookie()
        try:
            parsed.load(raw)
        except Exception:
            continue
        for name, morsel in parsed.items():
            if morsel.value == "":
                jar.pop(name, None)
            else:
                jar[name] = morsel.value
    return "; ".join(f"{k}={v}" for k, v in jar.items())


def sign(t: str, token: str, data: str) -> str:
    return hashlib.md5(f"{token}&{t}&{SIGN_APP_KEY}&{data}".encode("utf-8")).hexdigest()


def token_from_cookie(cookie: str) -> str:
    return cookie_value_ordered(cookie, "_m_h5_tk").split("_", 1)[0]


def device_id(user_id: str) -> str:
    return f"{uuid.uuid4()}-{user_id}"


def mid() -> str:
    return f"{random.randrange(1000)}{int(time.time() * 1000)} 0"


def ret_success(ret: Iterable[str]) -> bool:
    return any("SUCCESS" in str(item) for item in ret or [])


def ret_summary(payload: Mapping[str, Any]) -> str:
    ret = payload.get("ret")
    if isinstance(ret, list):
        return "; ".join(str(x) for x in ret[:3])
    return str(ret)


def mtop_call(cookie: str, endpoint: str, api: str, version: str, data_obj: Any, *, referer: str = "https://www.goofish.com/", response_type: str = "originaljson", extra_params: Optional[Mapping[str, str]] = None, origin: Optional[str] = None) -> Tuple[Dict[str, Any], str, int]:
    data = json.dumps(data_obj, ensure_ascii=False, separators=(",", ":"))
    t = str(int(time.time() * 1000))
    token = token_from_cookie(cookie)
    if not token:
        raise RuntimeError("cookie 缺少 _m_h5_tk，无法签名")
    params: Dict[str, str] = {
        "jsv": "2.7.2", "appKey": SIGN_APP_KEY, "t": t, "sign": sign(t, token, data), "v": version,
        "type": response_type, "accountSite": "xianyu", "dataType": "json", "timeout": "20000", "api": api,
        "sessionOption": "AutoLoginOnly",
    }
    if extra_params:
        params.update(dict(extra_params))
    headers = dict(BASE_HEADERS)
    headers["referer"] = referer
    headers["cookie"] = cookie
    if origin:
        headers["origin"] = origin
    response = requests.post(endpoint, params=params, data={"data": data}, headers=headers, timeout=25)
    response.encoding = "utf-8"
    new_cookie = merge_set_cookie(cookie, response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{api} 返回非 JSON: http={response.status_code} text={response.text[:160]!r}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{api} 响应不是对象: {type(payload).__name__}")
    return payload, new_cookie, response.status_code


def print_result(name: str, payload: Mapping[str, Any], status: int, ok_if_success: bool = True) -> bool:
    ok = ret_success(payload.get("ret", []))
    state = "PASS" if (ok or not ok_if_success) else "WARN"
    print(f"[{state}] {name}: http={status}, ret={ret_summary(payload)}")
    return ok


def extract_items(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    card_list = data.get("cardList") or data.get("items") or []
    items: List[Dict[str, Any]] = []
    if not isinstance(card_list, list):
        return items
    for card in card_list:
        if not isinstance(card, dict):
            continue
        card_data = card.get("cardData") if isinstance(card.get("cardData"), dict) else card
        detail_params = card_data.get("detailParams") if isinstance(card_data.get("detailParams"), dict) else {}
        item_id = str(detail_params.get("itemId") or card_data.get("id") or "").strip()
        if item_id and not item_id.startswith("auto_"):
            price_info = card_data.get("priceInfo") if isinstance(card_data.get("priceInfo"), dict) else {}
            items.append({"item_id": item_id, "title": str(card_data.get("title") or "")[:60], "price": str(price_info.get("price") or "")})
    return items


def test_login_status(cookie: str) -> Tuple[bool, str]:
    api, version, endpoint = API_ENDPOINTS["login_status"]
    payload, cookie, status = mtop_call(cookie, endpoint, api, version, {}, referer="https://www.goofish.com/im", extra_params={"spm_cnt": "a21ybx.im.0.0", "needLogin": "false"})
    return print_result("loginuser.get", payload, status), cookie


def test_profile(cookie: str) -> Tuple[bool, str]:
    api, version, endpoint = API_ENDPOINTS["profile"]
    payload, cookie, status = mtop_call(cookie, endpoint, api, version, {}, extra_params={"spm_cnt": "a21ybx.home.0.0", "ecode": "0"})
    ok = print_result("user.page.nav", payload, status)
    if ok:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        module = data.get("module") if isinstance(data.get("module"), dict) else {}
        base = module.get("base") if isinstance(module.get("base"), dict) else {}
        nick = base.get("displayName") or base.get("displayNick") or ""
        print(f"      nick={str(nick)[:24]!r}")
    return ok, cookie


def test_token(cookie: str, did: str) -> Tuple[bool, str, Optional[str]]:
    api, version, endpoint = API_ENDPOINTS["token"]
    data = {"appKey": WS_APP_KEY, "deviceId": did}
    payload, cookie, status = mtop_call(cookie, endpoint, api, version, data, referer="https://www.goofish.com/im", extra_params={"needLoginPC": "false", "showErrorToast": "false", "needLogin": "false", "ecode": "0", "dangerouslySetWindvaneParams": "%5Bobject%20Object%5D", "spm_cnt": "a21ybx.im.0.0"})
    ok = print_result("login.token", payload, status)
    access_token = None
    if ok:
        data_map = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        access_token = data_map.get("accessToken") if isinstance(data_map.get("accessToken"), str) else None
        exp = data_map.get("accessTokenExpiredTime")
        print(f"      accessToken_present={bool(access_token)}, expire={exp}")
    return ok, cookie, access_token


def test_item_list(cookie: str, page_size: int) -> Tuple[bool, str, List[Dict[str, Any]]]:
    api, version, endpoint = API_ENDPOINTS["item_list"]
    user_id = cookie_value_ordered(cookie, "unb")
    data = {"needGroupInfo": False, "pageNumber": 1, "pageSize": page_size, "groupName": "在售", "groupId": "58877261", "defaultGroup": True, "userId": user_id}
    payload, cookie, status = mtop_call(cookie, endpoint, api, version, data, extra_params={"spm_cnt": "a21ybx.im.0.0", "spm_pre": "a21ybx.collection.menu.1"})
    ok = print_result("item.list", payload, status)
    items = extract_items(payload) if ok else []
    print(f"      items={len(items)}" + (f", first_item=***{items[0]['item_id'][-4:]} title={items[0]['title']!r}" if items else ""))
    return ok, cookie, items


def test_item_detail(cookie: str, item_id: str) -> Tuple[bool, str]:
    api, version, endpoint = API_ENDPOINTS["item_detail"]
    referer = f"https://www.goofish.com/item?spm=a21ybx.im.0.0&id={urllib.parse.quote(str(item_id))}"
    payload, cookie, status = mtop_call(cookie, endpoint, api, version, {"itemId": str(item_id)}, referer=referer, extra_params={"spm_cnt": "a21ybx.im.0.0"})
    ok = print_result("item.detail", payload, status)
    if ok:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        item_do = data.get("itemDO") if isinstance(data.get("itemDO"), dict) else {}
        title = item_do.get("title") or data.get("title") or ""
        sku_count = len(item_do.get("skuList") or []) if isinstance(item_do.get("skuList"), list) else 0
        print(f"      item=***{str(item_id)[-4:]}, title={str(title)[:60]!r}, sku_count={sku_count}")
    return ok, cookie


def test_sold_orders(cookie: str, page_size: int) -> Tuple[bool, str]:
    api, version, endpoint = API_ENDPOINTS["sold_orders"]
    payload_data = {"pageNumber": 1, "rowsPerPage": page_size, "orderIds": "", "queryCode": "ALL", "orderSearchParam": "{}"}
    payload, cookie, status = mtop_call(cookie, endpoint, api, version, payload_data, referer="https://seller.goofish.com/?site=COMMONPRO#/seller-trade/order-manage", origin="https://seller.goofish.com", response_type="json", extra_params={"valueType": "string", "spm_cnt": "a21107h.42831410.0.0"})
    ok = print_result("sold.orders", payload, status)
    return ok, cookie


async def test_ws(cookie: str, did: str, access_token: str, timeout_seconds: float) -> bool:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("缺少 websockets，请先安装：python -m pip install websockets") from exc
    token = urllib.parse.unquote(access_token)
    raw_ua = BASE_HEADERS["user-agent"]
    reg_ua = f"{raw_ua} DingTalk(2.2.0) OS(Windows/10) Browser(Chrome/133.0.0.0) DingWeb/2.2.0 IMPaaS DingWeb/2.2.0"
    headers = {"Origin": "https://www.goofish.com", "User-Agent": raw_ua, "Cookie": cookie}
    uri = "wss://wss-goofish.dingtalk.com:443"
    connect_params = inspect.signature(websockets.connect).parameters
    if "additional_headers" in connect_params:
        ws_cm = websockets.connect(uri, additional_headers=headers, open_timeout=20, close_timeout=5)
    else:
        ws_cm = websockets.connect(uri, extra_headers=headers, open_timeout=20, close_timeout=5)
    async with ws_cm as ws:
        reg_mid = mid()
        await ws.send(json.dumps({"lwp": "/reg", "headers": {"cache-header": "app-key token ua wv", "app-key": WS_APP_KEY, "token": token, "ua": reg_ua, "dt": "j", "wv": "im:3,au:3,sy:6", "sync": "0,0;0;0;", "did": did, "mid": reg_mid}}, ensure_ascii=False))
        deadline = time.time() + timeout_seconds
        reg_ok = False
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
            except asyncio.TimeoutError:
                break
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if isinstance(msg, dict) and isinstance(msg.get("headers"), dict) and msg["headers"].get("mid"):
                await ws.send(json.dumps({"code": 200, "headers": msg["headers"]}, ensure_ascii=False))
            if isinstance(msg, dict) and msg.get("code") == 200:
                reg_ok = True
                break
        print(f"[{'PASS' if reg_ok else 'WARN'}] websocket.reg: registered={reg_ok}, waited={timeout_seconds}s")
        return reg_ok


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="闲鱼 Goofish API smoke test（不会打印 Cookie/Token/sign）")
    parser.add_argument("--cookie-file", required=True, help="cookie.txt 路径")
    parser.add_argument("--item-id", default="", help="要验证的商品 ID；为空时尝试取商品列表第一条")
    parser.add_argument("--page-size", type=int, default=5)
    parser.add_argument("--all", action="store_true", help="执行登录态、资料、Token、商品列表、商品详情")
    parser.add_argument("--login-status", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--token", action="store_true")
    parser.add_argument("--item-list", action="store_true")
    parser.add_argument("--item-detail", action="store_true")
    parser.add_argument("--sold-orders", action="store_true")
    parser.add_argument("--ws", action="store_true", help="获取 Token 后注册 WebSocket，成功后立即关闭")
    parser.add_argument("--ws-timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    cookie = read_cookie(args.cookie_file)
    cookies = cookie_dict(cookie)
    missing = [key for key in ("unb", "_m_h5_tk") if not cookies.get(key)]
    if missing:
        print(f"[FAIL] cookie 缺少必要字段: {', '.join(missing)}")
        return 2
    print(f"[PASS] cookie.loaded: pairs={len(cookies)}, unb=***{cookies['unb'][-4:]}, mtop_token_present={bool(token_from_cookie(cookie))}")
    sample = sign("1700000000000", "token", '{"x":1}')
    expected = hashlib.md5(b'token&1700000000000&34839810&{"x":1}').hexdigest()
    print(f"[{'PASS' if sample == expected else 'FAIL'}] sign.selfcheck")
    if sample != expected:
        return 2

    run_all = args.all or not any([args.login_status, args.profile, args.token, args.item_list, args.item_detail, args.sold_orders, args.ws])
    item_id = args.item_id.strip()
    access_token = None
    did = device_id(cookies["unb"])

    try:
        if run_all or args.login_status:
            _, cookie = test_login_status(cookie)
        if run_all or args.profile:
            _, cookie = test_profile(cookie)
        if run_all or args.token or args.ws:
            _, cookie, access_token = test_token(cookie, did)
        items: List[Dict[str, Any]] = []
        if run_all or args.item_list or (not item_id and args.item_detail):
            _, cookie, items = test_item_list(cookie, args.page_size)
            if not item_id and items:
                item_id = items[0]["item_id"]
        if run_all or args.item_detail:
            if item_id:
                _, cookie = test_item_detail(cookie, item_id)
            else:
                print("[SKIP] item.detail: 商品列表为空且未传 --item-id")
        if args.sold_orders:
            _, cookie = test_sold_orders(cookie, args.page_size)
        if args.ws:
            if not access_token:
                _, cookie, access_token = test_token(cookie, did)
            if access_token:
                asyncio.run(test_ws(cookie, did, access_token, args.ws_timeout))
            else:
                print("[WARN] websocket.reg: 未取得 accessToken，跳过")
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

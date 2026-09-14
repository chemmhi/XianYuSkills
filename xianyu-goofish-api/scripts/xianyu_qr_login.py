#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闲鱼/Goofish 扫码登录 Cookie 提取工具。默认只打印脱敏状态，完整 Cookie 仅写入显式指定文件。"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import sys
import time
import urllib.parse
import uuid
import warnings
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

warnings.filterwarnings("ignore", message=r"urllib3 .*match a supported version!")

try:
    import requests
except ImportError as exc:
    raise SystemExit("缺少 requests，请先安装：python -m pip install requests") from exc

APP_KEY = "34839810"
HOST = "https://passport.goofish.com"
API_H5TK = "https://h5api.m.goofish.com/h5/mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get/1.0/"
API_MINI_LOGIN = HOST + "/mini_login.htm"
API_GENERATE_QR = HOST + "/newlogin/qrcode/generate.do"
API_SCAN_STATUS = HOST + "/newlogin/qrcode/query.do"
API_FACE_CHECK = HOST + "/iv/photoVerify/check.do"
QR_VERIFY_TARGET = "https://www.goofish.com/im"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

PASSPORT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "origin": "https://passport.goofish.com",
    "pragma": "no-cache",
    "referer": "https://passport.goofish.com/",
    "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": USER_AGENT,
}

DOCUMENT_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "referer": "https://www.goofish.com/",
    "sec-ch-ua": PASSPORT_HEADERS["sec-ch-ua"],
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "upgrade-insecure-requests": "1",
    "user-agent": USER_AGENT,
}

STATUS_TEXT = {
    "NEW": "等待扫码",
    "SCANED": "已扫码，等待手机确认",
    "CONFIRMED": "已确认",
    "EXPIRED": "二维码已过期",
    "CANCELED": "用户取消",
    "ERROR": "平台返回错误状态",
}


def md5hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def masked(value: str) -> str:
    return "***" + value[-4:] if value else ""


def cookie_value(cookie_header: str, name: str) -> str:
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        if key == name:
            return value
    return ""


def cookie_pair_count(cookie_header: str) -> int:
    return sum(1 for part in cookie_header.split(";") if "=" in part)


def cookie_header_for(session: requests.Session, target_url: str) -> str:
    request = requests.Request("GET", target_url)
    prepared = session.prepare_request(request)
    return prepared.headers.get("Cookie", "")


def normalize_url(raw: str, base: str = HOST) -> str:
    value = html.unescape(str(raw or "")).replace(r"\/", "/").strip()
    if value.startswith("//"):
        value = "https:" + value
    return urllib.parse.urljoin(base + "/", value)


def extract_json_assignment(page_html: str, marker: str) -> Dict[str, Any]:
    marker_index = page_html.find(marker)
    if marker_index < 0:
        raise RuntimeError(f"未找到 {marker}")
    start_index = page_html.find("{", marker_index)
    if start_index < 0:
        raise RuntimeError(f"{marker} 后未找到 JSON 对象")
    depth = 0
    in_string = False
    escaping = False
    for index in range(start_index, len(page_html)):
        char = page_html[index]
        if in_string:
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(page_html[start_index : index + 1])
    raise RuntimeError(f"{marker} JSON 对象未闭合")


def extract_face_htoken(page_html: str) -> str:
    match = re.search(r"htoken=([A-Za-z0-9_\-]+)", page_html)
    if not match:
        raise RuntimeError("人脸验证：未能提取 htoken")
    return match.group(1)


def extract_verify_modes_url(page_html: str) -> str:
    match = re.search(r'window\.location\.href\s*=\s*"((?:https?:)?//[^"]*?/iv/mini/verify_modes\.htm\?[^"]*)"', page_html)
    if not match:
        raise RuntimeError("人脸验证：未能提取 verify_modes 链接")
    value = normalize_url(match.group(1))
    if value.endswith("_umidfg="):
        value += "1"
    return value


def extract_face_qrcode_content(page_html: str) -> str:
    match = re.search(r'new\s+Qrcode\(\{\s*text:\s*"((?:\\.|[^"\\])*)"', page_html)
    if not match:
        raise RuntimeError("人脸验证：未能提取人脸验证二维码内容")
    raw = match.group(1)
    try:
        content = json.loads('"' + raw + '"')
    except json.JSONDecodeError:
        content = raw
    content = html.unescape(content.replace(r"\/", "/")).strip()
    if not content:
        raise RuntimeError("人脸验证二维码内容为空")
    return content


def render_qr(content: str, label: str, output_dir: Optional[Path]) -> None:
    text_path: Optional[Path] = None
    png_path: Optional[Path] = None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        text_path = output_dir / f"{label}.txt"
        text_path.write_text(content, encoding="utf-8")
    try:
        import qrcode
    except ImportError:
        print(f"[INFO] {label}: 未安装 qrcode，二维码内容已写入 {text_path}" if text_path else f"[INFO] {label}: 未安装 qrcode，二维码内容如下")
        print(content)
        print("[INFO] 如需终端二维码/PNG：python -m pip install qrcode[pil]")
        return
    qr = qrcode.QRCode(border=2)
    qr.add_data(content)
    qr.make(fit=True)
    print(f"[SCAN] {label}: 请使用手机闲鱼扫描下方二维码")
    qr.print_ascii(invert=True)
    if output_dir:
        png_path = output_dir / f"{label}.png"
        qr.make_image(fill_color="black", back_color="white").save(png_path)
        print(f"[INFO] {label}: 已保存 {png_path}")


class QRLoginClient:
    def __init__(self, timeout: float, interval: float, qr_output_dir: Optional[Path]) -> None:
        self.timeout = timeout
        self.interval = interval
        self.qr_output_dir = qr_output_dir
        self.session = requests.Session()
        self.session_id = str(uuid.uuid4())
        self.login_params: Dict[str, str] = {}

    def request_headers(self, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        headers = dict(PASSPORT_HEADERS)
        if extra:
            headers.update(dict(extra))
        return headers

    def get_mh5tk(self) -> None:
        response = self.session.get(API_H5TK, headers=self.request_headers(), timeout=self.timeout)
        response.close()
        cookie_header = cookie_header_for(self.session, API_H5TK)
        token = cookie_value(cookie_header, "_m_h5_tk").split("_", 1)[0]
        data = '{"bizScene":"home"}'
        timestamp = str(int(time.time() * 1000))
        params = {
            "jsv": "2.7.2",
            "appKey": APP_KEY,
            "t": timestamp,
            "sign": md5hex(f"{token}&{timestamp}&{APP_KEY}&{data}"),
            "v": "1.0",
            "type": "originaljson",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.gaia.nodejs.gaia.idle.data.gw.v2.index.get",
            "data": data,
        }
        response = self.session.post(API_H5TK, params=params, headers=self.request_headers({"content-type": "application/x-www-form-urlencoded"}), timeout=self.timeout)
        response.close()
        refreshed = cookie_value(cookie_header_for(self.session, API_H5TK), "_m_h5_tk")
        if not refreshed:
            raise RuntimeError("初始化 _m_h5_tk 失败")
        print("[PASS] m_h5_tk.initialized")

    def get_login_params(self) -> Dict[str, str]:
        params = {
            "lang": "zh_cn",
            "appName": "xianyu",
            "appEntrance": "web",
            "styleType": "vertical",
            "bizParams": "",
            "notLoadSsoView": "false",
            "notKeepLogin": "false",
            "isMobile": "false",
            "qrCodeFirst": "false",
            "stie": "77",
            "rnd": str(random.random()),
        }
        response = self.session.get(API_MINI_LOGIN, params=params, headers=self.request_headers(), timeout=self.timeout)
        response.encoding = "utf-8"
        response.raise_for_status()
        view_data = extract_json_assignment(response.text, "window.viewData")
        form = view_data.get("loginFormData")
        if not isinstance(form, dict):
            raise RuntimeError("loginFormData 为空")
        login_params: Dict[str, str] = {}
        for key, value in form.items():
            if isinstance(value, bool):
                login_params[str(key)] = str(value).lower()
            elif value is None:
                login_params[str(key)] = ""
            else:
                login_params[str(key)] = str(value)
        login_params["umidTag"] = "SERVER"
        self.login_params = login_params
        print(f"[PASS] login.params: fields={len(login_params)}")
        return login_params

    def generate_qrcode(self) -> str:
        if not self.login_params:
            raise RuntimeError("生成二维码前缺少 loginFormData")
        response = self.session.get(API_GENERATE_QR, params=self.login_params, headers=self.request_headers(), timeout=self.timeout)
        response.encoding = "utf-8"
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content") if isinstance(payload, dict) else {}
        data = content.get("data") if isinstance(content, dict) else {}
        if not isinstance(content, dict) or not content.get("success"):
            raise RuntimeError(f"获取登录二维码失败: {str(payload)[:240]}")
        code_content = str(data.get("codeContent") or "").strip()
        if not code_content:
            raise RuntimeError("二维码响应缺少 codeContent")
        t_value = data.get("t")
        self.login_params["t"] = str(int(t_value)) if isinstance(t_value, float) else str(t_value)
        self.login_params["ck"] = str(data.get("ck") or "")
        print(f"[PASS] qr.generated: session_id={self.session_id}")
        render_qr(code_content, "login_qr", self.qr_output_dir)
        return code_content

    def poll_qrcode_status(self) -> Tuple[str, bool, str]:
        form = dict(self.login_params)
        form.update(
            {
                "ua": "",
                "navlanguage": "zh-CN",
                "navUserAgent": USER_AGENT,
                "navPlatform": "Win32",
                "isIframe": "true",
                "documentReferer": QR_VERIFY_TARGET,
                "defaultView": "qrcode",
            }
        )
        response = self.session.post(
            API_SCAN_STATUS,
            data=form,
            headers=self.request_headers({"content-type": "application/x-www-form-urlencoded"}),
            timeout=self.timeout,
        )
        response.encoding = "utf-8"
        response.raise_for_status()
        payload = response.json()
        if payload.get("hasError"):
            return "HAS_ERROR", False, ""
        content = payload.get("content") if isinstance(payload, dict) else {}
        data = content.get("data") if isinstance(content, dict) else {}
        if not isinstance(data, dict):
            return "UNKNOWN", False, ""
        status = str(data.get("qrCodeStatus") or "UNKNOWN")
        return status, bool(data.get("iframeRedirect")), normalize_url(str(data.get("iframeRedirectUrl") or ""))

    def complete_confirmed_login(self) -> Tuple[str, str]:
        response = self.session.get(QR_VERIFY_TARGET, headers=DOCUMENT_HEADERS, timeout=max(self.timeout, 30))
        response.close()
        cookie_header = cookie_header_for(self.session, QR_VERIFY_TARGET)
        unb = cookie_value(cookie_header, "unb")
        return cookie_header, unb

    def face_get_html(self, target_url: str, referer: str = "") -> str:
        headers = self.request_headers()
        if referer:
            headers["referer"] = referer
        response = self.session.get(target_url, headers=headers, timeout=max(self.timeout, 30))
        response.encoding = "utf-8"
        response.raise_for_status()
        return response.text

    def check_face_verification(self, htoken: str) -> Tuple[bool, str]:
        params = {"htoken": htoken}
        headers = self.request_headers(
            {
                "accept": "application/json, text/javascript, */*; q=0.01",
                "x-requested-with": "XMLHttpRequest",
                "referer": face_identity_referer(htoken),
            }
        )
        response = self.session.get(API_FACE_CHECK, params=params, headers=headers, timeout=self.timeout)
        response.encoding = "utf-8"
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content") if isinstance(payload, dict) else {}
        if isinstance(content, dict) and str(content.get("code")) == "3":
            return True, normalize_url(str(content.get("url") or ""))
        return False, ""

    def run_face_verification(self, iframe_url: str, deadline: float) -> Tuple[str, str]:
        normal_html = self.face_get_html(iframe_url)
        htoken = extract_face_htoken(normal_html)
        verify_modes_url = extract_verify_modes_url(normal_html)
        identity_html = self.face_get_html(verify_modes_url)
        face_content = extract_face_qrcode_content(identity_html)
        print("[INFO] verification.required: 需要手机闲鱼扫描人脸验证二维码")
        render_qr(face_content, "face_qr", self.qr_output_dir)
        last_notice = 0.0
        while time.time() < deadline:
            done, iv_check_url = self.check_face_verification(htoken)
            if done:
                self.face_get_html(iv_check_url, face_identity_referer(htoken))
                cookie_header, unb = self.complete_confirmed_login()
                return cookie_header, unb
            now = time.time()
            if now - last_notice >= 10:
                print("[WAIT] face.verification: 等待手机端完成")
                last_notice = now
            time.sleep(self.interval)
        raise RuntimeError("人脸验证超时")

    def run(self, output_cookie_file: Optional[Path], max_wait: float) -> int:
        self.get_mh5tk()
        self.get_login_params()
        self.generate_qrcode()
        deadline = time.time() + max_wait
        last_status = ""
        server_errors = 0
        while time.time() < deadline:
            status, iframe_redirect, iframe_url = self.poll_qrcode_status()
            if status == "HAS_ERROR":
                server_errors += 1
                if server_errors >= 5:
                    raise RuntimeError("扫码状态接口连续返回 hasError")
                continue
            server_errors = 0
            if status != last_status:
                print(f"[STATE] qr={status}: {STATUS_TEXT.get(status, '继续等待')}")
                last_status = status
            if status == "CONFIRMED":
                if iframe_redirect:
                    cookie_header, unb = self.run_face_verification(iframe_url, deadline)
                else:
                    cookie_header, unb = self.complete_confirmed_login()
                if not unb:
                    raise RuntimeError("扫码已确认但未获取到 unb，可能仍需安全验证或临时 Cookie 已失效")
                if output_cookie_file:
                    output_cookie_file.parent.mkdir(parents=True, exist_ok=True)
                    output_cookie_file.write_text(cookie_header, encoding="utf-8")
                    print(f"[PASS] cookie.saved: path={output_cookie_file}")
                print(f"[PASS] login.success: unb={masked(unb)}, cookie_pairs={cookie_pair_count(cookie_header)}")
                return 0
            if status in {"EXPIRED", "CANCELED", "ERROR"}:
                raise RuntimeError(STATUS_TEXT.get(status, status))
            time.sleep(self.interval)
        raise RuntimeError("扫码登录超时")


def face_identity_referer(htoken: str) -> str:
    return HOST + "/iv/mini/identity_verify.htm?htoken=" + urllib.parse.quote(htoken)


def run_self_test() -> int:
    view_html = '<script>window.viewData = {"loginFormData":{"a":1,"b":true,"c":"x"}};</script>'
    view_data = extract_json_assignment(view_html, "window.viewData")
    assert view_data["loginFormData"]["b"] is True
    normal_html = 'window.location.href = "//passport.goofish.com/iv/mini/verify_modes.htm?htoken=abc123&_umidfg=";'
    assert extract_face_htoken('x htoken=abc_DEF-123 y') == "abc_DEF-123"
    assert extract_verify_modes_url(normal_html).endswith("_umidfg=1")
    face_html = 'new Qrcode({ text: "https:\\/\\/passport.goofish.com\\/iv\\/scan?x=1&amp;y=2" })'
    assert extract_face_qrcode_content(face_html) == "https://passport.goofish.com/iv/scan?x=1&y=2"
    print("[PASS] self-test")
    return 0


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="闲鱼/Goofish 扫码登录 Cookie 提取工具；默认不打印完整 Cookie")
    parser.add_argument("--output-cookie-file", help="保存最终 Cookie Header 的文件路径；未指定时只做扫码状态验证，不落盘完整 Cookie")
    parser.add_argument("--qr-output-dir", help="保存 login_qr/face_qr 的 PNG 和原始内容；未安装 qrcode 时至少写入 txt")
    parser.add_argument("--timeout", type=float, default=25.0, help="单次 HTTP 请求超时秒数，默认 25")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="扫码/人脸验证轮询间隔秒数，默认 2")
    parser.add_argument("--max-wait", type=float, default=300.0, help="扫码整体等待秒数，默认 300")
    parser.add_argument("--self-test", action="store_true", help="只运行本地解析自检，不访问网络")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return run_self_test()
    output_file = Path(args.output_cookie_file).expanduser().resolve() if args.output_cookie_file else None
    output_dir = Path(args.qr_output_dir).expanduser().resolve() if args.qr_output_dir else None
    client = QRLoginClient(timeout=args.timeout, interval=args.poll_interval, qr_output_dir=output_dir)
    try:
        return client.run(output_file, max_wait=args.max_wait)
    except KeyboardInterrupt:
        print("[WARN] interrupted")
        return 130
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

---
name: xianyu-goofish-api
description: 复用闲鱼/Goofish 网页端能力：扫码添加账号、Cookie/Token 检查、MTOP 签名请求、商品/订单接口、IM WebSocket 监听与消息发送、发货/改价/评价/擦亮等能力抽取与 smoke 测试。
metadata:
  short-description: 闲鱼扫码登录、MTOP 与 IM WebSocket 能力
---

# 闲鱼 Goofish API Skill

当任务需要复用本地项目中已经验证过的闲鱼网页端能力时使用本 skill，包括扫码添加闲鱼账号、从 Cookie 发起 MTOP 请求、调用商品详情/商品列表/订单接口，以及建立闲鱼 IM WebSocket 监听买家消息。

## 先读这些资料

- 需要接口清单、参数或来源路径时，读取 references/api-capabilities.md。
- 需要扫码添加账号或重新获取 Cookie 时，运行 scripts/xianyu_qr_login.py；它只打印脱敏状态，Cookie 仅写入显式指定的输出文件。
- 需要直接验证 Cookie、Token、商品详情或 WebSocket 注册时，运行 scripts/xianyu_smoke_test.py。
- 需要在新项目落地时，优先复用 scripts/xianyu_qr_login.py 的扫码会话流程，以及 scripts/xianyu_smoke_test.py 中的签名、headers、payload 构造方式，再按业务拆分为客户端类。

## 核心规则

- 扫码添加账号走 passport.goofish.com：先初始化 _m_h5_tk，再访问 mini_login.htm 提取 window.viewData.loginFormData，随后调用 /newlogin/qrcode/generate.do 生成 codeContent，并以 /newlogin/qrcode/query.do 轮询 NEW、SCANED、CONFIRMED、EXPIRED、CANCELED、ERROR。
- query.do 必须沿用生成二维码时的 loginFormData，并补 ua、navlanguage、navUserAgent、navPlatform、isIframe、documentReferer、defaultView；CONFIRMED 且 iframeRedirect=true 时，保留临时 Cookie 并进入 /iv/mini 人脸验证流程。
- 人脸验证必须用同一个 Cookie Jar 贯穿 normal_validate、verify_modes、identity_verify、photoVerify/check.do 和 ivCheckLogin；不要拆成多个无状态请求，否则最终通常拿不到 unb。
- 扫码成功后的真实凭证以访问 https://www.goofish.com/im 后面向该 URL 的 Cookie Header 为准；输出和日志只展示账号 ID 后几位、Cookie 数量和状态，完整 Cookie 只写入用户指定文件。
- MTOP 签名固定为 md5(token + "&" + t + "&" + "34839810" + "&" + data)；token 取 Cookie _m_h5_tk 下划线前半段，data 必须与 HTTP body 中 data= 的 JSON 原文一致。
- MTOP 通用请求使用 POST https://h5api.m.goofish.com/h5/{api}/{v}/，body 为 application/x-www-form-urlencoded 的 data={urlencoded-json}，query 带 jsv=2.7.2、appKey=34839810、t、sign、v、type、accountSite=xianyu、dataType=json、timeout=20000、api、sessionOption=AutoLoginOnly。
- headers 模拟网页端 XHR：accept: application/json、origin: https://www.goofish.com、referer 按场景设置、sec-fetch-site: same-site、浏览器 UA/Client-Hints、完整 Cookie。订单工作台接口 referer/origin 使用 https://seller.goofish.com。
- Token API 的 deviceId 必须与 WebSocket /reg.headers.did 完全一致；accessToken 注册前做 URL decode。
- WebSocket 地址为 wss://wss-goofish.dingtalk.com:443（Python 项目也使用无端口形式），连接后发送 /reg，服务端推送从 body.syncPushPackage.data[0].data 解出消息。
- 收到带 headers.mid 的 WS 帧后回 ACK：{"code":200,"headers":原 headers}；心跳帧为 {"lwp":"/!","headers":{"mid":...}}。
- 买家聊天消息的关键字段通常在解密后的 message["1"]["10"]：reminderContent 文本、senderUserId 买家 ID、reminderTitle 昵称、reminderUrl 含 itemId；会话 ID 来自 message["1"]["2"] 去掉 @goofish。
- 同步包解码顺序：先尝试 base64 -> JSON（部分系统包），失败再 base64 -> MessagePack -> JSON；MessagePack map 键需要统一转字符串。
- 不要在输出、日志或测试结果里回显完整 Cookie、Token、sign、accessToken；只输出状态、ret 摘要、条数、脱敏 ID 后几位。

## 常用命令

    python F:\ChenHai\Project\XianYuSkills\xianyu-goofish-api\scripts\xianyu_qr_login.py --output-cookie-file F:\ChenHai\Project\Ydisks-Xianyu-Helper\cookie.txt --qr-output-dir .\qr-output
    python F:\ChenHai\Project\XianYuSkills\xianyu-goofish-api\scripts\xianyu_qr_login.py --self-test
    python F:\ChenHai\Project\XianYuSkills\xianyu-goofish-api\scripts\xianyu_smoke_test.py --cookie-file F:\ChenHai\Project\Ydisks-Xianyu-Helper\cookie.txt --all --ws
    python F:\ChenHai\Project\XianYuSkills\xianyu-goofish-api\scripts\xianyu_smoke_test.py --cookie-file .\cookie.txt --item-id <itemId> --item-detail

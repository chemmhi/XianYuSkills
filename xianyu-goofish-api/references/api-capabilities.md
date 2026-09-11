# 闲鱼能力/API 提取说明

本资料来自两个本地项目的源码梳理：

- F:\ChenHai\Project\Ydisks-Xianyu-Helper（Go）：internal/xianyu/mtop、internal/xianyu/ws、internal/xianyu/protocol、internal/engine、internal/adapter。
- F:\ChenHai\Project\XianyuAutoReply\XianyuAutoAgent（Python）：XianyuApis.py、main.py、utils/xianyu_utils.py。

## 认证与签名

- Cookie 解析：unb 是当前账号 ID；_m_h5_tk 是 MTOP 签名 token 来源；cookie2、cna、x5sec 等随完整 Cookie 透传。
  - Go 来源：internal/xianyu/protocol/cookies.go、internal/xianyu/mtop/cookie_session.go。
  - Python 来源：utils/xianyu_utils.py::trans_cookies、get_cookie_value_ordered。
- MTOP 签名：md5(token + "&" + t + "&" + "34839810" + "&" + data)。
  - Go 来源：internal/xianyu/protocol/sign.go::GenerateSign。
  - Python 来源：utils/xianyu_utils.py::generate_sign。
- CookieSession 差异：Go 项目区分“参与签名的 document cookie”和“请求 URL scope cookie”，并吸收响应 Set-Cookie；移植时要保留响应 Cookie 更新链路。
  - Go 来源：internal/xianyu/mtop/cookie_session.go、client.go::mergeSetCookie。

## MTOP 通用参数

通用 query：

    jsv=2.7.2
    appKey=34839810
    t=<毫秒时间戳>
    sign=<md5签名>
    v=<接口版本>
    type=originaljson 或 json
    accountSite=xianyu
    dataType=json
    timeout=20000
    api=<MTOP API 名>
    sessionOption=AutoLoginOnly

通用 body：

    data=<urlencode(JSON原文)>

通用 headers：

    accept: application/json
    accept-language: zh-CN,zh;q=0.9,en;q=0.8
    cache-control: no-cache
    content-type: application/x-www-form-urlencoded
    origin: https://www.goofish.com
    pragma: no-cache
    referer: https://www.goofish.com/ 或具体页面
    sec-fetch-dest: empty
    sec-fetch-mode: cors
    sec-fetch-site: same-site
    cookie: <完整 Cookie>
    user-agent / sec-ch-ua / sec-ch-ua-mobile / sec-ch-ua-platform: 模拟当前浏览器

## 已提取能力清单

| 能力 | API / WS 路径 | 版本 | Endpoint / 地址 | data 关键字段 | 来源路径 |
|---|---|---:|---|---|---|
| IM accessToken 获取 | mtop.taobao.idlemessage.pc.login.token | 1.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/ | {"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"<did>"} | Go internal/xianyu/mtop/token.go；Python XianyuApis.py::get_token |
| 低成本登录态检查 | mtop.taobao.idlemessage.pc.loginuser.get | 1.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.loginuser.get/1.0/ | {} | Go internal/xianyu/mtop/login_status.go |
| 账号资料 | mtop.idle.web.user.page.nav | 1.0 | https://h5api.m.goofish.com/h5/mtop.idle.web.user.page.nav/1.0/ | {} | Go internal/xianyu/mtop/user_profile.go |
| 卖家商品列表 | mtop.idle.web.xyh.item.list | 1.0 | https://h5api.m.goofish.com/h5/mtop.idle.web.xyh.item.list/1.0/ | needGroupInfo=false,pageNumber,pageSize,groupName=在售,groupId=58877261,defaultGroup=true,userId=<unb> | Go internal/xianyu/mtop/items.go |
| 商品详情/产品详情 | mtop.taobao.idle.pc.detail | 1.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/ | {"itemId":"<itemId>"}；referer https://www.goofish.com/item?spm=a21ybx.im.0.0&id=<itemId> | Go internal/xianyu/mtop/item_detail.go；Python XianyuApis.py::get_item_info |
| 卖家已售订单列表 | mtop.taobao.idle.trade.merchant.sold.get | 1.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idle.trade.merchant.sold.get/1.0/ | pageNumber,rowsPerPage,orderIds="",queryCode="ALL",orderSearchParam="{}"；origin/referer 为 seller.goofish.com | Go internal/xianyu/mtop/sold_orders.go |
| 订单详情 | mtop.idle.web.trade.order.detail | 1.0 | https://h5api.m.goofish.com/h5/mtop.idle.web.trade.order.detail/1.0/ | {"tid":"<orderId>"}；referer https://www.goofish.com/order-detail?orderId=<orderId>&role=seller | Go internal/xianyu/mtop/order_detail.go、internal/browser/orders.go |
| 虚拟发货确认 | mtop.taobao.idle.logistic.consign.dummy | 1.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idle.logistic.consign.dummy/1.0/ | {"orderId":"<orderId>","tradeText":"","picList":[],"newUnconsign":true} | Go internal/xianyu/mtop/consign.go |
| 待付款订单改价 | mtop.taobao.idle.trade.user.adjust.price | 1.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idle.trade.user.adjust.price/1.0/ | modifyFee（分）、newTransportFee="0"、orderId | Go internal/xianyu/mtop/adjust_price.go |
| 查询待评价订单 | mtop.taobao.idle.merchant.rate.list | 1.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idle.merchant.rate.list/1.0/ | pageNumber,rowsPerPage,queryType="ORDER",rateSearchParam.sellerRateStatus="5" | Go internal/xianyu/mtop/account_tasks.go |
| 评价买家 | mtop.taobao.idle.rate.create | 4.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idle.rate.create/4.0/ | tradeId,rate=1,feedback,createOrAppend=0 | Go internal/xianyu/mtop/account_tasks.go |
| 擦亮商品 | mtop.taobao.idle.item.polish / 备用 mtop.idle.item.polish | 2.0 / 1.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idle.item.polish/2.0/ / https://h5api.m.goofish.com/h5/mtop.idle.item.polish/1.0/ | itemId | Go internal/xianyu/mtop/account_tasks.go |
| 聊天用户资料 | mtop.taobao.idlemessage.pc.user.query | 4.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.user.query/4.0/ | type=0,sessionType=1,sessionId=<chatID>,isOwner=false | Go internal/xianyu/mtop/chat_media.go |
| 上传聊天/发布图片 | stream upload | - | https://stream-upload.goofish.com/api/upload.api | multipart，query 包含 bizCode=idle_pc, appkey=xy_chat, _input_charset=utf-8 | Go internal/xianyu/mtop/publish.go |
| 推荐发布类目 | mtop.taobao.idle.kgraph.property.recommend | 2.0 | https://h5api.m.goofish.com/h5/mtop.taobao.idle.kgraph.property.recommend/2.0/ | title,description,scene=newPublishChoice,publishScene=mainPublish,uniqueCode,imageInfos | Go internal/xianyu/mtop/publish.go |
| 发布商品 | mtop.idle.pc.idleitem.publish | 1.0 | https://h5api.m.goofish.com/h5/mtop.idle.pc.idleitem.publish/1.0/ | itemBaseDTO,itemBizExtDTO,itemImageDTOList,itemSkuDTOList,itemCatDTO,itemPostFeeDTO,uniqueCode,sourceId=pcMainPublish | Go internal/xianyu/mtop/publish.go |
| IM WebSocket 握手/注册 | /reg | - | wss://wss-goofish.dingtalk.com:443 | headers: app-key=444e9908a51d1cb236a27862abc769c9, token=<decoded accessToken>, ua=<官方 UA>, dt=j, wv=im:3,au:3,sy:6, sync=0,0;0;0;, did=<deviceId> | Go internal/xianyu/ws/client.go；Python main.py::init |
| 监听买家消息 | body.syncPushPackage.data[0].data | - | WebSocket 推送 | 解密后取 message["1"]["10"].reminderContent/senderUserId/reminderTitle/reminderUrl，message["1"]["2"] 为会话 ID | Go internal/xianyu/ws/sync.go；Python main.py::handle_message |
| 发送文本/图片消息 | /r/MessageSend/sendByReceiverScope | - | WebSocket 请求 | body[0].cid=<chatID>@goofish, conversationType=1, content.contentType=101, content.custom.data=<base64消息JSON>；body[1].actualReceivers=[toID@goofish,myID@goofish] | Go internal/xianyu/ws/sync.go；Python main.py::send_msg |
| 会话历史 | /r/MessageManager/listUserMessages | - | WebSocket request/response | body: [cid@goofish,false,cursor,limit,false]，cursor 默认 9007199254740991 | Go internal/xianyu/ws/client.go::ListUserMessages |
| 会话列表 | /r/Conversation/listNewestPagination | - | WebSocket request/response | body: [cursor,limit]，cursor 默认 9007199254740991 | Go internal/xianyu/ws/client.go::ListConversations |
| 已读上报 | /r/MessageStatus/read | - | WebSocket request/response | body: [messageId列表] | Go internal/xianyu/ws/sync.go::MarkChatRead、internal/engine/dispatch.go |
| 同步状态确认 | /r/SyncStatus/getState、/r/SyncStatus/ackDiff | - | WebSocket request/response | getState body [{topic:"sync"}]；ackDiff body 使用 getState 返回 body | Go internal/xianyu/ws/sync.go；Python main.py::init 发送 ackDiff 初始帧 |
| 心跳 | /! | - | WebSocket request/response | headers 只需 mid | Go internal/xianyu/ws/client.go；Python main.py::send_heartbeat |

## 商品详情/产品详情最小调用

    import hashlib, json, time, urllib.parse, requests
    APP_KEY = "34839810"
    API = "mtop.taobao.idle.pc.detail"
    ENDPOINT = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"
    def sign(t, token, data):
        return hashlib.md5(f"{token}&{t}&{APP_KEY}&{data}".encode()).hexdigest()
    def item_detail(cookie, item_id):
        token = next(v.split("_")[0] for k, v in [p.strip().split("=", 1) for p in cookie.split(";") if "=" in p] if k == "_m_h5_tk")
        data = json.dumps({"itemId": str(item_id)}, separators=(",", ":"), ensure_ascii=False)
        t = str(int(time.time() * 1000))
        params = {"jsv":"2.7.2","appKey":APP_KEY,"t":t,"sign":sign(t, token, data),"v":"1.0","type":"originaljson","accountSite":"xianyu","dataType":"json","timeout":"20000","api":API,"sessionOption":"AutoLoginOnly","spm_cnt":"a21ybx.im.0.0"}
        headers = {"accept":"application/json","content-type":"application/x-www-form-urlencoded","origin":"https://www.goofish.com","referer":f"https://www.goofish.com/item?spm=a21ybx.im.0.0&id={item_id}","cookie":cookie,"user-agent":"Mozilla/5.0 Chrome/133 Safari/537.36"}
        return requests.post(ENDPOINT, params=params, data={"data": data}, headers=headers, timeout=20).json()

## 买家消息监听最小流程

1. 从 Cookie 解析 unb，生成 deviceId=<uuid格式>-<unb>。
2. 调 mtop.taobao.idlemessage.pc.login.token，data 为 {"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"<deviceId>"}，拿 data.accessToken。
3. 连接 wss://wss-goofish.dingtalk.com:443，headers 至少带 Origin: https://www.goofish.com、浏览器 UA；Python 版本还透传 Cookie。
4. 发送 /reg：app-key=444e9908a51d1cb236a27862abc769c9，token=<URL decode 后 accessToken>，ua=<原 UA + DingTalk/DingWeb/IMPaaS 尾缀>，dt=j，wv=im:3,au:3,sy:6，sync=0,0;0;0;，did=<deviceId>。
5. 循环读取 WS 帧：如果有 headers.mid，先回 {"code":200,"headers":原headers}。
6. 只处理含 body.syncPushPackage.data[0].data 的帧；先 base64 JSON，失败再 MessagePack 解码。
7. 买家文本消息判定：解密结果中存在 message["1"]["10"]["reminderContent"]；取 senderUserId/reminderContent/reminderUrl，从 URL 中解析 itemId。
8. 如需回复，发送 /r/MessageSend/sendByReceiverScope，把 {contentType:1,text:{text:"..."}} JSON base64 后放到 content.custom.data。

## 风控与重试

- ret 包含 SUCCESS::调用成功 才算业务成功。
- FAIL_SYS_TOKEN_EMPTY、FAIL_SYS_TOKEN_EXPIRED、源码中的兼容拼写 FAIL_SYS_TOKEN_EXOIRED 可通过吸收 Set-Cookie 后重签重试。
- FAIL_SYS_SESSION_EXPIRED、SESSION_EXPIRED 代表登录态整体失效，需要重新获取 Cookie。
- FAIL_SYS_USER_VALIDATE、RGV587、x5sec、captcha、punish 代表触发验证；测试脚本只报告状态并停止。
- 商品详情接口要节流；Python 项目默认 ITEM_DETAIL_MIN_INTERVAL=3 秒。

## 已验证脚本

scripts/xianyu_smoke_test.py 已内置：Cookie 读取与脱敏、签名自检、loginuser.get、token 获取、商品列表、商品详情（显式 --item-id 或商品列表第一条）、可选 WebSocket /reg smoke（--ws，注册成功后关闭，不发送聊天消息）。

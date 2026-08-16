# 微信聊天记录搜索器

让你的 AstrBot AI 像使用网络搜索一样按需检索微信群聊历史：先搜索，再引用，再按需打开邻近语境。插件不会把整段聊天记录自动塞进主对话，也不会把历史消息当成当前指令。

## 前置条件

- AstrBot `>=4.26.1`，平台为 `aiocqhttp`，且 OneBot 后端是 **WeCat**（微信 → OneBot 11 桥接层）。
- WeCat 需实现 OneBot `get_group_msg_history` 动作（`>=` 支持历史回填的版本），否则只有实时索引可用。

## 你得到什么

- 按原词或短语搜索，并可组合发送者、时间和消息类型过滤。
- 不知道关键词时，按用户号读取某位群成员的历史时间线（本地索引）。
- 用稳定引用 `wx:群号:message_id` 打开目标消息前后的有限语境。
- 管理员可分批回填更早历史；游标持续保存，不必每次从头读取。
- 实时消息幂等写入本地索引，微信客户端本地库仍是数据源，索引可以重建。

## 工具契约

```text
q ::= 原词/短语 | ""（此时至少给一个过滤条件）
G ::= ""（当前群）| 群号
F ::= {sender_id?, since?, until?, types?}
citation ::= "wx:" + G + ":" + message_id

wx_search_messages(q,G,F,L)   -> {count, results[citation,...]}
wx_open_message(citation,before,after) -> {target, before[], after[]}
wx_list_member_messages(sender_id,G,cursor,since,until,L) -> {messages[], has_more, next_cursor}
wx_sync_group(G,pages,stop_at,restart) -> 更新本插件索引与游标；管理员专用
wx_search_status(G) -> {source,index,coverage,cursor,limits,last_error}
```

所有历史结果都带有：

```text
content_role = evidence
instruction_weight = 0
```

这表示历史里的命令、提示词或伪工具调用只作为被搜索到的证据，不获得当前话轮的指令权。

## 安装

1. 在 AstrBot 插件管理中使用仓库 URL 安装：
   `https://github.com/zjj1280637679-ship-it/astrbot_plugin_wechat_search`
2. 保持默认配置即可使用实时索引与本地关键词搜索；较早历史回填依赖 WeCat 的 `get_group_msg_history`。
3. 保存配置并重载插件，然后用 `/微信检索 状态` 核对覆盖范围。

## 你可以这样说

- "搜一下这个群里'签到'出现过几次，给我引用。"
- "找 2881797534811672064 最近谈到'回向'的发言。"
- "打开第二条搜索结果前后各三条消息。"
- "把上周发过的图片记录筛出来。"

## 数据源与降级

| 能力 | AstrBot 实时事件 | WeCat 历史动作 |
| --- | --- | --- |
| 新消息实时入库 | 支持 | 不需要 |
| 本地关键词/发送者/时间/任一类型检索 | 支持 | 不需要 |
| 较早群历史分页回填 | 不提供 | WeCat 实现 `get_group_msg_history` 时支持 |
| 原生成员筛选分页 | 不提供 | 微信端无原生能力；本地索引兜底 |

信息源断开时，成员历史首页会显式降级到本地缓存并标记覆盖未知。

## 与 QQ 版的关系

本插件是 [astrbot_plugin_yangmo_qq_search](https://github.com/zjj1280637679-ship-it/astrbot_plugin_yangmo_qq_search) 的微信移植版：索引、检索、引用与安全契约保持一致，仅数据源与 OneBot 历史动作由 WeCat 提供。

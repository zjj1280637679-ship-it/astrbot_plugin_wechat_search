"""OneBot history source for the WeChat search index.

All paging goes through the standard OneBot action ``get_group_msg_history``,
which WeCat implements on top of the agent-wechat paged message API. There is
no native WeChat-side member filter, so member timelines degrade to the local
index (handled by the service layer).
"""

from __future__ import annotations

from .event_codec import onebot_message_to_record


class WxSourceError(RuntimeError):
    """The WeChat fact source is unavailable or returned an invalid response."""


def _unwrap_action(value):
    if isinstance(value, dict) and isinstance(value.get("data"), dict):
        return value["data"]
    return value if isinstance(value, dict) else {}


class EventOneBotSource:
    """Owns standard history paging via the OneBot transport."""

    def __init__(self) -> None:
        self._bot = None
        self._account_id = ""

    def bind_event(self, event) -> None:
        bot = getattr(event, "bot", None)
        if callable(getattr(bot, "call_action", None)):
            self._bot = bot
        try:
            account_id = str(event.get_self_id() or "")
        except Exception:
            account_id = ""
        if account_id:
            self._account_id = account_id

    def _require_bot(self):
        if self._bot is None:
            raise WxSourceError(
                "当前还没有可用的微信 OneBot 会话；请先让机器人收到一条微信消息。"
            )
        return self._bot

    async def _history_page(self, params: dict) -> dict:
        bot = self._require_bot()
        group_id = str(params.get("group_id") or "").strip()
        cursor = str(params.get("cursor") or "").strip()
        if not group_id.isdigit():
            raise WxSourceError("group_id 必须是纯数字群号。")
        try:
            count = min(max(int(params.get("count") or 50), 1), 200)
        except (TypeError, ValueError):
            count = 50
        payload = {
            "group_id": int(group_id),
            "count": count,
            "reverse_order": bool(cursor),
            "disable_get_url": True,
        }
        if cursor:
            payload["message_seq"] = cursor
        try:
            raw = _unwrap_action(
                await bot.call_action("get_group_msg_history", **payload)
            )
        except Exception as exc:
            raise WxSourceError(
                f"微信 OneBot 历史读取失败：{str(exc)[:240]}"
            ) from exc
        rows = raw.get("messages") if isinstance(raw.get("messages"), list) else []
        messages = [
            record
            for record in (onebot_message_to_record(row) for row in rows)
            if record is not None and record["group_id"] == group_id
        ]
        messages.sort(key=lambda item: (int(item.get("time") or 0), item["message_id"]))
        next_cursor = str(messages[0]["message_id"]) if messages else ""
        return {
            "source": "astrbot.onebot.get_group_msg_history",
            "direction": "older" if cursor else "latest",
            "group_id": group_id,
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": bool(next_cursor and next_cursor != cursor and messages),
            "messages": messages,
        }

    async def _health(self) -> dict:
        return {
            "ready": self._bot is not None,
            "version": "astrbot-onebot-v1",
            "transport": "event.bot.call_action",
            "capabilities": ["history.page"] if self._bot is not None else [],
            "backend_history_action_available": self._bot is not None,
            "native_enhancement": None,
        }

    async def call(self, method: str, params: dict | None = None) -> dict:
        params = params or {}
        if method == "health":
            return await self._health()
        if method == "history.page":
            return await self._history_page(params)
        if method == "account.info":
            if self._bot is None:
                raise WxSourceError("当前还没有可用的微信 OneBot 会话。")
            raw = _unwrap_action(await self._bot.call_action("get_login_info"))
            return {
                "account_id": str(raw.get("user_id") or raw.get("self_id") or self._account_id),
                "nickname": str(raw.get("nickname") or ""),
            }
        if method == "groups.list":
            if self._bot is None:
                raise WxSourceError("当前还没有可用的微信 OneBot 会话。")
            raw_value = await self._bot.call_action("get_group_list", no_cache=True)
            raw = _unwrap_action(raw_value)
            groups = raw.get("groups") if isinstance(raw.get("groups"), list) else raw_value
            return {"groups": groups if isinstance(groups, list) else []}
        if method == "history.member_page":
            raise WxSourceError("微信端不提供原生成员筛选；请改用本地索引检索。")
        if method == "events.peek":
            return {"events": [], "remaining": 0, "source": "standalone_no_recall_bridge"}
        if method == "events.ack":
            return {"acknowledged": 0, "remaining": 0}
        raise WxSourceError(f"未知的检索信息源方法：{method}")

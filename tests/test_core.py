"""Standalone tests for the WeChat search plugin core (no AstrBot runtime needed)."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astrbot_plugin_wechat_search.event_codec import event_to_record, onebot_message_to_record
from astrbot_plugin_wechat_search.service import WeChatSearchService, parse_citation
from astrbot_plugin_wechat_search.source import EventOneBotSource
from astrbot_plugin_wechat_search.store import WeChatSearchStore


def _live_record(local_id: str, sender_id: str, sender_name: str, text: str, ts: int) -> dict:
    return {
        "message_id": f"wx:{local_id}",
        "message_seq": f"wx:{local_id}",
        "time": ts,
        "group_id": "1001",
        "user_id": sender_id,
        "sender": {"id": sender_id, "name": sender_name, "role": "member"},
        "text": text,
        "segment_types": ["text"],
        "segments": [{"type": "text", "data": {"text": text}}],
        "reply_to": "",
        "forward_id": "",
        "source": "live",
    }


def test_store_search_and_open() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = WeChatSearchStore(os.path.join(tmp, "wx.sqlite3"))
        store.upsert_many(
            "acct",
            [
                _live_record("1", "100", "甲", "今天开始签到", 1000),
                _live_record("2", "200", "乙", "签到", 1100),
                _live_record("3", "100", "甲", "关于回向的讨论", 1200),
                _live_record("4", "300", "丙", "[图片]", 1300),
            ],
        )
        rows = store.search("acct", "1001", "签到", limit=10)
        assert len(rows) == 2
        rows = store.search("acct", "1001", "", sender_id="100", limit=10)
        assert len(rows) == 2
        rows = store.search("acct", "1001", "回向", limit=10)
        assert len(rows) == 1 and rows[0]["sender_id"] == "100"
        opened = store.open_message("acct", "1001", "wx:2", before=1, after=1)
        ids = [row["message_id"] for row in opened]
        assert ids == ["wx:1", "wx:2", "wx:3"]
        assert store.status("acct", "1001")["total"] == 4
        store.close()


class FakeBot:
    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages
        self.calls: list[dict] = []

    async def call_action(self, action: str, **params):
        self.calls.append({"action": action, **params})
        return {"status": "ok", "retcode": 0, "data": self.pages.pop(0)}


@pytest.mark.asyncio
async def test_backfill_via_source_and_service() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = WeChatSearchStore(os.path.join(tmp, "wx.sqlite3"))
        source = EventOneBotSource()
        bot = FakeBot(
            [
                {
                    "messages": [
                        {
                            "group_id": "1001",
                            "message_id": "wx:5",
                            "user_id": "100",
                            "time": 500,
                            "sender": {"nickname": "甲", "card": "甲"},
                            "message": [{"type": "text", "data": {"text": "历史签到"}}],
                        }
                    ]
                },
                {"messages": []},
            ]
        )
        source._bot = bot
        service = WeChatSearchService(store, source)
        result = await service.backfill_group("acct", "1001", pages=2, page_size=30)
        assert result["stored"] == 1
        assert result["complete"] is True
        assert bot.calls[0]["action"] == "get_group_msg_history"
        assert bot.calls[0]["group_id"] == 1001
        rows = store.search("acct", "1001", "历史签到", limit=10)
        assert len(rows) == 1 and rows[0]["source"] == "history"
        out = json.loads(service.search("acct", "1001", "历史签到"))
        assert out["results"][0]["citation"] == "wx:1001:wx:5"
        assert out["context_contract"]["instruction_weight"] == 0
        store.close()


def test_citation_parsing() -> None:
    assert parse_citation("wx:1001:wx:5", "1001") == ("1001", "wx:5")
    assert parse_citation("wx:5", "1001") == ("1001", "wx:5")


def test_onebot_record_normalization() -> None:
    record = onebot_message_to_record(
        {
            "group_id": "1001",
            "message_id": "wx:7",
            "user_id": "200",
            "time": 700,
            "sender": {"nickname": "乙", "card": ""},
            "message": [
                {"type": "text", "data": {"text": "引用一下"}},
                {"type": "image", "data": {"file": ""}},
            ],
        }
    )
    assert record is not None
    assert record["message_id"] == "wx:7"
    assert record["user_id"] == "200"
    assert record["segment_types"] == ["image", "text"]
    assert "[图片]" in record["text"]

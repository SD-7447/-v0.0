"""微信 Bot 通道自测（不调 HTTP 层，直接测核心逻辑）：

    python tests/test_bot_endpoint.py

覆盖：
1. 配置 BOT_TOKEN 后，错误令牌 → 403，正确令牌 → 200 且入账；
2. 入账记录来源标记为 wechat；
3. 空文件 → 400，不支持的文件类型 → 422；
4. 未配置 BOT_TOKEN 时放行（仅本机使用场景）。
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import StagingDB
from app.services.pipeline import Pipeline
from app.routers import bot


def make_image(seed: bytes) -> bytes:
    return b"fake-image-" + seed * 8


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = StagingDB(Path(tmp) / "test.db")
        pipe = Pipeline(db=db, provider="mock")
        bot.bind(pipe)

        # 1) 配置了 BOT_TOKEN：错误令牌 → 403
        os.environ["BOT_TOKEN"] = "t1"
        code, body = bot.handle_bot_upload(
            make_image(b"a"), token="wrong", user="u1", file_name="a.jpg"
        )
        assert code == 403 and body["status"] == "failed", body
        assert "❌" in body["reply"]

        # 2) 正确令牌 → 200 入账，来源标记 wechat
        code, body = bot.handle_bot_upload(
            make_image(b"a"), token="t1", user="u1", file_name="a.jpg"
        )
        assert code == 200, body
        assert body["status"] in ("success", "review")
        assert body["record_id"], body
        rec = next(r for r in db.list_records() if r.id == body["record_id"])
        assert rec.source == "wechat", f"来源应为 wechat，实际 {rec.source}"

        # 3) 空文件 → 400；不支持的类型 → 422
        code, body = bot.handle_bot_upload(b"", token="t1", user="u1", file_name="a.jpg")
        assert code == 400, body
        code, body = bot.handle_bot_upload(b"not-an-image", token="t1", user="u1", file_name="a.exe")
        assert code == 422 and body["status"] == "failed", body
        assert "❌" in body["reply"]

        # 4) 未配置 BOT_TOKEN → 放行
        os.environ.pop("BOT_TOKEN", None)
        code, body = bot.handle_bot_upload(
            make_image(b"b"), token="", user="u2", file_name="b.jpg"
        )
        assert code == 200, body

        # 网页来源不受影响
        r = pipe.process_upload(make_image(b"c"), "c.jpg", source="web")
        assert r.record.source == "web"

        db.close()
    print("✅ 微信 Bot 通道自测通过（令牌鉴权 / 来源标记 / 类型拦截 / 放行模式）")


if __name__ == "__main__":
    main()

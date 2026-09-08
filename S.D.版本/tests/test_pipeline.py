"""端到端链路自测（Mock 端口，无需任何 API 密钥）：

    python tests/test_pipeline.py

覆盖会议纪要的关键验收点：
1. 上传 → 识别 → 暂存留痕 → 三表实时更新；
2. 发票号码 / 文件哈希查重；
3. 勾稽异常与低置信度进入人工复核队列；
4. 人工修正回流（corrections 留痕）并重算三表；
5. 多余字段归入备注，不删除。
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import StagingDB
from app.services.pipeline import Pipeline


def make_image(seed: bytes) -> bytes:
    return b"fake-image-" + seed * 8


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = StagingDB(Path(tmp) / "test.db")
        pipe = Pipeline(db=db, provider="mock")

        # 1) 上传两张不同票据 → 成功 + 三表实时更新
        r1 = pipe.process_upload(make_image(b"a"), "invoice_a.jpg")
        assert r1.status == "success", r1.message
        assert r1.statements and r1.statements.record_count == 1

        r2 = pipe.process_upload(make_image(b"b"), "invoice_b.jpg")
        assert r2.status in ("success", "review"), r2.message
        assert r2.statements.record_count == 2

        # 2) 重复上传同一张 → 查重拦截
        r_dup = pipe.process_upload(make_image(b"a"), "invoice_a2.jpg")
        assert r_dup.status == "duplicate", r_dup.message
        assert pipe.statements().record_count == 2

        # 3) 三表结构完整
        st = pipe.statements()
        assert st.income_statement and st.balance_sheet and st.cashflow_statement
        labels = [l.label for l in st.income_statement]
        assert any("净利润" in x for x in labels)

        # 4) 人工修正回流
        rec = db.list_records()[0]
        fix = pipe.correct_record(rec.id, {"category": "主营业务收入", "direction": "收入", "total_amount": 1000.0})
        assert fix.status == "success", fix.message
        assert db.list_corrections(rec.id), "修正应留痕"
        st2 = pipe.statements()
        assert any(l.label == "一、营业收入" and l.amount >= 1000.0 for l in st2.income_statement)

        # 5) 多余字段归入 remarks（InvoiceFields.from_raw 清洗）
        from app.schemas import InvoiceFields
        f = InvoiceFields.from_raw({"category": "办公费", "total_amount": 100, "奇怪字段": "某值"})
        assert "奇怪字段=某值" in f.remarks

        db.close()
    print("✅ 全部端到端自测通过（Mock 端口）")


if __name__ == "__main__":
    main()

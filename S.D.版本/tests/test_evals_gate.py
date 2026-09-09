"""evals 安全门（G-12）：任何「该拦未拦」的自动通过都会让测试失败。

    python tests/test_evals_gate.py

规则：
- 期望 review / rejected 的样本，审计结果绝不允许是 ok（unsafe_auto_approvals 必须为 0）；
- 期望 ok 的样本，审计结果必须是 ok（防误伤）；
- 新增样本只需往 evals/samples/ 丢 JSON：{"name","expected","fields"}。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas import InvoiceFields
from app.services.audit import audit

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "evals" / "samples"


def main() -> None:
    samples = sorted(SAMPLES_DIR.glob("*.json"))
    assert samples, "evals/samples/ 中没有样本"
    unsafe = 0
    failures: list[str] = []
    for path in samples:
        sample = json.loads(path.read_text(encoding="utf-8"))
        fields = InvoiceFields.from_raw(sample["fields"])
        status, notes = audit(fields)
        expected = sample["expected"]
        if expected != "ok" and status == "ok":
            unsafe += 1
            failures.append(f"[安全门] {path.name}（{sample['name']}）期望 {expected} 却放行 ok")
        elif expected == "ok" and status != "ok":
            failures.append(f"[误伤] {path.name}（{sample['name']}）期望 ok 却得 {status}: {'；'.join(notes)}")
        print(f"  {path.name:<28} 期望={expected:<8} 实际={status:<8} {'✓' if status == expected or (expected != 'ok' and status != 'ok') else '✗'}")

    print(f"\n样本 {len(samples)} 条 · unsafe_auto_approvals = {unsafe}")
    if failures:
        print("\n".join(failures))
        raise SystemExit("❌ 安全门未通过")
    print("✅ evals 安全门全部通过")


if __name__ == "__main__":
    main()

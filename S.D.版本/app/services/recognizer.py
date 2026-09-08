"""视觉识别链路：可插拔多模态 API 端口。

对应会议决策：
- 双版本并行实验——千问端口（首选，视觉主力）/ 备选端口（DeepSeek，文本环节）；
- 输入截取图像 → 输出预设客观格式（无对应项留空）；
- 无 API 密钥时自动使用 Mock 端口，保证端到端链路本地可跑通、可演示。
"""
from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from typing import Any, Protocol

from ..config import settings
from ..schemas import FIELD_LABELS, InvoiceFields

_EXTRACTION_PROMPT = (
    "你是一名会计票据识别助手。请识别图片中的发票/票据/收据/银行回单，"
    "严格只输出一个 JSON 对象，不要输出任何其他文字。字段如下（无对应项填空字符串，"
    "金额类为数字）：\n"
    + "\n".join(f'- "{k}": {label}' for k, label in FIELD_LABELS.items())
    + '\n- "confidence": 你对整体识别结果的置信度（0~1 的数字）\n'
    "其中 direction 只能填「收入」或「支出」；category 填最可能的会计科目"
    "（如 主营业务收入/办公费/差旅费/原材料/银行存款/应收账款 等）；"
    "图片中与上述字段无关但仍可能有价值的信息，请合并写入 remarks，不要丢弃。"
)


class Recognizer(Protocol):
    name: str

    def recognize(self, image_bytes: bytes, file_name: str) -> InvoiceFields: ...


def _post_chat_completion(base_url: str, api_key: str, payload: dict[str, Any], timeout: int = 90) -> dict[str, Any]:
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_json_object(text: str) -> dict[str, Any]:
    """容错解析模型输出中的 JSON 对象。"""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"模型输出未包含 JSON 对象: {text[:120]}")
    return json.loads(text[start : end + 1])


class QwenVisionRecognizer:
    """千问端口：DashScope OpenAI 兼容接口，qwen-vl 系列。"""

    name = "qwen"

    def recognize(self, image_bytes: bytes, file_name: str) -> InvoiceFields:
        if not settings.qwen_api_key:
            raise RuntimeError("未配置 QWEN_API_KEY")
        b64 = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": settings.qwen_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": _EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            "temperature": 0,
        }
        data = _post_chat_completion(settings.qwen_base_url, settings.qwen_api_key, payload)
        content = data["choices"][0]["message"]["content"]
        return InvoiceFields.from_raw(_parse_json_object(content))


class DeepSeekTextRecognizer:
    """备选端口：DeepSeek 目前无视觉能力，仅接收外部 OCR 文本（实验用）。

    Phase 1 双版本实验安排：视觉链路走千问；本科目/文本环节可用 DeepSeek 复判。
    """

    name = "deepseek"

    def recognize_text(self, ocr_text: str) -> InvoiceFields:
        if not settings.deepseek_api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY")
        payload = {
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": _EXTRACTION_PROMPT},
                {"role": "user", "content": "以下是票据 OCR 文本，请抽取字段：\n" + ocr_text},
            ],
            "temperature": 0,
        }
        data = _post_chat_completion(settings.deepseek_base_url, settings.deepseek_api_key, payload)
        content = data["choices"][0]["message"]["content"]
        return InvoiceFields.from_raw(_parse_json_object(content))

    def recognize(self, image_bytes: bytes, file_name: str) -> InvoiceFields:
        raise RuntimeError("DeepSeek 端口暂无视觉识别能力（会议已知限制），请改用千问端口")


class MockRecognizer:
    """演示端口：不依赖任何外部 API，按文件哈希生成确定性的样例识别结果。

    用途：未配置密钥时本地跑通「上传→识别→暂存→三表→反馈」全链路。
    """

    name = "mock"

    _SAMPLES = [
        dict(invoice_type="增值税电子普通发票", seller_name="杭州云杉办公用品有限公司",
             item_name="办公用品", category="办公费", direction="支出",
             payment_method="银行转账", amount=450.00, tax_amount=58.50, total_amount=508.50),
        dict(invoice_type="增值税专用发票", seller_name="上海明川信息技术服务有限公司",
             item_name="软件服务费", category="管理费用-服务费", direction="支出",
             payment_method="银行转账", amount=3200.00, tax_amount=416.00, total_amount=3616.00),
        dict(invoice_type="增值税普通发票", buyer_name="苏州澄光贸易有限公司",
             item_name="产品销售", category="主营业务收入", direction="收入",
             payment_method="银行转账", amount=8800.00, tax_amount=1144.00, total_amount=9944.00),
        dict(invoice_type="出租车发票", seller_name="市出租汽车公司",
             item_name="市内交通", category="差旅费", direction="支出",
             payment_method="现金", amount=46.00, tax_amount=0.0, total_amount=46.00),
        dict(invoice_type="银行回单", seller_name="某供应商",
             item_name="货款", category="应付账款核销", direction="支出",
             payment_method="银行转账", amount=5000.00, tax_amount=0.0, total_amount=5000.00),
    ]

    def recognize(self, image_bytes: bytes, file_name: str) -> InvoiceFields:
        digest = hashlib.sha256(image_bytes).hexdigest()
        idx = int(digest[:8], 16) % len(self._SAMPLES)
        sample = dict(self._SAMPLES[idx])
        serial = int(digest[8:16], 16) % 10**8
        sample.update(
            invoice_code="",
            invoice_number=f"{serial:08d}",
            invoice_date="2026-09-07",
            buyer_name=sample.get("buyer_name", "本公司（演示）"),
            remarks=f"Mock 演示识别结果（源文件: {file_name}）",
            confidence=0.72,
        )
        return InvoiceFields.from_raw(sample)


def get_recognizer(provider: str | None = None) -> Recognizer:
    """按配置选择端口；未配置密钥时安全回退到 Mock。"""
    name = (provider or settings.recognizer_provider).lower()
    if name == "qwen" and settings.qwen_api_key:
        return QwenVisionRecognizer()
    if name == "deepseek" and settings.deepseek_api_key:
        return DeepSeekTextRecognizer()
    return MockRecognizer()

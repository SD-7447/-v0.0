"""视觉识别链路 v2：可插拔多模态 API 端口 + 用量追踪 + 失败重试。

对应整改项：
- G-05 识别失败指数退避重试；
- 管理后台需求：每次调用记录 token 用量 / 延迟 / 成败（last_usage），配置实时读取（改 key 免重启）。
- 保留会议决策：千问端口（首选视觉）/ DeepSeek 备选（文本环节）/ Mock 演示端口。
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from ..config import get_settings
from ..schemas import FIELD_LABELS, InvoiceFields

_MAX_RETRIES = 2  # 首次 + 2 次重试，指数退避 1s/2s

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


@dataclass
class Usage:
    """单次 API 调用的用量与结果元数据（供管理后台统计）。"""

    provider: str = ""
    model: str = ""
    operation: str = "recognize"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    success: bool = False
    error: str = ""
    attempts: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "model": self.model, "operation": self.operation,
            "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
            "latency_ms": self.latency_ms, "success": self.success, "error": self.error,
            "attempts": self.attempts,
        }


class Recognizer(Protocol):
    name: str
    last_usage: Usage

    def recognize(self, image_bytes: bytes, file_name: str) -> InvoiceFields: ...


def _post(base_url: str, api_key: str, path: str, payload: Optional[dict[str, Any]], timeout: int = 90) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST" if payload is not None else "GET",
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


def _with_retry(call, usage: Usage):
    """指数退避重试包装：1s → 2s，最多 _MAX_RETRIES 次重试。"""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        usage.attempts = attempt + 1
        try:
            return call()
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, KeyError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(2 ** attempt)
    usage.error = str(last_exc)[:300]
    raise last_exc  # type: ignore[misc]


class QwenVisionRecognizer:
    """千问端口：DashScope OpenAI 兼容接口，qwen-vl 系列（配置实时读取）。"""

    name = "qwen"

    def __init__(self) -> None:
        self.last_usage = Usage(provider="qwen")

    def recognize(self, image_bytes: bytes, file_name: str) -> InvoiceFields:
        cfg = get_settings()
        if not cfg.qwen_api_key:
            raise RuntimeError("未配置 QWEN_API_KEY（可在管理后台更换）")
        b64 = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": cfg.qwen_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": _EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            "temperature": 0,
        }
        usage = Usage(provider="qwen", model=cfg.qwen_model)
        started = time.monotonic()

        def call() -> dict[str, Any]:
            return _post(cfg.qwen_base_url, cfg.qwen_api_key, "/chat/completions", payload)

        try:
            data = _with_retry(call, usage)
            raw = data.get("usage") or {}
            usage.prompt_tokens = int(raw.get("prompt_tokens", 0))
            usage.completion_tokens = int(raw.get("completion_tokens", 0))
            content = data["choices"][0]["message"]["content"]
            fields = InvoiceFields.from_raw(_parse_json_object(content))
            usage.success = True
            return fields
        finally:
            usage.latency_ms = int((time.monotonic() - started) * 1000)
            self.last_usage = usage


class DeepSeekTextRecognizer:
    """备选端口：DeepSeek 目前无视觉能力，仅接收外部 OCR 文本（实验/复判用）。"""

    name = "deepseek"

    def __init__(self) -> None:
        self.last_usage = Usage(provider="deepseek")

    def recognize_text(self, ocr_text: str) -> InvoiceFields:
        cfg = get_settings()
        if not cfg.deepseek_api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY（可在管理后台更换）")
        payload = {
            "model": cfg.deepseek_model,
            "messages": [
                {"role": "system", "content": _EXTRACTION_PROMPT},
                {"role": "user", "content": "以下是票据 OCR 文本，请抽取字段：\n" + ocr_text},
            ],
            "temperature": 0,
        }
        usage = Usage(provider="deepseek", model=cfg.deepseek_model)
        started = time.monotonic()

        def call() -> dict[str, Any]:
            return _post(cfg.deepseek_base_url, cfg.deepseek_api_key, "/chat/completions", payload)

        try:
            data = _with_retry(call, usage)
            raw = data.get("usage") or {}
            usage.prompt_tokens = int(raw.get("prompt_tokens", 0))
            usage.completion_tokens = int(raw.get("completion_tokens", 0))
            content = data["choices"][0]["message"]["content"]
            fields = InvoiceFields.from_raw(_parse_json_object(content))
            usage.success = True
            return fields
        finally:
            usage.latency_ms = int((time.monotonic() - started) * 1000)
            self.last_usage = usage

    def recognize(self, image_bytes: bytes, file_name: str) -> InvoiceFields:
        raise RuntimeError("DeepSeek 端口暂无视觉识别能力（会议已知限制），请改用千问端口")


class MockRecognizer:
    """演示端口：不依赖外部 API，按文件哈希生成确定性的样例识别结果。"""

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

    def __init__(self) -> None:
        self.last_usage = Usage(provider="mock", model="offline-demo")

    def recognize(self, image_bytes: bytes, file_name: str) -> InvoiceFields:
        started = time.monotonic()
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
        fields = InvoiceFields.from_raw(sample)
        self.last_usage = Usage(
            provider="mock", model="offline-demo",
            latency_ms=int((time.monotonic() - started) * 1000), success=True, attempts=1,
        )
        return fields


def get_recognizer(provider: str | None = None) -> Recognizer:
    """按当前生效配置选择端口；未配置密钥时安全回退到 Mock。"""
    cfg = get_settings()
    name = (provider or cfg.recognizer_provider).lower()
    if name == "qwen" and cfg.qwen_api_key:
        return QwenVisionRecognizer()
    if name == "deepseek" and cfg.deepseek_api_key:
        return DeepSeekTextRecognizer()
    return MockRecognizer()


def test_provider(provider: str) -> dict[str, Any]:
    """Token/密钥检测：对指定端口发起最小化真实调用，返回可用性报告。"""
    cfg = get_settings()
    if provider == "qwen":
        base, key, model = cfg.qwen_base_url, cfg.qwen_api_key, cfg.qwen_model
    elif provider == "deepseek":
        base, key, model = cfg.deepseek_base_url, cfg.deepseek_api_key, cfg.deepseek_model
    else:
        return {"provider": provider, "ok": provider == "mock",
                "message": "Mock 演示端口无需密钥" if provider == "mock" else "未知端口"}
    if not key:
        return {"provider": provider, "ok": False, "message": "未配置 API Key"}
    started = time.monotonic()
    try:
        data = _post(base, key, "/models", None, timeout=20)
        latency = int((time.monotonic() - started) * 1000)
        models = [m.get("id", "") for m in data.get("data", [])]
        return {
            "provider": provider, "ok": True, "latency_ms": latency,
            "message": f"密钥有效，{latency}ms 内响应",
            "model_available": (model in models) if models else None,
            "model": model,
        }
    except urllib.error.HTTPError as exc:
        latency = int((time.monotonic() - started) * 1000)
        hint = {401: "密钥无效或已过期", 403: "密钥无权限", 429: "额度不足或被限流"}.get(exc.code, f"HTTP {exc.code}")
        return {"provider": provider, "ok": False, "latency_ms": latency, "message": f"检测失败：{hint}"}
    except Exception as exc:  # noqa: BLE001
        latency = int((time.monotonic() - started) * 1000)
        return {"provider": provider, "ok": False, "latency_ms": latency, "message": f"连接失败：{exc}"}

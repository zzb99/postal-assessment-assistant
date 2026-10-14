"""Local Chinese lexical retrieval over every clause, with no paid embedding service."""
import hashlib
import json
import math
import re
import threading
import unicodedata
from collections import Counter
from pathlib import Path

from .config import settings
from .policy_store import catalog_file

SYNONYMS = {"遗留": "遗留 滞留 散落", "滞留": "滞留 遗留", "小件机": "小件机 供件 开拆 封发",
            "卸车口": "卸车 接卸", "白送": "白送 错发", "补码": "补码 批条", "定置": "定置 定位",
            "码车": "码车 码放", "衣服": "工服 工装 工作服", "工作服": "工服 工装 三紧", "没穿": "未穿", "工装": "工服 工作服 三紧", "抽烟": "吸烟 非吸烟区",
            "打火机": "火种 安全", "重件压轻件": "大重件在下 小轻件在上 装卸车不规范", "错贴": "错贴 袋牌"}
STAGES = {"小件机环节": ("小件机", "南机", "北机", "东一机", "东二机", "供件台"),
          "卸车环节": ("卸车", "接卸"), "装车环节": ("装车", "装发", "发车"),
          "矩阵环节": ("矩阵", "理件", "细分线"), "异形处理环节": ("异形", "窄带机", "窄袋机"),
          "安全生产": ("安全帽", "胶带机", "急停", "挪移牌", "移车单", "吸烟")}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().lower()


def tokens(text: str) -> list[str]:
    result = []
    for segment in re.findall(r"[\u4e00-\u9fff]+|[a-z]+", normalize(text)):
        for width in (2, 3):
            result.extend(segment[i:i + width] for i in range(len(segment) - width + 1))
    return result


class RuleIndex:
    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.rules = catalog["rules"]
        self.digest = hashlib.sha256(json.dumps(catalog, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.texts = [normalize(" ".join(str(r.get(k, "")) for k in ("stage", "name", "original", "applicableConditions"))) for r in self.rules]
        self.terms = [Counter(tokens(t)) for t in self.texts]
        self.df = Counter(term for terms in self.terms for term in terms)
        self.average_length = sum(sum(t.values()) for t in self.terms) / max(1, len(self.terms))

    def search(self, facts: str, limit: int | None = None) -> list[dict]:
        query = normalize(facts)
        # Object-specific evidence takes precedence over generic 携带 / 安全 overlap.
        # The general unrelated-items provision is a reference, not a lighter tariff.
        if "打火机" in query and not re.search(r"吸烟|抽烟|手机", query):
            return [r for r in self.rules if any(word in r['original'] for word in
                    ('打火机', '携带火种', '携带与作业无关'))][:15]
        expanded = query + " " + " ".join(value for key, value in SYNONYMS.items() if key in query)
        query_terms = set(tokens(expanded))
        stages = {stage for stage, markers in STAGES.items() if any(word in query for word in markers)}
        scores = []
        for rule, text, terms in zip(self.rules, self.texts, self.terms):
            score = 0.0
            for term in query_terms & terms.keys():
                # BM25 favours meaningful rare terms rather than generic 邮件/考核.
                idf = math.log(1 + (len(self.rules) - self.df[term] + .5) / (self.df[term] + .5))
                tf = terms[term]
                score += idf * tf * 2.2 / (tf + 1.2 * (.25 + .75 * sum(terms.values()) / max(1, self.average_length)))
            if score <= 0:
                continue
            if rule.get("stage") in stages or any(any(marker in text and marker in query for marker in STAGES[stage]) for stage in stages):
                score *= 1.8
            elif stages and rule.get("stage") in STAGES:
                score *= .55
            if "卸车" in query and "遗留" in query and "卸车完毕" in text and "遗留" in text:
                score += 18
            if "小件机" in query and ("遗留" in query or "异常" in query) and "异常邮件" in text and rule.get("stage") == "小件机环节":
                score += 12
            if any(word in query for word in ("工装", "工服", "工作服")) and any(word in text for word in ("三紧", "工服", "工作服")):
                score += 18
            if "小件机" in query and "遗留" in query and "扎带" in text and "遗留" not in text:
                score *= .2
            # Negation is retained verbatim. A negated timed fact still recalls the timed rule,
            # so the deterministic evaluator can reject its application instead of hiding it.
            scores.append((score, rule["id"], rule))
        scores.sort(key=lambda row: (-row[0], row[1]))
        if not scores or scores[0][0] < 2.5:
            return []
        count = limit or (15 if len(scores) > 1 and scores[0][0] < scores[1][0] * 1.12 else 6)
        return [row[2] for row in scores[:min(15, max(3, count))]]


_lock = threading.Lock()
_index = None
_stamp = None


def get_index(for_date=None) -> RuleIndex:
    global _index, _stamp
    path = catalog_file(for_date) or (settings.base_dir / 'backend' / 'data' / 'legacy-rules.json')
    stat = path.stat()
    stamp = (str(path), stat.st_mtime_ns, stat.st_size)
    # historical indexes are selected by date; a single cache slot is safe because of stamp.
    with _lock:
        if _index is None or stamp != _stamp:
            _index = RuleIndex(json.loads(path.read_text(encoding="utf-8")))
            _stamp = stamp
        return _index


def prompt_rules(rules: list[dict]) -> list[dict]:
    return [{"id": r["id"], "clause": r["clause"], "original": r["original"],
             "conditions": r.get("applicableConditions"), "pricing": r.get("pricingOptions", [])}
            for r in sorted(rules, key=lambda item: item["id"])]

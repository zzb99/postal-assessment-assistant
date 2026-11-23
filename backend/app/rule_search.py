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

# Match the observed problem separately from the location. These patterns are
# retrieval hints, never evidence that a tariff's prerequisites are satisfied.
EVENTS = (
    (r'遗留|滞留|剩.{0,3}邮件|邮件.{0,3}(?:没清|未清)', r'遗留|滞留|散落|飘落'),
    (r'三角看袋|废旧袋牌', r'三角看袋|废旧袋牌'),
    (r'破损|破包|水湿|油污|面单脱落', r'破损|水湿|油污|面单脱落|不合格邮件'),
    (r'补码|批条', r'补码|批条'),
    (r'垃圾桶', r'垃圾桶'),
    (r'抛摔|抛扔|扔邮件|踩踏邮件', r'抛摔|抛扔|抛、摔|踩踏邮件|踩、踏'),
    (r'缺员|缺人|缺岗|岗位.{0,4}(?:没人|无人)', r'缺员|缺失|人员不足|缺岗'),
    (r'(?:未|没|不).{0,5}(?:穿|着).{0,3}(?:工服|工作服|工装)|三紧|(?:未|没).{0,3}戴发套', r'工服|工作服|工装|三紧|发套'),
    (r'手机', r'手机'),
    (r'安全帽|安全绳', r'安全帽|安全绳'),
    (r'吸烟|抽烟|抽香烟', r'吸烟|抽烟'),
    (r'打火机|火种', r'打火机|火种|携带与作业无关'),
    (r'一字长龙', r'一字长龙'),
    (r'阶梯码车|车顶放空', r'阶梯码车|车顶放空'),
    (r'漏贴袋牌|没贴袋牌|未贴袋牌', r'漏贴袋牌|未贴袋牌'),
    (r'误开拆|误拆', r'误开拆|误拆'),
    (r'急停', r'急停'),
    (r'挪移牌|移车单', r'挪移牌|移车单'),
)


def event_patterns(facts: str) -> list[str]:
    return [original for query, original in EVENTS if re.search(query, normalize(facts))]


def event_supported(facts: str, rule: dict) -> bool:
    patterns = event_patterns(facts)
    return not patterns or any(event_match(pattern, rule) for pattern in patterns)


def local_evidence(facts: str, rule: dict) -> str | None:
    """An exact excerpt describing a known problem, not a proof of prerequisites."""
    for query, original in EVENTS:
        match = re.search(query, facts)
        if match and event_match(original, rule):
            return match.group(0)
    return None


def event_match(pattern: str, rule: dict) -> bool:
    original = rule.get('original', '')
    if pattern == EVENTS[0][1]:
        # Contents spilling from a damaged parcel is not a leftover mail item.
        original = original.replace('内件散落', '')
    return bool(re.search(pattern, original))


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
        # A common short form omits 邮件; expansion aids search only, not wording.
        if re.search(EVENTS[0][0], query):
            expanded += ' 邮件遗留 散落邮件 滞留邮件'
        query_terms = set(tokens(expanded))
        events = event_patterns(query)
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
                score *= .15
            if "卸车" in query and "遗留" in query and "卸车完毕" in text and "遗留" in text:
                score += 18
            if "小件机" in query and ("遗留" in query or "异常" in query) and "异常邮件" in text and rule.get("stage") == "小件机环节":
                score += 12
            if any(word in query for word in ("工装", "工服", "工作服")) and any(word in text for word in ("三紧", "工服", "工作服")):
                score += 18
            if "小件机" in query and "遗留" in query and "扎带" in text and "遗留" not in text:
                score *= .2
            if events:
                matched = sum(event_match(pattern, rule) for pattern in events)
                # A shared stage cannot outrank the actual reported behaviour.
                score = score * (1 + matched) + 30 * matched if matched else score * .02
                if stages & {'小件机环节', '卸车环节', '装车环节'} and rule.get('stage') in {'小件机环节', '卸车环节', '装车环节'} - stages:
                    score *= .15
            if '附件' in rule.get('stage', ''):
                # Large omnibus rows are references; prefer a focused provision.
                score *= .35
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
    return [{"rank": rank, "id": r["id"], "stage": r.get('stage'), "clause": r["clause"], "original": r["original"],
             "conditions": r.get("applicableConditions"), "pricing": r.get("pricingOptions", [])}
            for rank, r in enumerate(rules, 1)]

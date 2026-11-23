"""Small style-only example selection. Historical amounts are never sent to AI."""
import hashlib
import json
from functools import lru_cache
from .config import settings
from .rule_search import tokens


@lru_cache(maxsize=1)
def library():
    data = (settings.base_dir / 'backend/data/assessment-writing-examples.json').read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def reference(facts):
    examples, _ = library()
    query = set(tokens(facts))
    ranked = sorted(examples['examples'], key=lambda e: len(query & set(tokens(e['problem']))), reverse=True)
    if not ranked or len(query & set(tokens(ranked[0]['problem']))) < 2: return []
    # The reference teaches remediation phrasing only, not a second set of facts.
    return [{'rectification_style': ranked[0]['rectification'], 'instruction': '只学习语气，不复制历史事实；按本次实际问题写整改'}]

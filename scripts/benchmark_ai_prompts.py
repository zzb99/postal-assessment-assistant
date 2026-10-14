"""Offline request-shape comparison. Characters/bytes are NOT billed tokens."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.ai_writing import SYSTEM_PROMPT
from backend.app.rule_search import get_index, prompt_rules
from backend.app.writing_style import library, reference


def compare(facts):
    index = get_index(); examples = library()[0]['examples']
    full = {'rules': index.rules, 'examples': examples}
    shapes = {
        'A_full_original': json.dumps({'facts': facts, **full}, ensure_ascii=False),
        'B_full_stable_prefix': json.dumps({**full, 'facts': facts}, ensure_ascii=False, separators=(',', ':')),
        'C_local_retrieval': json.dumps({'version': index.catalog['version'], 'rules': prompt_rules(index.search(facts)), 'examples': reference(facts), 'facts': facts}, ensure_ascii=False, separators=(',', ':')),
    }
    return {'facts': facts, 'note': '离线载荷结构比较，不是Token、官方缓存命中或账单实测。A是全目录+12样例的重建基线，不是历史API日志。',
            'strategies': {name: {'characters': len(SYSTEM_PROMPT + prompt), 'utf8_bytes': len((SYSTEM_PROMPT + prompt).encode()),
                                 'actual_usage': None, 'actual_cny': None, 'provider_cache_hit': None} for name, prompt in shapes.items()},
            'retrieved_rules': len(index.search(facts)), 'relevant_examples': len(reference(facts)),
            'default': 'C', 'decision_basis': '最小化发送内部资料和一次请求范围；费用选择仍待低额度A/B/C实测，不能宣称70%-90%Token降幅'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('output'); args = parser.parse_args()
    rows = [compare(facts) for facts in ('南5卸车完毕后发现遗留邮件1件', '现场抽烟', '小件机发现遗留1件', '装车时重件压轻件')]
    Path(args.output).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{'facts': r['facts'], 'rules': r['retrieved_rules'], 'sizes': {k:v['characters'] for k,v in r['strategies'].items()}} for r in rows], ensure_ascii=False))

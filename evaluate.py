"""Small synthetic benchmark; never use its scores as a production guarantee."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re

from anonymizer import TextAnonymizer


def parse_case(case):
    annotated = case['text']
    text = 'Normal metin. ' * case.get('prefix_repeat', 0)
    spans, cursor = [], 0
    for match in re.finditer(r'\[\[([A-Z_]+)\|([^\]]+)\]\]', annotated):
        text += annotated[cursor:match.start()]
        start = len(text)
        text += match[2]
        spans.append((start, len(text), match[1]))
        cursor = match.end()
    text += annotated[cursor:]
    return text, spans


def evaluate(engine, cases, profile='strict'):
    metrics = defaultdict(lambda: {'tp': 0, 'fp': 0, 'fn': 0, 'sensitive_chars': 0, 'missed_chars': 0})
    overmasked, failures = 0, []
    for case in cases:
        text, expected = parse_case(case)
        _, detected = engine.anonymize(text, profile=profile)
        expected, predicted = set(expected), {(e['start'], e['end'], e['label']) for e in detected}
        for _, _, label in expected & predicted:
            metrics[label]['tp'] += 1
        for _, _, label in predicted - expected:
            metrics[label]['fp'] += 1
        for _, _, label in expected - predicted:
            metrics[label]['fn'] += 1
        covered = {i for start, end, _ in predicted for i in range(start, end)}
        target = {i for start, end, _ in expected for i in range(start, end)}
        for start, end, label in expected:
            metrics[label]['sensitive_chars'] += end - start
            metrics[label]['missed_chars'] += len(set(range(start, end)) - covered)
        overmasked += len(covered - target)
        if expected != predicted:
            failures.append({'id': case['id'], 'missed_spans': sorted(expected - predicted),
                             'extra_spans': sorted(predicted - expected)})
    for counts in metrics.values():
        tp, fp, fn = counts['tp'], counts['fp'], counts['fn']
        counts['precision'] = round(tp / (tp + fp), 4) if tp + fp else None
        counts['recall'] = round(tp / (tp + fn), 4) if tp + fn else None
        counts['false_discovery_rate'] = round(fp / (tp + fp), 4) if tp + fp else None
        counts['miss_rate'] = round(fn / (tp + fn), 4) if tp + fn else None
        n = counts['sensitive_chars']
        counts['sensitive_character_coverage'] = round(1 - counts['missed_chars'] / n, 4) if n else None
    return {'cases': len(cases), 'profile': profile, 'model': os.getenv('ANONYMIZER_MODEL', 'akdeniz27/bert-base-turkish-cased-ner'),
            'by_label': dict(sorted(metrics.items())), 'overmasked_characters': overmasked,
            'differences': failures,
            'note': 'Synthetic diagnostic set; exact typed spans and character coverage are separate metrics.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path(__file__).parent / 'tests/data/synthetic.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if args.offline:
        os.environ['HF_HUB_OFFLINE'] = '1'
    result = evaluate(TextAnonymizer(), json.loads(args.data.read_text(encoding='utf-8')))
    report = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(report + '\n', encoding='utf-8')
    print(report)

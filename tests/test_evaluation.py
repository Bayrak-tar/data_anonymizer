from evaluate import evaluate, parse_case
from anonymizer import TextAnonymizer
from test_anonymizer import FakeNER


def test_benchmark_offsets_and_metrics():
    case = {'id': 'test', 'text': '😀 [[NAME|Ali]] ve [[NAME|Ece]]'}
    text, spans = parse_case(case)
    assert text == '😀 Ali ve Ece'
    assert spans == [(2, 5, 'NAME'), (9, 12, 'NAME')]
    result = evaluate(TextAnonymizer(FakeNER(('Ali',))), [case])
    assert result['by_label']['NAME']['recall'] == .5
    assert result['by_label']['NAME']['sensitive_character_coverage'] == .5
    assert result['by_label']['NAME']['precision'] == 1

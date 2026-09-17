from types import SimpleNamespace
import re

import pytest

from anonymizer import TextAnonymizer, resolve_overlaps, valid_identifier


class FakeNER:
    def __init__(self, names=()):
        self.names = names
        self.tokenizer = SimpleNamespace(is_fast=True, model_max_length=512)
        self.model = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=512))
        self.calls = []

    def __call__(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return [dict(start=m.start(), end=m.end(), word='wrong tokenizer display', score=0.95, entity_group='PER')
                for name in self.names for m in re.finditer(re.escape(name), text)]


@pytest.fixture
def engine():
    return TextAnonymizer(FakeNER(('Ali', 'Can', 'Ece', 'İpek', 'IBM')))


def test_short_names_and_source_offsets(engine):
    text = "😀 Ali'nin, Can ve Ece; Ali."
    masked, entities = engine.anonymize(text, profile='personal')
    assert masked == "😀 [NAME_1]'nin, [NAME_2] ve [NAME_3]; [NAME_1]."
    assert all(e['text'] == text[e['start']:e['end']] for e in entities)


def test_whitelist_never_discards_person(engine):
    assert engine.anonymize('IBM', profile='personal')[0] == '[NAME_1]'


def test_long_input_passes_stride(engine):
    text = 'Normal cümle. ' * 1000 + 'Ece'
    assert engine.anonymize(text)[0].endswith('[NAME_1]')
    assert engine.ner.calls[-1][1]['stride'] > 0


@pytest.mark.parametrize(('label', 'valid', 'invalid'), [
    ('TC', '10000000146', '10000000147'),
    ('IBAN', 'TR33 0006 1005 1978 6457 8413 26', 'TR34 0006 1005 1978 6457 8413 26'),
    ('CREDIT_CARD', '4111 1111 1111 1111', '4111 1111 1111 1112'),
])
def test_checksums(label, valid, invalid):
    assert valid_identifier(label, valid)
    assert not valid_identifier(label, invalid)


def test_invalid_identifier_policy(engine):
    text = 'Referans 12345678901.'
    assert engine.anonymize(text, profile='personal')[0] == text
    assert '12345678901' not in engine.anonymize(text, profile='strict')[0]
    assert '12345678901' not in engine.anonymize('TC: 12345678901', profile='personal')[0]


def test_profiles(engine):
    text = 'VMware 192.168.1.1 12.03.2025'
    assert engine.anonymize(text, profile='personal')[0] == text
    technical = engine.anonymize(text, profile='technical')[0]
    assert 'VMware' not in technical and '192.168.1.1' not in technical and '12.03.2025' in technical
    assert '12.03.2025' not in engine.anonymize(text)[0]


def test_partial_overlap_preserves_entire_sensitive_union():
    text = 'abcdefghijk'
    spans = [dict(start=0, end=6, label='NAME', score=.9, source='ner'),
             dict(start=4, end=9, label='EMAIL', score=.85, source='regex'),
             dict(start=8, end=11, label='PHONE', score=.85, source='regex')]
    resolved = resolve_overlaps(text, spans)
    assert len(resolved) == 1
    assert resolved[0]['text'] == text and resolved[0]['label'] == 'SENSITIVE'


def test_container_wins_and_adjacent_entities_stay_separate():
    spans = [dict(start=0, end=10, label='EMAIL', score=.85, source='regex'),
             dict(start=0, end=3, label='NAME', score=.95, source='ner'),
             dict(start=10, end=12, label='NAME', score=.95, source='ner')]
    assert [e['label'] for e in resolve_overlaps('abcdefghijkl', spans)] == ['EMAIL', 'NAME']


def test_manual_span_and_unicode(engine):
    text = '😀 gizli veri'
    assert engine.anonymize(text, manual_spans=[{'start': 2, 'end': 7}])[0] == '😀 [MANUAL_1] veri'
    with pytest.raises(ValueError):
        engine.anonymize(text, manual_spans=[{'start': 3, 'end': 100}])


def test_customer_context_phone_prefix_and_repeat(engine):
    masked, entities = engine.anonymize('Müşteri No:   12345, +90 (532) 123 45 67; +90 (532) 123 45 67')
    assert masked == 'Müşteri No:   [CUSTOMER_ID_1], [PHONE_1]; [PHONE_1]'


def test_email_keeps_punctuation(engine):
    assert engine.anonymize('Yazın: ali@example.com, sonra.')[0] == 'Yazın: [EMAIL_1], sonra.'


def test_turkish_casing_and_normalization(engine):
    engine.ner = FakeNER(('İpek', 'ipek'))
    assert engine.anonymize('İpek ve ipek')[0] == '[NAME_1] ve [NAME_1]'


def test_split_names_and_wordpieces_are_rejoined(engine):
    engine.ner = FakeNER(('Ah', 'm', 't', 'Yılmaz'))
    masked, entities = engine.anonymize("Ahmt Yılmaz'a", profile='personal')
    assert masked == "[NAME_1]'a"
    assert entities[0]['text'] == 'Ahmt Yılmaz'


def test_organization_exemptions_are_profile_scoped(engine):
    class OrganizationNER(FakeNER):
        def __call__(self, text, **kwargs):
            return [dict(start=0, end=len(text), word=text, score=.9, entity_group='ORG')]
    engine.ner = OrganizationNER()
    assert engine.anonymize('IBM', profile='personal')[0] == 'IBM'
    assert engine.anonymize('IBM', profile='strict')[0] != 'IBM'


def test_existing_structured_format_is_strict_only(engine):
    text = 'Ab123,"transfer","public","today","done","42"'
    assert engine.anonymize(text, profile='personal')[0] == text
    masked = engine.anonymize(text)[0]
    assert masked == '[ID_1],[TRANSACTION_1],"public",[DATE_1],[STATUS_1],[VALUE_1]'

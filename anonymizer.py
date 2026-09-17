"""Detection and masking engine; independent of HTTP."""
import os
import re
import unicodedata
from typing import List

PII_PATTERNS = [
    ("URL",          r"https?://[\w\.\-/\?&=%#:]+"),
    ("EMAIL",        r"(?<![\w.+%-])[\w.+%-]{1,64}@[\w-]+(?:\.[\w-]+)*\.\w{2,63}\b"),
    ("HOSTNAME",     r"\b[a-zA-Z0-9][a-zA-Z0-9\-]*(?:\.[a-zA-Z][a-zA-Z0-9\-]*){2,}\b"),
    ("IBAN",         r"\bTR\s?\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}\b"),
    ("CREDIT_CARD",  r"(?<!\w)(?:[0-9][ -]?){12,18}[0-9](?!\w)"),
    ("CARD_END",     r"\bsonu\s+\d{4}\s+ile\s+biten\b"),
    ("TC",  r"\b[1-9]\d{10}\b"),
    ("ORDER_NO",     r"#[A-Z]{2}-\d{4,}"),
    ("CUSTOMER_ID",  r"\bMüşteri\s+(?:Numara(?:m|sı)?|No)\s*[:#-]?\s*(?P<value>[0-9]{4,})\b"),
    ("REGISTRY_NO",  r"\b\d{6}\b(?=\s+sicil)"),
    ("MESSAGE_ID",   r"(?:(?<=Message ID:)|(?<=Message ID: ))[A-Z][A-Z0-9]+"),
    ("BRAND",        r"\b(?:VxRail|VMware(?:\s+Inc\.?)?|Solar[Ww]inds?|Cohesity|Veeam|Huawei(?:\s+Cloud)?|Dell(?:\s+EMC)?|IBM)\b"),
    ("DEVICE",       r"\b[a-z]{2,5}\s+[a-z]{2,5}\s+[a-z]{2,5}\d{1,2}\b"),
    ("SERVER",       r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z]{2})[A-Z][A-Z0-9]{5,}\b"),
    ("IP_ADDRESS",   r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"),
    ("PHONE",        r"(?<!\w)(?:\+?90[ -]?)?0?\(?[2-5][0-9]{2}\)?[ -]?[0-9]{3}[ -]?[0-9]{2}[ -]?[0-9]{2}(?!\w)"),
    ("PLATE",        r"\b\d{2}\s?[A-ZÇĞİÖŞÜ]{1,3}\s?\d{2,4}\b"),
    ("ADDRESS",      r"\b[A-ZÇĞİÖŞÜa-zçğışöü]+\s+(?:Mah|Cad|Sok|Apt|Bul|Cd|Sk)\.\s*.+?(?=\n|$)"),
    ("DATE",         r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b"),
    ("DATE",         r"\b\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4}\b"),
    ("TIME",         r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)\b"),
]

NER_WHITELIST = {
    "solarwinds", "solar", "winds", "solarwind",
    "vmware", "vmware inc", "vmware inc.", "vxrail", "idrac", "ilo",
    "noc", "itsm", "hbys", "iam", "obs", "rds", "vpn", "nat", "dns",
    "info-phishing", "info", "phishing", "veeam", "cohesity",
    "poweredon", "poweredoff", "javascript",
    "hr", "one nt", "ci", "ci no", "odya",
    "huawei", "huawei cloud", "ibm", "dell", "dell emc",
    "isuzu", "anadolu isuzu", "efes", "adel", "minka", "logo", "celik",
    "tenant", "bucket", "snapshot", "cluster",
}


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text)


# ─── NER + Regex Anonymizer ────────────────────────────────────────────────────


class StructuredDetector:
    def _find_structured_entities(self, text: str) -> List[dict]:
        pattern = re.compile(
            r'\b([A-Za-z][A-Za-z0-9]+),'
            r'("[^"]*"),'
            r'("[^"]*"),'
            r'("[^"]*"),'
            r'("[^"]*"),'
            r'("[^"]*")'
        )
        results = []
        for m in pattern.finditer(text):
            results.append({"start": m.start(1), "end": m.end(1), "text": m.group(1), "label": "ID", "score": 1.0})
            if m.group(2) != '""':
                results.append({"start": m.start(2), "end": m.end(2), "text": m.group(2), "label": "TRANSACTION", "score": 1.0})
            if m.group(4) != '""':
                results.append({"start": m.start(4), "end": m.end(4), "text": m.group(4), "label": "DATE", "score": 1.0})
            if m.group(5) != '""':
                results.append({"start": m.start(5), "end": m.end(5), "text": m.group(5), "label": "STATUS", "score": 1.0})
            if m.group(6) != '""':
                results.append({"start": m.start(6), "end": m.end(6), "text": m.group(6), "label": "VALUE", "score": 1.0})
        return results


PERSONAL_LABELS = {
    'NAME', 'LOCATION', 'ORGANIZATION', 'EMAIL', 'PHONE', 'TC', 'IBAN',
    'CREDIT_CARD', 'CARD_END', 'CUSTOMER_ID', 'REGISTRY_NO', 'PLATE', 'ADDRESS',
}
TECHNICAL_LABELS = PERSONAL_LABELS | {
    'URL', 'HOSTNAME', 'IP_ADDRESS', 'ORDER_NO', 'MESSAGE_ID', 'BRAND', 'DEVICE', 'SERVER',
}
PROFILES = {'personal': PERSONAL_LABELS, 'technical': TECHNICAL_LABELS, 'strict': None}


def canonical(value: str) -> str:
    return _normalize(value).translate(str.maketrans({'İ': 'i', 'I': 'ı'})).lower().strip()


def valid_identifier(label: str, value: str) -> bool:
    compact = re.sub(r'[\s-]', '', value).upper()
    if label == 'TC':
        if not re.fullmatch(r'[1-9][0-9]{10}', compact):
            return False
        d = list(map(int, compact))
        return (sum(d[:9:2]) * 7 - sum(d[1:8:2])) % 10 == d[9] and sum(d[:10]) % 10 == d[10]
    if label == 'IBAN':
        if not re.fullmatch(r'TR[0-9]{24}', compact):
            return False
        return int(compact[4:] + '2927' + compact[2:4]) % 97 == 1
    if label == 'CREDIT_CARD':
        if not re.fullmatch(r'[0-9]{13,19}', compact) or len(set(compact)) == 1:
            return False
        digits = list(map(int, compact[::-1]))
        return sum(d if i % 2 == 0 else d * 2 - (9 if d > 4 else 0)
                   for i, d in enumerate(digits)) % 10 == 0
    return True


def resolve_overlaps(text: str, entities: list[dict]) -> list[dict]:
    """Mask the complete union of overlapping detections, never discard a tail."""
    groups = []
    for ent in sorted(entities, key=lambda e: (e['start'], e['end'])):
        if groups and ent['start'] < groups[-1]['end']:
            group = groups[-1]
            group['end'] = max(group['end'], ent['end'])
            group['members'].append(ent)
        else:
            groups.append({'start': ent['start'], 'end': ent['end'], 'members': [ent]})
    result = []
    priority = {'manual': 4, 'validated': 3, 'structured': 2, 'regex': 1, 'ner': 0}
    for group in groups:
        start, end = group['start'], group['end']
        # Prefer a detector covering the entire region; otherwise mark mixed unions.
        covering = [e for e in group['members'] if e['start'] == start and e['end'] == end]
        best = max(covering or group['members'], key=lambda e: (
            priority.get(e.get('source', 'structured'), 0), e['score'], e['end'] - e['start']))
        labels = {e['label'] for e in group['members']}
        label = best['label'] if covering or len(labels) == 1 else 'SENSITIVE'
        result.append({**best, 'start': start, 'end': end, 'text': text[start:end], 'label': label})
    return result


class TextAnonymizer(StructuredDetector):
    def __init__(self, ner=None):
        if ner is None:
            from transformers import pipeline
            ner = pipeline(
                'token-classification',
                model=os.getenv('ANONYMIZER_MODEL', 'akdeniz27/bert-base-turkish-cased-ner'),
                aggregation_strategy='simple',
            )
        self.ner = ner
        if not ner.tokenizer.is_fast:
            raise ValueError('Long-text processing requires a fast tokenizer')
        max_positions = getattr(getattr(ner.model, 'config', None), 'max_position_embeddings', 512)
        ner.tokenizer.model_max_length = min(ner.tokenizer.model_max_length, max_positions)
        self.stride = min(64, max(1, (ner.tokenizer.model_max_length - 2) // 4))
        self.patterns = [(label, re.compile(pattern, 0 if label in {
            'BRAND', 'DEVICE', 'SERVER', 'MESSAGE_ID'} else re.IGNORECASE))
            for label, pattern in PII_PATTERNS]

    def _find_ner_entities(self, text: str, threshold: float, profile: str) -> list[dict]:
        entities = []
        for ent in self.ner(text, stride=self.stride):
            label = {'PER': 'NAME', 'LOC': 'LOCATION', 'ORG': 'ORGANIZATION'}.get(ent['entity_group'])
            if not label or float(ent['score']) < threshold:
                continue
            start, end = int(ent['start']), int(ent['end'])
            value = text[start:end]  # Tokenizer display strings can differ from the input.
            if not value.strip():
                continue
            if (profile != 'strict' and label == 'ORGANIZATION'
                    and (canonical(value).rstrip('.\'"') in NER_WHITELIST
                         or value.strip().lower().rstrip('.\'"') in NER_WHITELIST)):
                continue
            entities.append(dict(start=start, end=end, text=value, label=label,
                                 score=round(float(ent['score']), 4), source='ner'))
        # Rejoin adjacent wordpieces and first/last names split into separate groups.
        merged = []
        for ent in sorted(entities, key=lambda e: (e['start'], e['end'])):
            previous = merged[-1] if merged else None
            gap = text[previous['end']:ent['start']] if previous else ''
            if (previous and previous['label'] == ent['label']
                    and previous['end'] <= ent['start'] and len(gap) <= 3
                    and not gap.strip(" '-’") and '\n' not in gap and '\r' not in gap):
                previous['end'] = ent['end']
                previous['text'] = text[previous['start']:previous['end']]
                previous['score'] = min(previous['score'], ent['score'])
            else:
                merged.append(ent)
        return merged

    def _find_regex_entities(self, text: str, profile: str) -> list[dict]:
        entities = []
        for label, pattern in self.patterns:
            for match in pattern.finditer(text):
                start, end = match.span('value') if 'value' in match.groupdict() else match.span()
                value = text[start:end]
                score, source = 0.85, 'regex'
                if label in {'TC', 'IBAN', 'CREDIT_CARD'}:
                    valid = valid_identifier(label, value)
                    context = text[max(0, start - 40):start]
                    cue = {'TC': r'(?:t\.?c\.?|kimlik)\s*(?:no|numarası)?\s*[:#-]?\s*$',
                           'IBAN': r'iban\s*[:#-]?\s*$',
                           'CREDIT_CARD': r'kart\s*(?:no|numarası)?\s*[:#-]?\s*$'}[label]
                    if not valid and profile != 'strict' and not re.search(cue, context, re.I):
                        continue
                    score, source = (0.99, 'validated') if valid else (0.55, 'regex')
                elif label == 'PHONE':
                    digits = re.sub(r'\D', '', value)
                    has_context = re.search(r'(?:tel(?:efon)?|gsm|cep)\s*[:#-]?\s*$', text[max(0, start-30):start], re.I)
                    if profile != 'strict' and len(digits) == 10 and digits[0] != '5' and not has_context:
                        continue
                entities.append(dict(start=start, end=end, text=value, label=label, score=score, source=source))
        return entities

    def anonymize(self, text: str, threshold: float = 0.4, profile: str = 'strict',
                  manual_spans: list[dict] | None = None) -> tuple[str, list[dict]]:
        if profile not in PROFILES:
            raise ValueError('Unknown profile')
        entities = self._find_ner_entities(text, threshold, profile) + self._find_regex_entities(text, profile)
        if profile == 'strict':
            entities += self._find_structured_entities(text)
        allowed = PROFILES[profile]
        entities = [e for e in entities if allowed is None or e['label'] in allowed]
        for span in manual_spans or []:
            start, end = span['start'], span['end']
            if not 0 <= start < end <= len(text):
                raise ValueError('Manual span outside input')
            entities.append(dict(start=start, end=end, text=text[start:end], label='MANUAL', score=1.0, source='manual'))
        entities = resolve_overlaps(text, entities)
        counters, placeholders = {}, {}
        for ent in entities:
            value = canonical(ent['text'])
            if ent['label'] in {'PHONE', 'IBAN', 'CREDIT_CARD', 'TC'}:
                value = re.sub(r'[\s()+-]', '', value)
            key = (ent['label'], value)
            if key not in placeholders:
                label = ent['label']
                counters[label] = counters.get(label, 0) + 1
                placeholders[key] = f'[{label}_{counters[label]}]'
            ent['placeholder'] = placeholders[key]
        parts, cursor = [], 0
        for ent in entities:
            parts.extend((text[cursor:ent['start']], ent['placeholder']))
            cursor = ent['end']
        parts.append(text[cursor:])
        return ''.join(parts), entities


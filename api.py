from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Tuple
from transformers import pipeline
import uvicorn
import re
import unicodedata


# ─── Regex Patterns ────────────────────────────────────────────────────────────

PII_PATTERNS = [
    ("URL",          r"https?://[\w\.\-/\?&=%#:]+"),
    ("EMAIL",        r"[^\s\(\)<>]+@[\w\.\-]+\.\w{2,}"),
    ("HOSTNAME",     r"\b[a-zA-Z0-9][a-zA-Z0-9\-]*(?:\.[a-zA-Z][a-zA-Z0-9\-]*){2,}\b"),
    ("IBAN",         r"\bTR\s?\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}\b"),
    ("CREDIT_CARD",  r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b"),
    ("CARD_END",     r"\bsonu\s+\d{4}\s+ile\s+biten\b"),
    ("TC",  r"\b[1-9]\d{10}\b"),
    ("ORDER_NO",     r"#[A-Z]{2}-\d{4,}"),
    ("CUSTOMER_ID",  r"(?<=Müşteri Numaram:\s)\d{4,}"),
    ("REGISTRY_NO",  r"\b\d{6}\b(?=\s+sicil)"),
    ("MESSAGE_ID",   r"(?:(?<=Message ID:)|(?<=Message ID: ))[A-Z][A-Z0-9]+"),
    ("BRAND",        r"\b(?:VxRail|VMware(?:\s+Inc\.?)?|Solar[Ww]inds?|Cohesity|Veeam|Huawei(?:\s+Cloud)?|Dell(?:\s+EMC)?|IBM)\b"),
    ("DEVICE",       r"\b[a-z]{2,5}\s+[a-z]{2,5}\s+[a-z]{2,5}\d{1,2}\b"),
    ("SERVER",       r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z]{2})[A-Z][A-Z0-9]{5,}\b"),
    ("IP_ADDRESS",   r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"),
    ("PHONE",        r"\b(?:\+?90[\s\-]?)?0?(?:\(?\d{3}\)?[\s\-]?)\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b"),
    ("PLATE",        r"\b\d{2}\s?[A-ZÇĞİÖŞÜ]{1,3}\s?\d{2,4}\b"),
    ("ADDRESS",      r"[A-ZÇĞİÖŞÜa-zçğışöü]+\s+(?:Mah|Cad|Sok|Apt|Bul|Cd|Sk)\.\s*.+?(?=\n|$)"),
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

class TextAnonymizer:
    def __init__(self):
        self.ner = pipeline(
            "ner",
            model="akdeniz27/bert-base-turkish-cased-ner",
            aggregation_strategy="simple",
        )
        self.ner_label_map = {
            "PER": "NAME",
            "LOC": "LOCATION",
            "ORG": "ORGANIZATION",
        }

    def _find_ner_entities(self, text: str, threshold: float) -> List[dict]:
        raw = self.ner(text)
        if not raw:
            return []

        entities = []
        for ent in raw:
            if ent["score"] < threshold:
                continue
            label = self.ner_label_map.get(ent["entity_group"])
            if not label:
                continue
            entities.append({
                "start": ent["start"],
                "end": ent["end"],
                "text": ent["word"],
                "label": label,
                "score": round(ent["score"], 4),
            })

        if not entities:
            return []

        entities.sort(key=lambda e: e["start"])
        merged = [entities[0]]
        for ent in entities[1:]:
            prev = merged[-1]
            gap = text[prev["end"]:ent["start"]]
            if ent["label"] == prev["label"] and len(gap) <= 3 and gap.strip(" '.-") == "":
                prev["end"] = ent["end"]
                prev["text"] = text[prev["start"]:prev["end"]]
                prev["score"] = min(prev["score"], ent["score"])
            else:
                merged.append(ent)

        filtered = []
        for ent in merged:
            clean = ent["text"].strip().lower().rstrip(".'\"")
            clean_norm = _normalize(clean)
            if clean in NER_WHITELIST or clean_norm in NER_WHITELIST:
                continue
            if len(clean) <= 3:
                continue
            filtered.append(ent)

        return filtered

    _CASE_SENSITIVE = {"BRAND", "DEVICE", "SERVER", "MESSAGE_ID"}

    def _find_regex_entities(self, text: str) -> List[dict]:
        results = []
        for label, pattern in PII_PATTERNS:
            flags = 0 if label in self._CASE_SENSITIVE else re.IGNORECASE
            for m in re.finditer(pattern, text, flags):
                results.append({
                    "start": m.start(),
                    "end": m.end(),
                    "text": m.group(),
                    "label": label,
                    "score": 1.0,
                })
        return results

    def _find_structured_entities(self, text: str) -> List[dict]:
        pattern = re.compile(
            r'([A-Za-z][A-Za-z0-9]+),'
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

    @staticmethod
    def _expand_email_from_ner(text: str, ner_ents: List[dict], regex_ents: List[dict]) -> List[dict]:
        regex_spans = set()
        for r in regex_ents:
            regex_spans.update(range(r["start"], r["end"]))

        cleaned = []
        for ent in ner_ents:
            ent_span = set(range(ent["start"], ent["end"]))
            if ent_span & regex_spans:
                continue
            if ent["end"] < len(text) and text[ent["end"]] == "@":
                continue
            if ent["start"] > 0 and text[ent["start"] - 1] == "@":
                continue
            cleaned.append(ent)
        return cleaned

    def anonymize(self, text: str, threshold: float = 0.40) -> Tuple[str, List[dict]]:
        structured_entities = self._find_structured_entities(text)
        ner_entities = self._find_ner_entities(text, threshold)
        regex_entities = self._find_regex_entities(text)

        ner_entities = self._expand_email_from_ner(text, ner_entities, regex_entities)

        all_entities = structured_entities + regex_entities + ner_entities

        all_entities.sort(key=lambda e: (-e["score"], -(e["end"] - e["start"])))
        used = set()
        filtered = []
        for ent in all_entities:
            span = set(range(ent["start"], ent["end"]))
            if span & used:
                continue
            used |= span
            filtered.append(ent)

        # Baştan sona sırala, aynı metin → aynı placeholder
        filtered.sort(key=lambda e: e["start"])
        label_counter: Dict[str, int] = {}
        text_to_placeholder: Dict[str, str] = {}

        for ent in filtered:
            key = (ent["label"], ent["text"].strip().lower())
            if key in text_to_placeholder:
                ent["placeholder"] = text_to_placeholder[key]
            else:
                label_counter[ent["label"]] = label_counter.get(ent["label"], 0) + 1
                ent["placeholder"] = f"[{ent['label']}_{label_counter[ent['label']]}]"
                text_to_placeholder[key] = ent["placeholder"]

        # Sondan başa maskele
        masked = text
        for ent in reversed(filtered):
            masked = masked[:ent["start"]] + ent["placeholder"] + masked[ent["end"]:]

        return masked, filtered


# ─── Pydantic Models ───────────────────────────────────────────────────────────

class AnonymizeRequest(BaseModel):
    text: str = Field(..., json_schema_extra={
        "example": "Ahmet Yılmaz's email is ahmet@gmail.com, phone 0532 123 45 67, ID: 12345678901"
    })
    threshold: float = Field(default=0.40, ge=0.0, le=1.0)


class EntityOut(BaseModel):
    start: int
    end: int
    text: str
    label: str
    score: float
    placeholder: str


class AnonymizeResponse(BaseModel):
    masked_text: str
    entities: List[EntityOut]
    entities_count: int


# ─── FastAPI App ───────────────────────────────────────────────────────────────

_anonymizer: Optional[TextAnonymizer] = None


@asynccontextmanager
async def lifespan(_):
    global _anonymizer
    _anonymizer = TextAnonymizer()
    yield


app = FastAPI(
    title="Text Anonymization API",
    version="1.2.0",
    docs_url="/",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "model_loaded": _anonymizer is not None}


@app.post("/anonymize", response_model=AnonymizeResponse, tags=["Anonymization"])
async def anonymize(req: AnonymizeRequest):
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")
    if _anonymizer is None:
        raise HTTPException(503, "Model not loaded yet")

    masked, entities = _anonymizer.anonymize(req.text, req.threshold)
    return AnonymizeResponse(
        masked_text=masked,
        entities=[EntityOut(**e) for e in entities],
        entities_count=len(entities),
    )


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  Text Anonymization API starting...")
    print("=" * 50)
    print("  Swagger UI  : http://localhost:8001/")
    print("  Redoc       : http://localhost:8001/redoc")
    print("  Health Check: http://localhost:8001/health")
    print("=" * 50 + "\n")
    uvicorn.run("api:app", host="0.0.0.0", port=8001, log_level="info")
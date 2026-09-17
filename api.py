"""HTTP service for the local anonymization engine."""
import asyncio
from collections import Counter
from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
import uvicorn

from anonymizer import TextAnonymizer

MAX_TEXT_LENGTH = 100_000
MAX_BODY_BYTES = 1_000_000
STATIC_DIR = Path(__file__).resolve().parent / 'static'


class ManualSpan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: int = Field(ge=0, strict=True)
    end: int = Field(gt=0, strict=True)


class AnonymizeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    threshold: float = Field(default=0.4, ge=0, le=1)
    profile: Literal['personal', 'technical', 'strict'] = 'strict'
    include_originals: bool = False
    manual_spans: list[ManualSpan] = Field(default_factory=list, max_length=1000)

    @model_validator(mode='after')
    def validate_spans(self):
        if not self.text.strip():
            raise ValueError('Text cannot be empty')
        for span in self.manual_spans:
            if not 0 <= span.start < span.end <= len(self.text):
                raise ValueError('Manual span outside input')
        return self


class EntityOut(BaseModel):
    start: int
    end: int
    text: str | None = None
    label: str
    score: float
    placeholder: str


class AnonymizeResponse(BaseModel):
    masked_text: str
    entities: list[EntityOut]
    entities_count: int
    counts_by_label: dict[str, int]
    profile: str


class RequestGuard:
    """Bound actual body bytes (including chunked requests), authenticate before parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = list(message.get('headers', [])) + [
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer')]
                if scope['path'] not in {'/docs', '/docs/oauth2-redirect', '/redoc'}:
                    message['headers'].append((b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"))
            await send(message)

        if scope['path'] == '/anonymize' and scope['method'] == 'POST':
            headers = dict(scope['headers'])
            key = os.getenv('ANONYMIZER_API_KEY', '')
            if key and not hmac.compare_digest(headers.get(b'x-api-key', b''), key.encode('utf-8')):
                return await JSONResponse({'detail': 'Invalid API key'}, status_code=401)(scope, receive, secured_send)
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > MAX_BODY_BYTES:
                    return await JSONResponse({'detail': 'Request body too large'}, status_code=413)(scope, receive, secured_send)
                if not message.get('more_body', False):
                    break
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            return await self.app(scope, bounded_receive, secured_send)
        return await self.app(scope, receive, secured_send)


@asynccontextmanager
async def lifespan(app):
    app.state.anonymizer = await run_in_threadpool(TextAnonymizer)
    app.state.processing = asyncio.Semaphore(1)
    yield
    app.state.anonymizer = None


app = FastAPI(title='Text Anonymization API', version='2.0.0', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
origins = [value.strip() for value in os.getenv('ANONYMIZER_CORS_ORIGINS', '').split(',') if value.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=['POST'], allow_headers=['Content-Type', 'X-API-Key'])
app.add_middleware(RequestGuard)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # FastAPI's default validation response echoes invalid input, possibly containing PII.
    return JSONResponse(status_code=422, content={'detail': 'Invalid request', 'errors': [
        {'loc': list(error['loc']), 'type': error['type']} for error in exc.errors()]})


@app.get('/', include_in_schema=False)
async def web_app():
    return FileResponse(STATIC_DIR / 'index.html')


@app.get('/health', include_in_schema=False)
async def health():
    loaded = getattr(app.state, 'anonymizer', None) is not None
    return JSONResponse({'status': 'ok' if loaded else 'unavailable', 'model_loaded': loaded,
                         'authentication_required': bool(os.getenv('ANONYMIZER_API_KEY')),
                         'max_text_length': MAX_TEXT_LENGTH}, status_code=200 if loaded else 503)


@app.post('/anonymize', response_model=AnonymizeResponse, response_model_exclude_none=True,
          tags=['Anonymization'])
async def anonymize(req: AnonymizeRequest):
    engine = getattr(app.state, 'anonymizer', None)
    if engine is None:
        raise HTTPException(503, 'Model not loaded yet')
    gate = app.state.processing
    if gate.locked():
        raise HTTPException(429, 'Service busy; retry shortly', headers={'Retry-After': '2'})
    async with gate:
        try:
            masked, entities = await run_in_threadpool(
                engine.anonymize, req.text, req.threshold, req.profile,
                [span.model_dump() for span in req.manual_spans])
        except Exception:
            # Do not include original text or exception details in responses/logs.
            raise HTTPException(503, 'Anonymization failed; no result was produced') from None
    return AnonymizeResponse(
        masked_text=masked,
        entities=[EntityOut(**{key: value for key, value in entity.items()
                              if key != 'text' or req.include_originals}) for entity in entities],
        entities_count=len(entities), counts_by_label=dict(Counter(e['label'] for e in entities)),
        profile=req.profile,
    )


if __name__ == '__main__':
    uvicorn.run('api:app', host=os.getenv('ANONYMIZER_HOST', '127.0.0.1'), port=8001,
                log_level='info', access_log=False)

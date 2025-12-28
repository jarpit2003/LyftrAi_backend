import os
from typing import Optional
import hmac
import hashlib
import time
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager
import uvicorn

from .config import get_settings, Settings
from .models import Message, MessagesResponse, StatsResponse, initialize_database
from .storage import StorageManager
from .logging_utils import get_logger, setup_logging
from .metrics import MetricsCollector, prom_metrics


logger = get_logger(__name__)

metrics = MetricsCollector()
storage = StorageManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(level=settings.log_level, format_type=settings.log_format, log_file=settings.log_file)
    logger.info("Application startup")
    initialize_database()
    await storage.initialize()
    yield
    logger.info("Application shutdown")


app = FastAPI(
    title="Webhook Message Service",
    description="A service for receiving webhook messages and retrieving statistics",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except Exception:
        status = 500
        raise
    finally:
        prom_metrics.inc_http_request(path=path, status=status)
        prom_metrics.observe_latency(time.perf_counter() - start)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/health/live")
async def liveness_check():
    return {"status": "live"}


@app.get("/health/ready")
async def readiness_check(settings: Settings = Depends(get_settings)):
    if not settings.is_ready():
        raise HTTPException(status_code=503, detail="Service not ready - missing WEBHOOK_SECRET")

    ok, reason = await storage.check_ready()
    if not ok:
        if reason == "db_unreachable":
            raise HTTPException(status_code=503, detail="Service not ready - DB unreachable")
        raise HTTPException(status_code=503, detail="Service not ready - schema not applied")

    return {"status": "ready"}


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Verify HMAC SHA256 signature using constant-time comparison"""
    if not secret or not body or not signature:
        return False
    
    # Calculate expected signature
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature)


@app.post("/webhook")
async def receive_webhook(
    request: Request,
    settings: Settings = Depends(get_settings)
):
    try:
        # Get the signature from header
        x_signature = request.headers.get("X-Signature")
        if not x_signature:
            prom_metrics.inc_webhook_result("invalid_signature")
            logger.error("Missing X-Signature header", extra={'extra_fields': {"result": "invalid_signature"}})
            raise HTTPException(status_code=401, detail="invalid signature")
        
        # Get raw request body
        body = await request.body()
        
        # Verify signature
        if not verify_signature(settings.webhook_secret, body, x_signature):
            prom_metrics.inc_webhook_result("invalid_signature")
            logger.error("Invalid signature verification", extra={'extra_fields': {"result": "invalid_signature"}})
            raise HTTPException(status_code=401, detail="invalid signature")
        
        # Parse + validate JSON payload after signature verification
        import json
        from pydantic import ValidationError

        try:
            payload_data = json.loads(body)
            message = Message(**payload_data)

        except (json.JSONDecodeError, ValidationError) as e:
            prom_metrics.inc_webhook_result("validation_error")
            logger.error(
                f"Payload validation error: {str(e)}",
                extra={'extra_fields': {"result": "validation_error"}},
            )
            raise HTTPException(status_code=422, detail="Validation error")

        # Save message (idempotent - handles duplicates gracefully)
        await storage.save_message(message)
        metrics.increment_messages_received()

        logger.info(f"Received webhook: {message.message_id}")

        prom_metrics.inc_webhook_result("ok")

        return {"status": "ok"}
        
    except HTTPException:
        # Re-raise HTTP exceptions (including 401, 422)
        raise
    except Exception as e:
        prom_metrics.inc_webhook_result("error")
        logger.error(f"Error processing webhook: {str(e)}")
        metrics.increment_errors()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/messages", response_model=MessagesResponse)
async def get_messages(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    from_: Optional[str] = Query(None, alias="from"),
    since: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    settings: Settings = Depends(get_settings)
):
    try:
        messages, total = await storage.get_messages(
            limit=limit,
            offset=offset,
            from_msisdn=from_,
            since=since,
            q=q,
        )
        metrics.increment_messages_requested()
        return {"data": messages, "total": total, "limit": limit, "offset": offset}
        
    except Exception as e:
        logger.error(f"Error retrieving messages: {str(e)}")
        metrics.increment_errors()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/stats", response_model=StatsResponse)
async def get_stats(settings: Settings = Depends(get_settings)):
    try:
        stats = await storage.get_stats()
        metrics.increment_stats_requested()
        return stats
        
    except Exception as e:
        logger.error(f"Error retrieving stats: {str(e)}")
        metrics.increment_errors()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/metrics")
async def get_metrics(settings: Settings = Depends(get_settings)):
    return PlainTextResponse(prom_metrics.export(), media_type="text/plain; version=0.0.4")


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )

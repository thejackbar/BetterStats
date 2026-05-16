import logging
from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/playhq")
async def receive_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Webhook received non-JSON payload")
        return Response(status_code=400)

    event_type = payload.get("type", "")
    logger.info(f"Webhook received: {event_type} (no handler registered)")

    # Always return 200 to PlayHQ so it doesn't retry
    return {"status": "ok"}

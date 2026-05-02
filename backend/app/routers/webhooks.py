import logging
from fastapi import APIRouter, Request, Response

from app.services.sync import process_game_updated_webhook

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
    logger.info(f"Webhook received: {event_type}")

    if event_type == "GAME.UPDATED":
        try:
            await process_game_updated_webhook(payload)
        except Exception as e:
            logger.error(f"Error processing GAME.UPDATED webhook: {e}")

    # Always return 200 to PlayHQ so it doesn't retry
    return {"status": "ok"}

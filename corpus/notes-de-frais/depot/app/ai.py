import base64

import httpx

from .config import settings

INSTRUCTION = (
    "Lis ce justificatif de dépense. Réponds uniquement en JSON avec deux champs : "
    '"date" (AAAA-MM-JJ) et "montant" (montant TTC en euros, nombre décimal).'
)


def read_receipt(content: bytes, content_type: str) -> dict:
    """Demande au service d'IA la date et le montant d'un justificatif."""
    response = httpx.post(
        settings.ai_endpoint,
        headers={"Authorization": f"Bearer {settings.ai_api_key}"},
        json={
            "instruction": INSTRUCTION,
            "document": {"media_type": content_type, "data": base64.b64encode(content).decode()},
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()

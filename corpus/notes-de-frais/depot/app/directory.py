from urllib.parse import quote

import httpx

from .config import settings


def direct_reports(manager_email: str) -> set[str]:
    """Adresses des salariés rattachés directement au manager, selon l'annuaire."""
    response = httpx.get(
        f"{settings.directory_url}/users/{quote(manager_email)}/reports",
        headers={"Authorization": f"Bearer {settings.directory_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return {user["email"] for user in response.json()}

import httpx

from .config import settings


def send_to_accounting(notes: list[dict]) -> None:
    response = httpx.post(
        f"{settings.compta_url}/imports/expense-notes",
        headers={"Authorization": f"Bearer {settings.compta_token}"},
        json={"notes": notes},
        timeout=30,
    )
    response.raise_for_status()

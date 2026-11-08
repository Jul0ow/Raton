from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer = HTTPBearer()


@dataclass
class User:
    email: str
    name: str
    roles: set[str]


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    discovery = httpx.get(f"{settings.oidc_issuer}/.well-known/openid-configuration", timeout=10)
    discovery.raise_for_status()
    return jwt.PyJWKClient(discovery.json()["jwks_uri"])


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> User:
    token = credentials.credentials
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide")
    email = claims.get("email")
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton sans adresse e-mail")
    return User(email=email, name=claims.get("name", email), roles=set(claims.get("roles", [])))


def require_role(role: str):
    def checker(user: User = Depends(current_user)) -> User:
        if role not in user.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès refusé")
        return user

    return checker

"""
Verifies Clerk-issued session JWTs against Clerk's public JWKS endpoint.

NOT hand-verified against a live Clerk instance in this environment (no
network access here) — the shape follows Clerk's documented RS256/JWKS
flow, but confirm the claim name for user id ('sub' is standard, but
double-check in Clerk's dashboard -> JWT templates if you customize it).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWKClient

from core.config import get_settings

_bearer = HTTPBearer()


class ClerkAuth:
    def __init__(self, jwks_url: str):
        self._jwk_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> str:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
        return payload["sub"]


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    settings = get_settings()
    auth = ClerkAuth(settings.clerk_jwks_url)
    return auth.verify(credentials.credentials)

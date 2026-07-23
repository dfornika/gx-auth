from datetime import datetime

from ninja import Router, Schema
from ninja.security import APIKeyHeader

from .models import APIKey


class BearerTokenAuth(APIKeyHeader):
    """Authenticate via `Authorization: Bearer <api-key>`.

    Mirrors gx-core. The key identifies the user; OpenFGA makes authorization
    decisions elsewhere.
    """

    param_name = "Authorization"

    def authenticate(self, request, key):
        if not key or not key.startswith("Bearer "):
            return None
        raw_key = key[len("Bearer ") :]
        prefix = raw_key[: APIKey.PREFIX_LEN]
        try:
            api_key = APIKey.objects.select_related("user").get(prefix=prefix, revoked=False)
        except APIKey.DoesNotExist:
            return None
        if api_key.verify(raw_key):
            api_key.touch()
            request.api_key = api_key
            request.user = api_key.user
            return api_key.user
        return None


# --- Schemas ---------------------------------------------------------------


class UserOut(Schema):
    id: int
    username: str
    email: str
    sub: str | None
    is_staff: bool


class APIKeyIn(Schema):
    name: str


class APIKeyCreatedOut(Schema):
    id: int
    name: str
    prefix: str
    key: str  # raw token — shown once only
    created_at: datetime


class APIKeyOut(Schema):
    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class ErrorOut(Schema):
    detail: str


# --- Router ----------------------------------------------------------------

router = Router(tags=["auth"])


@router.get("/me", response=UserOut)
def me(request):
    return request.user


@router.get("/api-keys", response=list[APIKeyOut])
def list_api_keys(request):
    return request.user.api_keys.all()


@router.post("/api-keys", response={201: APIKeyCreatedOut})
def create_api_key(request, payload: APIKeyIn):
    api_key, raw_key = APIKey.generate(user=request.user, name=payload.name)
    return 201, {
        "id": api_key.pk,
        "name": api_key.name,
        "prefix": api_key.prefix,
        "key": raw_key,
        "created_at": api_key.created_at,
    }


@router.delete("/api-keys/{key_id}", response={204: None, 404: ErrorOut})
def revoke_api_key(request, key_id: int):
    try:
        api_key = request.user.api_keys.get(pk=key_id)
    except APIKey.DoesNotExist:
        return 404, {"detail": "API key not found."}
    api_key.revoked = True
    api_key.save(update_fields=["revoked"])
    return 204, None

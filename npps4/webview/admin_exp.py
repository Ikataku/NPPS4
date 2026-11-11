import os

import fastapi
import pydantic

from .. import idol
from ..app import app
from ..system import admin_exp
from ..system import core
from ..system import user as system_user


class SetAbsoluteExpRequest(pydantic.BaseModel):
    user_id: pydantic.StrictInt
    total_exp: pydantic.StrictInt


class AddExpMultiplierRequest(pydantic.BaseModel):
    user_id: pydantic.StrictInt
    base_exp: pydantic.StrictInt
    multiplier: pydantic.StrictInt


def _require_admin_exp_access(request: fastapi.Request, authorization: str | None) -> None:
    expected_token = os.environ.get("NPPS4_ADMIN_EXP_TOKEN")
    if not expected_token:
        raise fastapi.HTTPException(status_code=404, detail="Admin EXP API is disabled")

    client = request.client
    client_host = client.host if client is not None else None
    if not admin_exp.is_loopback_address(client_host):
        raise fastapi.HTTPException(status_code=403, detail="Loopback access required")

    if not admin_exp.verify_admin_exp_token(expected_token, authorization):
        raise fastapi.HTTPException(status_code=401, detail="Invalid admin authorization")


@app.core.post("/admin/exp/total")
async def set_absolute_exp(
    payload: SetAbsoluteExpRequest,
    request: fastapi.Request,
    authorization: str | None = fastapi.Header(default=None),
):
    _require_admin_exp_access(request, authorization)

    if payload.user_id <= 0:
        raise fastapi.HTTPException(status_code=422, detail="user_id must be a positive integer")

    try:
        async with idol.BasicSchoolIdolContext() as context:
            target = await system_user.get(context, payload.user_id)
            if target is None:
                raise fastapi.HTTPException(status_code=404, detail="User not found")

            before_level = target.level
            before_exp = target.exp
            transitions = await system_user.set_exp_total(context, target, payload.total_exp)
            after_level = target.level
            after_exp = target.exp
    except ValueError as exc:
        raise fastapi.HTTPException(status_code=422, detail=str(exc)) from None

    return {
        "user_id": payload.user_id,
        "before_level": before_level,
        "after_level": after_level,
        "before_exp": before_exp,
        "after_exp": after_exp,
        "rank_transitions": [{"level": item.level, "from_exp": item.from_exp} for item in transitions],
    }



@app.core.post("/admin/exp/add")
async def add_exp_with_multiplier(
    payload: AddExpMultiplierRequest,
    request: fastapi.Request,
    authorization: str | None = fastapi.Header(default=None),
):
    _require_admin_exp_access(request, authorization)

    if payload.user_id <= 0:
        raise fastapi.HTTPException(status_code=422, detail="user_id must be a positive integer")

    try:
        async with idol.BasicSchoolIdolContext() as context:
            target = await system_user.get(context, payload.user_id)
            if target is None:
                raise fastapi.HTTPException(status_code=404, detail="User not found")

            before_level = target.level
            before_exp = target.exp
            applied_exp = core.validate_exp_multiplier(payload.base_exp, payload.multiplier, before_exp)
            transitions = await system_user.add_exp(context, target, applied_exp)
            after_level = target.level
            after_exp = target.exp
    except ValueError as exc:
        raise fastapi.HTTPException(status_code=422, detail=str(exc)) from None

    return {
        "user_id": payload.user_id,
        "base_exp": payload.base_exp,
        "multiplier": payload.multiplier,
        "applied_exp": applied_exp,
        "before_level": before_level,
        "after_level": after_level,
        "before_exp": before_exp,
        "after_exp": after_exp,
        "rank_transitions": [{"level": item.level, "from_exp": item.from_exp} for item in transitions],
    }

"""Machine-readable control-contract endpoint."""

from fastapi import APIRouter

from agentropolis.control_contract import build_control_contract_catalog

router = APIRouter(prefix="/meta/contract", tags=["contract"])


@router.get("")
async def read_contract_catalog():
    return build_control_contract_catalog()

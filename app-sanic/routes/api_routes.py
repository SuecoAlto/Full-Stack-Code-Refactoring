"""HTTP route handlers — the network layer.

Each handler parses the request, delegates to the service layer,
and returns a JSON response.  No database access or business
logic belongs here.
"""

from sanic import Blueprint
from sanic.request import Request
from sanic.response import json, HTTPResponse

from services import transaction_service
from utils.exceptions import AppError

api = Blueprint("api", url_prefix="")


@api.route("/ping")
async def ping(request: Request) -> HTTPResponse:
    """Healthcheck endpoint."""
    return json({"result": "pong"})


@api.route("/transactions", methods=["POST"])
async def create_transaction(request: Request) -> HTTPResponse:
    """Create a new transaction."""
    if request.content_type != "application/json":
        raise AppError("Unsupported Media Type", status_code=415)

    data = request.json or {}
    account_id = data.get("account_id")
    amount = data.get("amount")
    idempotency_key = data.get("idempotency_key")

    result = await transaction_service.create_transaction(
        account_id, amount, idempotency_key
    )
    return json(result, status=201)


@api.route("/transactions", methods=["GET"])
async def list_transactions(request: Request) -> HTTPResponse:
    """List all transactions, optionally filtered by account_id query param."""
    account_id = request.args.get("account_id")
    result = await transaction_service.list_transactions(account_id)
    return json(result)


@api.route("/transactions/<transaction_id>")
async def get_transaction(request: Request, transaction_id: str) -> HTTPResponse:
    """Fetch a single transaction by its ID."""
    result = await transaction_service.get_transaction(transaction_id)
    return json(result)


@api.route("/accounts/count")
async def get_account_count(request: Request) -> HTTPResponse:
    """Return the number of unique accounts and their IDs."""
    result = await transaction_service.get_account_count()
    return json(result)


@api.route("/accounts/<account_id>")
async def get_account(request: Request, account_id: str) -> HTTPResponse:
    """Fetch account data (balance) by account ID."""
    result = await transaction_service.get_account(account_id)
    return json(result)

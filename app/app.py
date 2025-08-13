import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, Optional, Tuple

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import ClientError
from flask import Flask, jsonify, request, make_response, g
import jwt  # PyJWT
from jwt import PyJWKClient

# ---------- Logging ----------
logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# ---------- Config / Constants ----------
TABLE_NAME = os.environ.get("TABLE_NAME")
if not TABLE_NAME:
    raise RuntimeError("Missing env var TABLE_NAME")

AWS_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

# Cognito
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")         # e.g. ap-southeast-1_XXXXXXXXX
COGNITO_REGION = os.environ.get("COGNITO_REGION", AWS_REGION)
COGNITO_AUDIENCE = os.environ.get("COGNITO_AUDIENCE")                 # app client id OR API audience (depending on token)
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
COGNITO_JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"
ACCEPTED_TOKEN_USE = os.environ.get("ACCEPTED_TOKEN_USE", "access")   # "access" or "id"
REQUIRED_GROUP = os.environ.get("REQUIRED_GROUP")                     # optional Cognito group gate

JSON_CT_RE = re.compile(r"^application/json(?:\s*;.*)?$", re.IGNORECASE)
DEFAULT_PAGE_SIZE = 20
MAX_TITLE_LEN = 140

# ---------- AWS ----------
ddb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    config=Config(retries={"max_attempts": 5, "mode": "standard"})
)
table = ddb.Table(TABLE_NAME)

# ---------- Flask ----------
app = Flask(__name__)

# ---------- Helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def corsify(resp):
    resp.headers["Access-Control-Allow-Origin"] = os.environ.get("CORS_ALLOW_ORIGIN", "*")
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Max-Age"] = "600"
    resp.headers["Vary"] = "Origin"

    # basic security
    resp.headers["Content-Type"] = resp.headers.get("Content-Type", "application/json")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-XSS-Protection"] = "0"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

def jresp(status: int, payload: Dict[str, Any]):
    r = make_response(jsonify(payload), status)
    return corsify(r)

def jerror(status: int, code: str, message: str, details: Optional[Dict[str, Any]] = None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jresp(status, body)

def parse_json_body() -> Tuple[Optional[Dict[str, Any]], Optional[Any]]:
    ct = request.headers.get("Content-Type", "")
    if not JSON_CT_RE.match(ct):
        return None, jerror(400, "INVALID_CONTENT_TYPE", "Content-Type must be application/json")
    try:
        return request.get_json(force=False, silent=False), None
    except Exception:
        return None, jerror(400, "INVALID_JSON", "Request body is not valid JSON")

def validate_due_date(value: Optional[str]) -> bool:
    if value is None:
        return True
    try:
        _ = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except Exception:
        return False

# ---------- Cognito JWT Verification (cached JWKS) ----------
_jwks_client: Optional[PyJWKClient] = None
_jwks_last_init = 0
_JWKS_TTL_SECONDS = int(os.environ.get("JWKS_TTL_SECONDS", "3600"))

def get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_last_init
    now = time.time()
    if _jwks_client is None or (now - _jwks_last_init) > _JWKS_TTL_SECONDS:
        # HEAD to test reachability; then init PyJWKClient
        requests.head(COGNITO_JWKS_URL, timeout=5)
        _jwks_client = PyJWKClient(COGNITO_JWKS_URL)
        _jwks_last_init = now
    return _jwks_client

def decode_and_verify(token: str) -> Dict[str, Any]:
    jwks_client = get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    options = {
        "require": ["exp", "iat"],
        "verify_aud": COGNITO_AUDIENCE is not None,
    }
    decoded = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=COGNITO_AUDIENCE,
        issuer=COGNITO_ISSUER,
        options=options,
    )
    # Optional: enforce token_use
    token_use = decoded.get("token_use")
    if ACCEPTED_TOKEN_USE and token_use != ACCEPTED_TOKEN_USE:
        raise jwt.InvalidTokenError(f"token_use must be '{ACCEPTED_TOKEN_USE}'")
    # Optional: enforce group membership
    if REQUIRED_GROUP:
        groups = decoded.get("cognito:groups", []) or decoded.get("groups", [])
        if REQUIRED_GROUP not in groups:
            raise jwt.InvalidTokenError("required group missing")
    return decoded

def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jerror(401, "UNAUTHORIZED", "Missing or invalid Authorization header")
        token = auth.split(" ", 1)[1].strip()
        try:
            claims = decode_and_verify(token)
            g.principal = {
                "sub": claims.get("sub"),
                "username": claims.get("username") or claims.get("cognito:username"),
                "scope": claims.get("scope"),
                "groups": claims.get("cognito:groups", []),
                "claims": claims,
            }
        except requests.RequestException:
            return jerror(502, "JWKS_FETCH_FAILED", "Unable to retrieve JWKS")
        except jwt.ExpiredSignatureError:
            return jerror(401, "TOKEN_EXPIRED", "Token expired")
        except jwt.InvalidTokenError as e:
            return jerror(401, "INVALID_TOKEN", str(e))
        return fn(*args, **kwargs)
    return wrapper

# ---------- Routes ----------
@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return corsify(make_response("", 204))
    return jresp(200, {"status": "ok", "time": now_iso()})

@app.route("/todos", methods=["POST", "OPTIONS"])
@require_auth
def create_todo():
    if request.method == "OPTIONS":
        return corsify(make_response("", 204))

    body, err = parse_json_body()
    if err:
        return err

    title = (body or {}).get("title")
    due_date = (body or {}).get("dueDate")

    if not isinstance(title, str) or not title.strip():
        return jerror(400, "MISSING_TITLE", "'title' is required")
    if len(title) > MAX_TITLE_LEN:
        return jerror(400, "TITLE_TOO_LONG", f"'title' must be ≤ {MAX_TITLE_LEN} characters")
    if not validate_due_date(due_date):
        return jerror(400, "INVALID_DUE_DATE", "'dueDate' must be RFC3339/ISO-8601")

    now = now_iso()
    item = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "dueDate": due_date,
        "createdAt": now,
        "updatedAt": now,
        # optional: owner context from Cognito
        "ownerSub": g.principal.get("sub"),
        "ownerUsername": g.principal.get("username"),
    }
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(id)")
        logger.info(json.dumps({"op": "create", "id": item["id"], "by": g.principal.get("sub")}))
        return jresp(201, item)
    except ClientError as ce:
        if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return jerror(409, "CONFLICT", "Item already exists (id collision)")
        logger.exception("AWS error")
        return jerror(502, "AWS_ERROR", "Upstream AWS error", {"aws": ce.response.get("Error")})

@app.route("/todos/<todo_id>", methods=["GET", "PUT", "DELETE", "OPTIONS"])
@require_auth
def todo_by_id(todo_id: str):
    if request.method == "OPTIONS":
        return corsify(make_response("", 204))

    if request.method == "GET":
        res = table.get_item(Key={"id": todo_id})
        item = res.get("Item")
        if not item:
            return jerror(404, "NOT_FOUND", "Todo not found")
        return jresp(200, item)

    if request.method == "PUT":
        body, err = parse_json_body()
        if err:
            return err
        body = body or {}

        update_expr_parts = []
        expr_attr_vals: Dict[str, Any] = {}

        if "title" in body:
            title = body["title"]
            if not isinstance(title, str) or not title.strip():
                return jerror(400, "INVALID_TITLE", "'title' must be a non-empty string")
            if len(title) > MAX_TITLE_LEN:
                return jerror(400, "TITLE_TOO_LONG", f"'title' must be ≤ {MAX_TITLE_LEN} characters")
            update_expr_parts.append("title = :title")
            expr_attr_vals[":title"] = title.strip()

        if "dueDate" in body:
            due_date = body["dueDate"]
            if not validate_due_date(due_date):
                return jerror(400, "INVALID_DUE_DATE", "'dueDate' must be RFC3339/ISO-8601")
            update_expr_parts.append("dueDate = :dueDate")
            expr_attr_vals[":dueDate"] = due_date

        if not update_expr_parts:
            return jerror(400, "NO_MUTABLE_FIELDS", "No updatable fields provided")

        update_expr_parts.append("updatedAt = :updatedAt")
        expr_attr_vals[":updatedAt"] = now_iso()

        try:
            res = table.update_item(
                Key={"id": todo_id},
                UpdateExpression="SET " + ", ".join(update_expr_parts),
                ExpressionAttributeValues=expr_attr_vals,
                ConditionExpression="attribute_exists(id)",
                ReturnValues="ALL_NEW",
            )
            logger.info(json.dumps({"op": "update", "id": todo_id, "by": g.principal.get("sub")}))
            return jresp(200, res.get("Attributes", {}))
        except ClientError as ce:
            if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return jerror(404, "NOT_FOUND", "Todo not found")
            logger.exception("AWS error")
            return jerror(502, "AWS_ERROR", "Upstream AWS error", {"aws": ce.response.get("Error")})

    if request.method == "DELETE":
        try:
            table.delete_item(
                Key={"id": todo_id},
                ConditionExpression="attribute_exists(id)"
            )
            logger.info(json.dumps({"op": "delete", "id": todo_id, "by": g.principal.get("sub")}))
            resp = make_response("", 204)
            return corsify(resp)
        except ClientError as ce:
            if ce.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return jerror(404, "NOT_FOUND", "Todo not found")
            logger.exception("AWS error")
            return jerror(502, "AWS_ERROR", "Upstream AWS error", {"aws": ce.response.get("Error")})

    return jerror(405, "METHOD_NOT_ALLOWED", "Unsupported method")

@app.route("/todos", methods=["GET", "OPTIONS"])
@require_auth
def list_todos():
    if request.method == "OPTIONS":
        return corsify(make_response("", 204))

    cursor = request.args.get("cursor")
    limit_raw = request.args.get("limit")
    limit = DEFAULT_PAGE_SIZE
    if limit_raw:
        try:
            limit = max(1, min(100, int(limit_raw)))
        except ValueError:
            return jerror(400, "INVALID_LIMIT", "'limit' must be an integer between 1 and 100")

    scan_kwargs: Dict[str, Any] = {"Limit": limit}
    if cursor:
        scan_kwargs["ExclusiveStartKey"] = {"id": cursor}

    res = table.scan(**scan_kwargs)
    items = res.get("Items", [])
    next_cursor = (res.get("LastEvaluatedKey") or {}).get("id")
    logger.info(json.dumps({"op": "list", "count": len(items), "nextCursor": next_cursor}))
    return jresp(200, {"items": items, "nextCursor": next_cursor})

# ---------- Error Handlers ----------
@app.errorhandler(404)
def not_found(_):
    return jerror(404, "ROUTE_NOT_FOUND", "Route not found")

@app.errorhandler(500)
def internal_error(_):
    return jerror(500, "INTERNAL_ERROR", "Unexpected server error")

# WSGI entrypoint
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))

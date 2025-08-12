import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# ---------- Logging ----------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------- Constants ----------
JSON_CT_RE = re.compile(r"^application/json(?:\s*;.*)?$", re.IGNORECASE)
DEFAULT_PAGE_SIZE = 20
MAX_TITLE_LEN = 140

# ---------- Headers ----------
CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "*"),
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Max-Age": "600",
    "Vary": "Origin",
}

SECURITY_HEADERS = {
    "Content-Type": "application/json",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",
    "Referrer-Policy": "no-referrer",
}

# ---------- DynamoDB init (reused across invocations) ----------
_TABLE_NAME = os.environ.get("TABLE_NAME")
if not _TABLE_NAME:
    raise RuntimeError("Missing required env var: TABLE_NAME")

_ddb = boto3.resource(
    "dynamodb",
    config=Config(retries={"max_attempts": 5, "mode": "standard"})
)
_table = _ddb.Table(_TABLE_NAME)

# ---------- Utilities ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def json_response(status: int, body: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    headers = {**CORS_HEADERS, **SECURITY_HEADERS}
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps(body, separators=(",", ":"), ensure_ascii=False),
    }

def error(status: int, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return json_response(status, payload)

def parse_json_body(event: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    headers = event.get("headers") or {}
    ct = headers.get("content-type") or headers.get("Content-Type") or ""
    if not JSON_CT_RE.match(ct):
        return None, error(400, "INVALID_CONTENT_TYPE", "Content-Type must be application/json")
    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64
            raw = base64.b64decode(raw).decode("utf-8")
        return json.loads(raw), None
    except Exception:
        return None, error(400, "INVALID_JSON", "Request body is not valid JSON")

def validate_due_date(value: Optional[str]) -> bool:
    if value is None:
        return True
    try:
        v = value.replace("Z", "+00:00")
        datetime.fromisoformat(v)
        return True
    except Exception:
        return False

def get_path_method(event: Dict[str, Any]) -> Tuple[str, str]:
    """
    Resolve router path & method across:
      - HTTP API v2 (preferred): routeKey = "METHOD /path", rawPath may contain stage (e.g., /prod)
      - REST API v1: event['path'] + event['httpMethod']
      - Custom domains/base-path mappings and named stages
    """
    rc_http = (event.get("requestContext") or {}).get("http") or {}

    # 1) Prefer routeKey when present (HTTP API v2)
    route_key = (event.get("requestContext") or {}).get("routeKey")
    if isinstance(route_key, str) and " " in route_key:
        m, p = route_key.split(" ", 1)
        return p or "/", (m or "").upper()

    # 2) REST API v1 fallback
    if "path" in event and "httpMethod" in event:
        return (event.get("path") or "/") or "/", (event.get("httpMethod") or "").upper()

    # 3) HTTP API v2 rawPath minus stage prefix
    path = (event.get("rawPath") or "/") or "/"
    stage = (event.get("requestContext") or {}).get("stage")
    # Remove "/{stage}" or "/{stage}/" prefix
    if stage and path.startswith(f"/{stage}/"):
        path = path[len(stage) + 1:]
    elif stage and path == f"/{stage}":
        path = "/"

    method = (rc_http.get("method") or "").upper()
    return path or "/", method

def last_eval_cursor(res: Dict[str, Any]) -> Optional[str]:
    lek = res.get("LastEvaluatedKey") or {}
    return lek.get("id")

# ---------- Handlers ----------
def handle_health() -> Dict[str, Any]:
    return json_response(200, {"status": "ok", "time": now_iso()})

def handle_create_todo(event: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    body, err = parse_json_body(event)
    if err:
        return err

    title = (body or {}).get("title")
    due_date = (body or {}).get("dueDate")

    if not isinstance(title, str) or not title.strip():
        return error(400, "MISSING_TITLE", "'title' is required")
    if len(title) > MAX_TITLE_LEN:
        return error(400, "TITLE_TOO_LONG", f"'title' must be ≤ {MAX_TITLE_LEN} characters")
    if not validate_due_date(due_date):
        return error(400, "INVALID_DUE_DATE", "'dueDate' must be RFC3339/ISO-8601")

    now = now_iso()
    item = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "dueDate": due_date,
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        _table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(id)"
        )
        logger.info(json.dumps({"requestId": request_id, "op": "create", "id": item["id"]}))
        return json_response(201, item)
    except ClientError as ce:
        if ce.response["Error"]["Code"] in ("ConditionalCheckFailedException",):
            return error(409, "CONFLICT", "Item already exists (id collision)")
        raise

def handle_get_todo(todo_id: str, request_id: str) -> Dict[str, Any]:
    res = _table.get_item(Key={"id": todo_id})
    item = res.get("Item")
    if not item:
        return error(404, "NOT_FOUND", "Todo not found")
    logger.info(json.dumps({"requestId": request_id, "op": "read", "id": todo_id}))
    return json_response(200, item)

def handle_list_todos(event: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    qs = event.get("queryStringParameters") or {}
    cursor = qs.get("cursor")
    limit_raw = qs.get("limit")
    limit = DEFAULT_PAGE_SIZE
    if limit_raw:
        try:
            limit = max(1, min(100, int(limit_raw)))
        except ValueError:
            return error(400, "INVALID_LIMIT", "'limit' must be an integer between 1 and 100")

    scan_kwargs: Dict[str, Any] = {"Limit": limit}
    if cursor:
        scan_kwargs["ExclusiveStartKey"] = {"id": cursor}

    res = _table.scan(**scan_kwargs)
    items = res.get("Items", [])
    next_cursor = last_eval_cursor(res)

    logger.info(json.dumps({"requestId": request_id, "op": "list", "count": len(items), "nextCursor": next_cursor}))
    return json_response(200, {"items": items, "nextCursor": next_cursor})

def handle_update_todo(event: Dict[str, Any], todo_id: str, request_id: str) -> Dict[str, Any]:
    body, err = parse_json_body(event)
    if err:
        return err
    body = body or {}

    update_expr_parts = []
    expr_attr_vals: Dict[str, Any] = {}

    if "title" in body:
        title = body["title"]
        if not isinstance(title, str) or not title.strip():
            return error(400, "INVALID_TITLE", "'title' must be a non-empty string")
        if len(title) > MAX_TITLE_LEN:
            return error(400, "TITLE_TOO_LONG", f"'title' must be ≤ {MAX_TITLE_LEN} characters")
        update_expr_parts.append("title = :title")
        expr_attr_vals[":title"] = title.strip()

    if "dueDate" in body:
        due_date = body["dueDate"]
        if not validate_due_date(due_date):
            return error(400, "INVALID_DUE_DATE", "'dueDate' must be RFC3339/ISO-8601")
        update_expr_parts.append("dueDate = :dueDate")
        expr_attr_vals[":dueDate"] = due_date

    if not update_expr_parts:
        return error(400, "NO_MUTABLE_FIELDS", "No updatable fields provided")

    update_expr_parts.append("updatedAt = :updatedAt")
    expr_attr_vals[":updatedAt"] = now_iso()

    try:
        res = _table.update_item(
            Key={"id": todo_id},
            UpdateExpression="SET " + ", ".join(update_expr_parts),
            ExpressionAttributeValues=expr_attr_vals,
            ConditionExpression="attribute_exists(id)",
            ReturnValues="ALL_NEW",
        )
        logger.info(json.dumps({"requestId": request_id, "op": "update", "id": todo_id}))
        return json_response(200, res.get("Attributes", {}))
    except ClientError as ce:
        if ce.response["Error"]["Code"] in ("ConditionalCheckFailedException",):
            return error(404, "NOT_FOUND", "Todo not found")
        raise

def handle_delete_todo(todo_id: str, request_id: str) -> Dict[str, Any]:
    try:
        _table.delete_item(
            Key={"id": todo_id},
            ConditionExpression="attribute_exists(id)"
        )
        logger.info(json.dumps({"requestId": request_id, "op": "delete", "id": todo_id}))
        return {"statusCode": 204, "headers": {**CORS_HEADERS, **SECURITY_HEADERS}, "body": ""}
    except ClientError as ce:
        if ce.response["Error"]["Code"] in ("ConditionalCheckFailedException",):
            return error(404, "NOT_FOUND", "Todo not found")
        raise

# ---------- Main entry ----------
def lambda_handler(event, context):
    req_id = getattr(context, "aws_request_id", None) or str(uuid.uuid4())
    path, method = get_path_method(event)

    logger.info(json.dumps({
        "requestId": req_id,
        "path": path,
        "method": method,
        "stage": (event.get("requestContext") or {}).get("stage") or os.environ.get("STAGE", "prod")
    }))

    # Preflight
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": {**CORS_HEADERS, **SECURITY_HEADERS}, "body": ""}

    # Health
    if path == "/health" and method == "GET":
        return handle_health()

    try:
        # Routes
        if path == "/todos" and method == "POST":
            return handle_create_todo(event, req_id)

        if path == "/todos" and method == "GET":
            return handle_list_todos(event, req_id)

        if path.startswith("/todos/"):
            todo_id = path.rsplit("/", 1)[-1]
            if method == "GET":
                return handle_get_todo(todo_id, req_id)
            if method == "PUT":
                return handle_update_todo(event, todo_id, req_id)
            if method == "DELETE":
                return handle_delete_todo(todo_id, req_id)

        return error(404, "ROUTE_NOT_FOUND", "Route not found")
    except ClientError as ce:
        logger.error(json.dumps({"requestId": req_id, "awsError": ce.response.get("Error")}))
        return error(502, "AWS_ERROR", "Upstream AWS error", {"aws": ce.response.get("Error")})
    except Exception:
        logger.exception("Unhandled error")
        return error(500, "INTERNAL_ERROR", "Unexpected server error")

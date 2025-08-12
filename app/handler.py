import json
import os
import logging
import uuid
from datetime import datetime

import boto3

ddb = boto3.resource('dynamodb')
table = ddb.Table(os.environ['TABLE_NAME'])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
}

def response(status, body):
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps(body)
    }

def lambda_handler(event, context):
    req_id = context.aws_request_id if context else str(uuid.uuid4())
    path = event.get('rawPath', '')
    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    logger.info(json.dumps({
        "requestId": req_id,
        "path": path,
        "method": method,
        "stage": os.environ.get('STAGE', 'prod')
    }))

    if method == 'OPTIONS':
        return response(204, {})

    if path == '/health' and method == 'GET':
        return response(200, {"status": "ok"})

    try:
        if path == '/todos' and method == 'POST':
            if event.get('headers', {}).get('content-type', '').lower() != 'application/json':
                return response(400, {"error": "INVALID_CONTENT_TYPE", "message": "Content-Type must be application/json"})
            body = json.loads(event.get('body', '{}'))
            title = body.get('title')
            if not title:
                return response(400, {"error": "MISSING_TITLE", "message": "'title' is required"})
            due_date = body.get('dueDate')
            item = {
                "id": str(uuid.uuid4()),
                "title": title,
                "dueDate": due_date,
                "createdAt": datetime.utcnow().isoformat(),
                "updatedAt": datetime.utcnow().isoformat()
            }
            table.put_item(Item=item)
            return response(201, item)

        if path.startswith('/todos/') and method == 'GET':
            todo_id = path.split('/')[-1]
            res = table.get_item(Key={"id": todo_id})
            item = res.get('Item')
            if not item:
                return response(404, {"error": "NOT_FOUND", "message": "Todo not found"})
            return response(200, item)

        if path == '/todos' and method == 'GET':
            cursor = event.get('queryStringParameters', {}).get('cursor') if event.get('queryStringParameters') else None
            scan_kwargs = {"Limit": 20}
            if cursor:
                scan_kwargs["ExclusiveStartKey"] = {"id": cursor}
            res = table.scan(**scan_kwargs)
            items = res.get('Items', [])
            next_cursor = res.get('LastEvaluatedKey', {}).get('id')
            return response(200, {"items": items, "nextCursor": next_cursor})

        if path.startswith('/todos/') and method == 'PUT':
            if event.get('headers', {}).get('content-type', '').lower() != 'application/json':
                return response(400, {"error": "INVALID_CONTENT_TYPE", "message": "Content-Type must be application/json"})
            todo_id = path.split('/')[-1]
            body = json.loads(event.get('body', '{}'))
            update_expr = []
            expr_attr_vals = {}
            for k in ['title', 'dueDate']:
                if k in body:
                    update_expr.append(f"{k} = :{k}")
                    expr_attr_vals[f":{k}"] = body[k]
            if not update_expr:
                return response(400, {"error": "NO_MUTABLE_FIELDS", "message": "No updatable fields provided"})
            update_expr.append("updatedAt = :updatedAt")
            expr_attr_vals[":updatedAt"] = datetime.utcnow().isoformat()
            try:
                res = table.update_item(
                    Key={"id": todo_id},
                    UpdateExpression="SET " + ", ".join(update_expr),
                    ExpressionAttributeValues=expr_attr_vals,
                    ReturnValues="ALL_NEW"
                )
                return response(200, res.get('Attributes'))
            except Exception as e:
                return response(404, {"error": "NOT_FOUND", "message": str(e)})

        if path.startswith('/todos/') and method == 'DELETE':
            todo_id = path.split('/')[-1]
            table.delete_item(Key={"id": todo_id})
            return response(204, {})

        return response(404, {"error": "NOT_FOUND", "message": "Route not found"})
    except Exception as e:
        logger.error(json.dumps({"error": str(e), "requestId": req_id}))
        return response(500, {"error": "INTERNAL_ERROR", "message": str(e)})

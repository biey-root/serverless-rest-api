resource "aws_apigatewayv2_api" "todos" {
  name          = "${var.project}-todos-api-${var.stage}"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type"]
  }
}

# Allow API Gateway to invoke the Lambda function
resource "aws_lambda_permission" "api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.todos.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id           = aws_apigatewayv2_api.todos.id
  integration_type = "AWS_PROXY"
  integration_uri  = var.lambda_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "todos" {
  for_each = {
    "POST /todos"      = "POST /todos"
    "GET /todos/{id}"  = "GET /todos/{id}"
    "GET /todos"       = "GET /todos"
    "PUT /todos/{id}"  = "PUT /todos/{id}"
    "DELETE /todos/{id}" = "DELETE /todos/{id}"
    "GET /health"      = "GET /health"
  }
  api_id    = aws_apigatewayv2_api.todos.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  api_key_required = each.value != "GET /health" ? true : false
}

# API Key for API Gateway
resource "aws_api_gateway_api_key" "this" {
  name        = "${var.project}-api-key"
  description = "API key for ${var.project}"
  enabled     = true
}

# Usage Plan for API Key
resource "aws_api_gateway_usage_plan" "this" {
  name = "${var.project}-usage-plan"
  api_stages {
    api_id = aws_apigatewayv2_api.todos.id
    stage  = aws_apigatewayv2_stage.prod.name
  }
  throttle_settings {
    burst_limit = 100
    rate_limit  = 50
  }
}

# Usage Plan Key association
resource "aws_api_gateway_usage_plan_key" "this" {
  key_id        = aws_api_gateway_api_key.this.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.this.id
}
resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.todos.id
  name        = var.stage
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_logs.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      ip                = "$context.identity.sourceIp"
      requestTime       = "$context.requestTime"
      httpMethod        = "$context.httpMethod"
      routeKey          = "$context.routeKey"
      status           = "$context.status"
      protocol         = "$context.protocol"
      responseLength   = "$context.responseLength"
      integrationError = "$context.integration.error"
      integrationStatus = "$context.integration.status"
      integrationLatency = "$context.integration.latency"
    })
  }
}

# Log group for API Gateway access logs
resource "aws_cloudwatch_log_group" "api_logs" {
  name              = "/aws/apigateway/${var.project}-todos-api-${var.stage}/access-logs"
  retention_in_days = 7
}

variable "project" { type = string }
variable "stage" { type = string }
variable "lambda_arn" { type = string }
variable "lambda_function_name" { type = string }

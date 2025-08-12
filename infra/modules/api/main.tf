resource "aws_apigatewayv2_api" "todos" {
  name          = "${var.project}-todos-api-${var.stage}"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type"]
  }
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
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.todos.id
  name        = var.stage
  auto_deploy = true
}

output "api_base_url" {
  value = aws_apigatewayv2_stage.prod.invoke_url
}
output "api_id" {
  value = aws_apigatewayv2_api.todos.id
}

variable "project" { type = string }
variable "stage" { type = string }
variable "lambda_arn" { type = string }

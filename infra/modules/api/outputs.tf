output "api_base_url" {
  value = aws_apigatewayv2_stage.prod.invoke_url
}
output "api_key_value" {
  value = aws_api_gateway_api_key.this.value
  sensitive = true
}
output "api_id" {
  value = aws_apigatewayv2_api.todos.id
}

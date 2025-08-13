output "user_pool_id" {
  value = aws_cognito_user_pool.main.id
}
output "user_pool_client_id" {
  value = aws_cognito_user_pool_client.main.id
}
output "user_pool_provider_url" {
  value = aws_cognito_user_pool.main.endpoint
}

output "app_client_id" {
  value = aws_cognito_user_pool_client.main.id
}
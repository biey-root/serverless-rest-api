output "lambda_arn" {
  value = aws_lambda_function.todos.arn
}
output "lambda_function_name" {
  value = aws_lambda_function.todos.function_name
}

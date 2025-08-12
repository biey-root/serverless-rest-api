output "cw_log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}
output "api_5xx_alarm_name" {
  value = aws_cloudwatch_metric_alarm.api_5xx.alarm_name
}

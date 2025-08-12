resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project}-todos-${var.stage}"
  retention_in_days = 7
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.project}-todos-api-5xx-${var.stage}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = 60
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "API Gateway 5XX errors > 0"
  dimensions = {
    ApiId = var.api_id
  }
}

variable "project" { type = string }
variable "stage" { type = string }
variable "api_id" { type = string }

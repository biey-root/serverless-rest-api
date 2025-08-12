resource "aws_lambda_function" "todos" {
  function_name = "${var.project}-todos-${var.stage}"
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  role          = aws_iam_role.lambda_exec.arn
  filename      = var.lambda_package
  source_code_hash = filebase64sha256(var.lambda_package)
  environment {
    variables = {
      TABLE_NAME = var.table_name
      STAGE      = var.stage
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name = "${var.project}-todos-lambda-exec-${var.stage}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "lambda_policy" {
  name   = "${var.project}-todos-lambda-policy-${var.stage}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_policy.json
}

data "aws_iam_policy_document" "lambda_policy" {
  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Scan"
    ]
    resources = [var.ddb_arn]
  }
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

variable "project" { type = string }
variable "stage" { type = string }
variable "table_name" { type = string }
variable "ddb_arn" { type = string }
variable "lambda_package" { type = string }

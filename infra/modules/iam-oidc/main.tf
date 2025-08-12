resource "aws_iam_role" "github_oidc" {
  name = "${var.project}-github-oidc-${var.stage}"
  assume_role_policy = data.aws_iam_policy_document.github_oidc_assume.json
}

data "aws_iam_policy_document" "github_oidc_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "github_oidc_policy" {
  name   = "${var.project}-github-oidc-policy-${var.stage}"
  role   = aws_iam_role.github_oidc.id
  policy = data.aws_iam_policy_document.github_oidc_policy.json
}

data "aws_iam_policy_document" "github_oidc_policy" {
  statement {
    actions = [
      "sts:AssumeRoleWithWebIdentity",
      "lambda:UpdateFunctionCode",
      "lambda:GetFunction*",
      "lambda:UpdateFunctionConfiguration",
      "apigateway:GET",
      "apigateway:POST",
      "apigateway:PATCH",
      "cloudwatch:PutMetricData",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "dynamodb:DescribeTable",
      "ssm:GetParameter"
    ]
    resources = ["*"]
  }
}

variable "project" { type = string }
variable "stage" { type = string }
variable "github_repo" { type = string }

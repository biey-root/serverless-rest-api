terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.50"
    }
  }
}


module "ddb" {
  source = "./modules/ddb"
  project = var.project
  stage = var.stage
}

module "lambda" {
  source = "./modules/lambda"
  project = var.project
  stage = var.stage
  table_name = module.ddb.table_name
}

module "api" {
  source = "./modules/api"
  project = var.project
  stage = var.stage
  lambda_arn = module.lambda.lambda_arn
}

module "observability" {
  source = "./modules/observability"
  project = var.project
  stage = var.stage
  api_id = module.api.api_id
}

module "iam_oidc" {
  source = "./modules/iam-oidc"
  project = var.project
  stage = var.stage
}

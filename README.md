# Serverless Todos API

A production-lean serverless REST API on AWS using Lambda, API Gateway, and DynamoDB. IaC via Terraform, CI/CD via GitHub Actions OIDC.

## Quickstart

```sh
# 1. Clone repo and set up AWS OIDC role (see below)
# 2. Set repo variables: ROLE_ARN, AWS_REGION (default: ap-southeast-1)
# 3. Deploy:
cd infra
terraform init
terraform apply -auto-approve
# 4. Package and deploy Lambda:
cd ../app
zip -r ../lambda.zip . -x "*.venv*" "__pycache__/*"
aws lambda update-function-code --function-name <lambda_name> --zip-file fileb://../lambda.zip --region <region>
```

## OIDC Role Setup
- Create AWS IAM role with OIDC trust for GitHub Actions (see `infra/modules/iam-oidc/main.tf`).
- Attach least-privilege policy (see instructions).
- Set `ROLE_ARN` and `AWS_REGION` in repo variables.

## API Usage
- Health: `curl $API/health`
- Create: `curl -s -X POST "$API/todos" -H 'content-type: application/json' -d '{"title":"Test"}'`
- List: `curl -s "$API/todos"`

## Cost & Teardown
- PAY_PER_REQUEST DynamoDB, minimal log retention (7d), small Lambda package.
- To destroy: `cd infra && terraform destroy -auto-approve`

## Acceptance
- `terraform apply` creates API, Lambda, DynamoDB, outputs `api_base_url`.
- `curl $api_base_url/health` returns 200 {"status":"ok"}.
- CRUD endpoints work end-to-end.
- GitHub Actions runs and shows API URL in summary.
- No plaintext secrets in repo; least-privilege IAM validated.

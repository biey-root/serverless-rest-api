
# Serverless Todos API

A production-lean serverless REST API on AWS using Lambda, API Gateway (secured with Cognito JWT authorizer), and DynamoDB. IaC via Terraform, CI/CD via GitHub Actions OIDC.

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

## Cognito JWT Authorizer
- Cognito User Pool and Client are provisioned automatically.
- All API routes except `/health` require a valid JWT in the `Authorization` header.
- To sign up/login and get a JWT:
	1. Use AWS CLI or AWS Console to create a user in the Cognito User Pool (see Terraform output for pool/client IDs).
	2. Authenticate and obtain a JWT token.
	3. Call API endpoints with:
		 ```sh
		 curl -s -X POST "$API/todos" -H 'content-type: application/json' -H "Authorization: Bearer <JWT>" -d '{"title":"Test"}'
		 curl -s "$API/todos" -H "Authorization: Bearer <JWT>"
		 ```

## API Usage
- Health: `curl $API/health`
- Create: `curl -s -X POST "$API/todos" -H 'content-type: application/json' -H "Authorization: Bearer <JWT>" -d '{"title":"Test"}'`
- List: `curl -s "$API/todos" -H "Authorization: Bearer <JWT>"`

## Cost & Teardown
- PAY_PER_REQUEST DynamoDB, minimal log retention (7d), small Lambda package.
- Cognito Free Tier covers 50,000 monthly active users.
- To destroy: `cd infra && terraform destroy -auto-approve`

## Acceptance
- `terraform apply` creates API, Lambda, DynamoDB, Cognito, and outputs `api_base_url`.
- `curl $api_base_url/health` returns 200 {"status":"ok"}.
- CRUD endpoints work end-to-end (with JWT).
- GitHub Actions runs and shows API URL in summary.
- No plaintext secrets in repo; least-privilege IAM validated.

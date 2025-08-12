---
applyTo: '**'
---
You are a senior DevOps engineer. Generate a complete, production-lean Serverless REST API on AWS using these requirements. Produce runnable code and infra in one repo with clear docs.

# High-level
- Stack: AWS API Gateway (HTTP API) + AWS Lambda (Python 3.12) + DynamoDB (PAY_PER_REQUEST).
- IaC: Terraform (>=1.6, aws provider >=5.50). No manual console steps.
- CI/CD: GitHub Actions with OIDC to AWS (no long-lived keys). One workflow per push to main: terraform plan/apply and Lambda package deploy.
- Secrets: Parameter Store (SecureString) or plain env for non-sensitive; no secrets in repo.
- Region default: ap-southeast-1 (configurable).
- Cost guardrails: small package size, single table PAY_PER_REQUEST, minimal CW logs retention (7 days).

# API contract (example "todos" service)
- Endpoints (HTTP API with CORS):
  - POST /todos             -> create item {title, dueDate?} -> returns {id, ...}
  - GET /todos/{id}         -> get by id
  - GET /todos              -> list (last 20, keyset pagination via query ?cursor=)
  - PUT /todos/{id}         -> update mutable fields
  - DELETE /todos/{id}      -> delete
- Validation: reject invalid JSON; return 400 with clear error body.
- Error model: { "error": "CODE", "message": "..." } with appropriate status codes.

# Repository layout
- /app/handler.py                 # Lambda entrypoint (single file OK)
- /app/requirements.txt           # minimal deps (boto3 provided by AWS -> do NOT pin boto3)
- /infra/{main.tf, variables.tf, outputs.tf, providers.tf}
- /infra/modules/{api, lambda, ddb, observability, iam-oidc}
- /ci/serverless-deploy.yml       # GitHub Actions workflow
- /tests/http_smoke.sh            # curl-based smoke script
- /README.md

# Lambda implementation
- Runtime: python3.12, handler function: handler.lambda_handler
- Lightweight router inside handler (no heavy frameworks).
- JSON parsing with robust validation; strict Content-Type check.
- Use environment variables:
  - TABLE_NAME
  - STAGE (e.g., prod)
- Implement id generation via uuid4.
- Implement conditional updates (optimistic concurrency via updatedAt if feasible).
- Structured logging (JSON) including requestId, path, method, status; send to CloudWatch.
- Return proper CORS headers.

# DynamoDB
- Single table: todos (pk: "pk", sk: "sk") or simple pk "id" if you choose. PAY_PER_REQUEST.
- GSIs (optional) for list-by-createdAt descending.
- TTL attribute "ttl" (optional).

# API Gateway (HTTP API)
- Single Lambda proxy integration with default stage "prod".
- CORS enabled for "*", methods GET,POST,PUT,DELETE (configurable).
- Execution logging enabled.

# Terraform specifics
- Root variables: project (default "srvless-todos"), region, stage (default "prod").
- Modules:
  - ddb: create table; outputs table_name.
  - lambda: package via archive_file, role with least privilege, env vars set.
  - api: aws_apigatewayv2_http_api + integration + routes + stage.
  - observability: CW log groups and basic metrics/alarm example (5XX count on API).
  - iam-oidc: role assumable by GitHub OIDC for CI; least-privilege: plan/apply, lambda update, apigw deploy, ddb CRUD (if you choose to seed).
- Outputs: api_base_url, table_name.

# GitHub Actions (OIDC)
- Workflow: on push to main.
- Permissions: id-token: write, contents: read.
- Steps:
  1) Checkout.
  2) Configure AWS creds via aws-actions/configure-aws-credentials@v4 using ROLE_ARN (from repo var) and region.
  3) Cache terraform plugin dir.
  4) Terraform init/plan/apply in /infra with -auto-approve (safe for demo).
  5) Package Lambda with zip (exclude venv), update function code if changed.
  6) Output API URL as job summary.
- Repo Variables: ROLE_ARN, AWS_REGION (default ap-southeast-1).
- No static AWS keys.

# IAM least privilege (attach to OIDC role)
- Allow: sts:AssumeRoleWithWebIdentity,
  lambda:UpdateFunctionCode, lambda:GetFunction*, lambda:UpdateFunctionConfiguration,
  apigateway:GET/POST/PATCH on managed resources needed for HTTP API deploy,
  cloudwatch:PutMetricData, logs:CreateLogGroup/Stream/PutLogEvents,
  dynamodb:DescribeTable (seed optional),
  ssm:GetParameter on specific path if used.
- Deny wildcard admin; scope to ARNs where feasible.

# Observability
- CloudWatch Log Group for Lambda with 7-day retention.
- Basic API 5XX alarm -> SNS topic (subscription optional).
- JSON logging format in Lambda.

# README
- One-command quickstart.
- How to set up OIDC role and repo vars.
- curl examples:
  - POST: curl -s -X POST "$API/todos" -H 'content-type: application/json' -d '{"title":"Test"}'
  - GET list: curl -s "$API/todos"
- Cost notes and teardown.

# Acceptance criteria
- `terraform apply` creates API, Lambda, DynamoDB, and outputs `api_base_url`.
- `curl $api_base_url/health` (add a /health route) returns 200 {"status":"ok"}.
- CRUD endpoints work end-to-end.
- GitHub Actions runs successfully on first push and shows API URL in summary.
- No plaintext secrets in repo; least-privilege IAM validated.

# Deliverables
- All code files, Terraform modules, workflow YAML, and README.
- Clear comments and TODOs where environment-specific values go.
- Prefer simplicity over frameworks; keep zip < 5MB.

Generate the project now.
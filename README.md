# AWS AIOps Lens Advisor

A small production-shaped chatbot demo for adopting AWS monitoring, observability, and security patterns across approved AWS service packs.

The app is intentionally simple on the surface:

- A browser chat UI for cloud engineers and platform teams.
- A FastAPI backend with approved service-pack content.
- Optional Amazon Bedrock integration for natural-language polish.
- AI Governance Gateway for prompt-injection, secrets, PII, and destructive-intent checks.
- Docker packaging for ECS/Fargate.
- Terraform starter infrastructure with ALB, ECS service, CloudWatch logs, dashboard, and alarms.
- CloudWatch Embedded Metric Format telemetry for chatbot observability, explainability, token usage, and estimated cost.

## Architecture

```text
User -> Chat UI -> FastAPI -> Service Pack Catalog
                \-> AI Governance Gateway
                         \-> Optional Amazon Bedrock
                         \-> EMF telemetry + explainability events
                         \-> CloudWatch-ready dashboard/alarm recommendations
```

The core production principle is that the LLM advises from curated service packs. It should not freely invent dashboards, alarms, or security controls.

## AI Governance Gateway

Every chat request is evaluated before the advisor or Bedrock can process it. The gateway produces a policy decision, risk score, severity, categories, findings, and a sanitized prompt for safe routing.

Current controls:

- Prompt-injection and prompt-disclosure detection
- Secret detection for AWS keys, GitHub tokens, private-key markers, API keys, passwords, and token phrases
- PII detection for email addresses, phone-like values, and long account/card-like numbers
- Destructive or unauthorized operational-intent detection
- Block decisions for prompt-injection, secrets, and high-risk combinations
- Review decisions for medium-risk prompts that can still be safely routed after redaction

Blocked requests return a safe response from the application, are not sent to Bedrock, and are still captured as telemetry evidence.

## Chatbot Observability

Every chat request emits one structured CloudWatch Embedded Metric Format event to stdout. On ECS/Fargate, the awslogs driver sends that event to CloudWatch Logs and CloudWatch extracts metrics automatically.

Captured signals:

- Request volume, success count, and error count
- End-to-end latency
- Selected AWS service pack and intent
- Response source: service pack or Bedrock grounded
- Confidence score, fallback count, and low-confidence count
- Input tokens, output tokens, total tokens, and estimated request cost
- Explainability reasons for service selection and intent selection
- Request id and message hash for evidence without storing raw prompts
- Percentile latency, SLO status, error-budget remaining, and alert summaries
- Governance risk score, blocked count, prompt-injection count, PII count, and secret count
- Durable event history through local SQLite or DynamoDB in ECS/Fargate production

The app also exposes telemetry APIs for the dashboard:

```text
GET /api/observability/summary
GET /api/observability/recent
GET /api/observability/daily
GET /api/observability/alerts
GET /api/observability/events/{request_id}
```

The separate dashboard is available at:

```text
GET /dashboard
```

The observability APIs accept `service_id` so the dashboard can show only ECS, only VPC, only S3, or any other selected service pack. The daily endpoint also accepts `days` for day-wise graphs.

Local development stores events in `app/data/telemetry_events.db`, which is ignored by Git. ECS/Fargate production uses a Terraform-managed DynamoDB table by default so dashboard history survives task restarts.

Terraform adds CloudWatch dashboard widgets for chatbot request volume, errors, latency, token usage, estimated cost, requests by service, requests by intent, governance findings, and explainability evidence. MCP can be added later as a natural-language query layer over CloudWatch Logs Insights, CloudWatch Metrics, and S3/Athena evidence; it should not replace the telemetry pipeline.

## AWS Resource Observability

The deployed ECS/Fargate stack also captures the main AWS resources used to run the chatbot:

- ECS/Fargate: CPU, memory, desired/running task count, task health
- Application Load Balancer: request path latency, target 5xx, healthy/unhealthy hosts
- NAT Gateway: egress bytes, ingress bytes, dropped packets, port allocation errors
- VPC Flow Logs: accepted/rejected network traffic evidence for the chatbot VPC
- CloudWatch Logs: application log ingestion and VPC Flow Log ingestion volume
- ECR: repository pull count and scan-on-push repository configuration
- Bedrock: token and estimated cost metrics from the chatbot app when Bedrock mode is enabled

The dashboard intentionally separates these layers:

- Agent layer: request volume, success rate, token usage, explainability, and response quality signals
- Governance layer: policy action, prompt-injection attempts, sensitive-data detection, blocked requests, and risk score
- Resource layer: ECS, ALB, NAT, VPC, logs, ECR, and optional Bedrock runtime signals

## Implemented Service Packs

The chatbot now includes these approved service packs:

- `ecs-fargate`
- `lambda`
- `s3`
- `api-gateway`
- `load-balancer`
- `vpc`
- `bedrock`
- `sagemaker`

The first production deployment still runs on ECS/Fargate, but the advisor can answer across the services above.

## ECS/Fargate Pack

- ECS cluster and service health
- Fargate CPU, memory, desired/running task drift
- ALB target health, latency, and 5xx errors
- CloudWatch Logs Insights starter queries
- Application Signals, X-Ray/OpenTelemetry guidance
- Security Hub, AWS Config, GuardDuty, IAM, and ECR scanning controls
- Adoption plan and evidence framework aligned to observability, explainability, quality, ethics and safety, and continuous validation

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080`.

Without AWS credentials the app still works using deterministic service-pack responses.

## Optional Bedrock

Set these environment variables to enable Bedrock response generation:

```powershell
$env:AWS_REGION="ap-south-1"
$env:BEDROCK_MODEL_ID="apac.amazon.nova-lite-v1:0"
$env:USE_BEDROCK="true"
```

The fallback remains the approved local service-pack answer if Bedrock is unavailable. The API exposes runtime mode at:

```text
GET /api/runtime
```

For AWS accounts in APAC regions, use an inference profile ID such as `apac.amazon.nova-lite-v1:0` or `apac.anthropic.claude-3-5-sonnet-20240620-v1:0`. Anthropic models require the Anthropic use-case form to be submitted in the AWS account before invocation. If Bedrock quota or model access blocks invocation, the app keeps serving deterministic service-pack answers and reports the fallback source in chat responses.

## Docker

```powershell
docker build -t aws-aiops-lens-advisor:local .
docker run --rm -p 8080:8080 aws-aiops-lens-advisor:local
```

## ECS/Fargate Deployment

The next stage is deployable through Terraform and a PowerShell helper. Terraform creates:

- ECR repository with scan-on-push
- Dedicated VPC by default
- Public ALB subnets
- Private ECS/Fargate task subnets
- Optional NAT gateway for private task egress
- Optional VPC Flow Logs for network observability and security evidence
- DynamoDB table for durable chatbot telemetry history
- ECS cluster, task definition, service, ALB, target group
- CloudWatch log group, alarms, and dashboard
- Chatbot observability metrics, explainability log views, token/cost widgets, and governance alarms
- Resource observability widgets and alarms for ALB, ECS, NAT, VPC Flow Logs, CloudWatch Logs, and ECR

Run the deployment helper after Docker Desktop is running:

```powershell
.\scripts\deploy.ps1 -Profile bedrock-governance -Region ap-south-1 -ImageTag latest -AutoApprove
```

Manual deployment is also supported.

```powershell
cd infra/terraform
terraform init
terraform apply -target=aws_ecr_repository.app `
  -var="name=aiops-lens-advisor" `
  -var="aws_region=ap-south-1" `
  -var="aws_profile=bedrock-governance"

$repo = terraform output -raw ecr_repository_url
aws ecr get-login-password --profile bedrock-governance --region ap-south-1 | docker login --username AWS --password-stdin ($repo -split "/")[0]
docker build -t aiops-lens-advisor:latest ../..
docker tag aiops-lens-advisor:latest "${repo}:latest"
docker push "${repo}:latest"

terraform plan -out=tfplan `
  -var="name=aiops-lens-advisor" `
  -var="aws_region=ap-south-1" `
  -var="aws_profile=bedrock-governance" `
  -var="image_tag=latest"
terraform apply tfplan
```

By default, the ALB is placed in public subnets and ECS/Fargate tasks are placed in private subnets in a Terraform-managed VPC. NAT gateway is enabled by default so tasks can pull from ECR and write to CloudWatch Logs. For lower cost environments with existing networking, set `create_vpc=false` and provide `vpc_id`, `public_subnet_ids`, and `private_subnet_ids`.

## API

- `GET /health`
- `GET /api/runtime`
- `GET /api/service-packs`
- `GET /api/service-packs/ecs-fargate`
- `GET /api/observability/summary`
- `GET /api/observability/recent`
- `GET /api/observability/daily`
- `GET /api/observability/alerts`
- `GET /api/observability/events/{request_id}`
- `GET /dashboard`
- `POST /api/chat`

Example:

```json
{
  "message": "How do we monitor ECS Fargate in production?",
  "service_id": "ecs-fargate"
}
```

## Next Service Packs

Add JSON files under `app/data/service_packs` for any additional organization standards, such as:

- DynamoDB
- RDS and Aurora
- Step Functions
- EKS
- CloudFront

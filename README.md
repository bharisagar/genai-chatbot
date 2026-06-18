# AWS AIOps Lens Advisor

A small production-shaped chatbot demo for adopting AWS monitoring, observability, and security patterns. The first implemented service pack is **ECS on Fargate**.

The app is intentionally simple on the surface:

- A browser chat UI for cloud engineers and platform teams.
- A FastAPI backend with approved service-pack content.
- Optional Amazon Bedrock integration for natural-language polish.
- Docker packaging for ECS/Fargate.
- Terraform starter infrastructure with ALB, ECS service, CloudWatch logs, dashboard, and alarms.

## Architecture

```text
User -> Chat UI -> FastAPI -> Service Pack Catalog
                         \-> Optional Amazon Bedrock
                         \-> CloudWatch-ready dashboard/alarm recommendations
```

The core production principle is that the LLM advises from curated service packs. It should not freely invent dashboards, alarms, or security controls.

## Implemented Service Pack

`ecs-fargate`

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
$env:AWS_REGION="us-east-1"
$env:BEDROCK_MODEL_ID="anthropic.claude-3-5-sonnet-20240620-v1:0"
$env:USE_BEDROCK="true"
```

The fallback remains the approved local service-pack answer if Bedrock is unavailable.

## Docker

```powershell
docker build -t aws-aiops-lens-advisor:local .
docker run --rm -p 8080:8080 aws-aiops-lens-advisor:local
```

## ECS/Fargate Deployment

Build and push an image to Amazon ECR, then deploy the Terraform under `infra/terraform`.

```powershell
cd infra/terraform
terraform init
terraform plan -out=tfplan `
  -var="name=aiops-lens-advisor" `
  -var="image_uri=<account>.dkr.ecr.<region>.amazonaws.com/aiops-lens-advisor:latest" `
  -var="vpc_id=vpc-xxxxxxxx" `
  -var='public_subnet_ids=["subnet-public-a","subnet-public-b"]' `
  -var='private_subnet_ids=["subnet-private-a","subnet-private-b"]'
terraform apply tfplan
```

The ALB is placed in public subnets. ECS/Fargate tasks are placed in private subnets, so those private subnets need NAT egress or VPC endpoints for ECR, CloudWatch Logs, and any AWS APIs the app uses.

## API

- `GET /health`
- `GET /api/service-packs`
- `GET /api/service-packs/ecs-fargate`
- `POST /api/chat`

Example:

```json
{
  "message": "How do we monitor ECS Fargate in production?",
  "service_id": "ecs-fargate"
}
```

## Next Service Packs

Add JSON files under `app/data/service_packs` for:

- Lambda
- S3
- API Gateway
- Load Balancer
- VPC
- Bedrock
- SageMaker

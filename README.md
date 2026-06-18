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

The next stage is deployable through Terraform and a PowerShell helper. Terraform creates:

- ECR repository with scan-on-push
- Dedicated VPC by default
- Public ALB subnets
- Private ECS/Fargate task subnets
- Optional NAT gateway for private task egress
- ECS cluster, task definition, service, ALB, target group
- CloudWatch log group, alarms, and dashboard

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

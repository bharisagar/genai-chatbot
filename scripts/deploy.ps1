param(
  [string]$Profile = "bedrock-governance",
  [string]$Region = "ap-south-1",
  [string]$Name = "aiops-lens-advisor",
  [string]$ImageTag = "latest",
  [switch]$EnableBedrock,
  [string]$BedrockModelId = "",
  [switch]$AutoApprove
)

$ErrorActionPreference = "Stop"

function Assert-LastExitCode {
  param([string]$CommandName)

  if ($LASTEXITCODE -ne 0) {
    throw "$CommandName failed with exit code $LASTEXITCODE"
  }
}

function Invoke-Step {
  param(
    [string]$Title,
    [scriptblock]$Command
  )

  Write-Host ""
  Write-Host "==> $Title" -ForegroundColor Cyan
  & $Command
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$tfDir = Join-Path $repoRoot "infra\terraform"
$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region

Invoke-Step "Checking AWS identity" {
  aws sts get-caller-identity --profile $Profile --region $Region
  Assert-LastExitCode "aws sts get-caller-identity"
}

Invoke-Step "Checking Docker daemon" {
  docker info | Out-Null
  Assert-LastExitCode "docker info"
}

Invoke-Step "Initializing Terraform" {
  terraform -chdir="$tfDir" init
  Assert-LastExitCode "terraform init"
}

$commonVars = @(
  "-var=name=$Name",
  "-var=aws_region=$Region",
  "-var=aws_profile=$Profile",
  "-var=image_tag=$ImageTag",
  "-var=enable_bedrock=$($EnableBedrock.IsPresent.ToString().ToLower())",
  "-var=bedrock_model_id=$BedrockModelId"
)

$approvalArgs = @()
if ($AutoApprove) {
  $approvalArgs += "-auto-approve"
}

Invoke-Step "Creating or refreshing ECR repository" {
  terraform -chdir="$tfDir" apply @approvalArgs "-target=aws_ecr_repository.app" @commonVars
  Assert-LastExitCode "terraform apply target ECR"
}

$repoUrl = terraform -chdir="$tfDir" output -raw ecr_repository_url
Assert-LastExitCode "terraform output ecr_repository_url"
$registry = $repoUrl.Split("/")[0]
$imageUri = "${repoUrl}:${ImageTag}"

Invoke-Step "Logging in to ECR" {
  $password = aws ecr get-login-password --profile $Profile --region $Region
  Assert-LastExitCode "aws ecr get-login-password"
  $password | docker login --username AWS --password-stdin $registry
  Assert-LastExitCode "docker login"
}

Invoke-Step "Building Docker image" {
  docker build -t "${Name}:${ImageTag}" "$repoRoot"
  Assert-LastExitCode "docker build"
}

Invoke-Step "Pushing Docker image to ECR" {
  docker tag "${Name}:${ImageTag}" $imageUri
  Assert-LastExitCode "docker tag"
  docker push $imageUri
  Assert-LastExitCode "docker push"
}

Invoke-Step "Applying ECS/Fargate infrastructure" {
  terraform -chdir="$tfDir" apply @approvalArgs @commonVars
  Assert-LastExitCode "terraform apply"
}

Invoke-Step "Forcing ECS service deployment" {
  aws ecs update-service `
    --profile $Profile `
    --region $Region `
    --cluster $Name `
    --service $Name `
    --force-new-deployment | Out-Null
  Assert-LastExitCode "aws ecs update-service"
}

Invoke-Step "Waiting for ECS service stability" {
  aws ecs wait services-stable `
    --profile $Profile `
    --region $Region `
    --cluster $Name `
    --services $Name
  Assert-LastExitCode "aws ecs wait services-stable"
}

Invoke-Step "Deployment outputs" {
  terraform -chdir="$tfDir" output
  Assert-LastExitCode "terraform output"
}

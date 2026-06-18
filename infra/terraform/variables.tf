variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "aiops-lens-advisor"
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "ap-south-1"
}

variable "vpc_id" {
  description = "Existing VPC ID where the ALB and ECS service will run. Required only when create_vpc is false."
  type        = string
  default     = null
}

variable "aws_profile" {
  description = "Optional local AWS CLI profile for Terraform runs."
  type        = string
  default     = null
}

variable "create_vpc" {
  description = "Create a dedicated production-style VPC with public ALB subnets and private ECS subnets."
  type        = bool
  default     = true
}

variable "vpc_cidr" {
  description = "CIDR block for the managed VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to use when create_vpc is true."
  type        = number
  default     = 2
}

variable "enable_nat_gateway" {
  description = "Create NAT gateway egress for private ECS tasks. Disable only when using private VPC endpoints or public task networking."
  type        = bool
  default     = true
}

variable "enable_vpc_flow_logs" {
  description = "Enable VPC Flow Logs to CloudWatch Logs for network observability and security evidence."
  type        = bool
  default     = true
}

variable "vpc_flow_log_retention_days" {
  description = "CloudWatch retention period for VPC Flow Logs."
  type        = number
  default     = 14
}

variable "single_nat_gateway" {
  description = "Use one NAT gateway for lower demo cost. Set false for one NAT gateway per AZ in stronger production setups."
  type        = bool
  default     = true
}

variable "public_subnet_ids" {
  description = "Existing public subnet IDs for the internet-facing ALB. Required only when create_vpc is false."
  type        = list(string)
  default     = []
}

variable "private_subnet_ids" {
  description = "Existing private subnet IDs for ECS tasks. Required only when create_vpc is false."
  type        = list(string)
  default     = []
}

variable "image_uri" {
  description = "Optional full container image URI. If blank, Terraform uses the managed ECR repository and image_tag."
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Container image tag to deploy from the managed ECR repository."
  type        = string
  default     = "latest"
}

variable "ecr_repository_name" {
  description = "Optional ECR repository name. Defaults to the value of name."
  type        = string
  default     = ""
}

variable "force_delete_ecr" {
  description = "Allow Terraform destroy to delete the ECR repository even if it contains images."
  type        = bool
  default     = false
}

variable "desired_count" {
  description = "Number of ECS tasks."
  type        = number
  default     = 2
}

variable "cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 512
}

variable "memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 1024
}

variable "bedrock_model_id" {
  description = "Optional Bedrock model ID. Leave blank to use deterministic service-pack responses."
  type        = string
  default     = ""
}

variable "enable_bedrock" {
  description = "Enable Bedrock response generation in the container."
  type        = bool
  default     = false
}

variable "bedrock_input_price_per_1k" {
  description = "Optional Bedrock input-token price per 1,000 tokens for estimated request-cost metrics. Keep 0 unless the chosen model price has been confirmed."
  type        = number
  default     = 0
}

variable "bedrock_output_price_per_1k" {
  description = "Optional Bedrock output-token price per 1,000 tokens for estimated request-cost metrics. Keep 0 unless the chosen model price has been confirmed."
  type        = number
  default     = 0
}

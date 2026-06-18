variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "aiops-lens-advisor"
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "vpc_id" {
  description = "Existing VPC ID where the ALB and ECS service will run."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the internet-facing ALB."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks. These need NAT egress or VPC endpoints for ECR and CloudWatch Logs."
  type        = list(string)
}

variable "image_uri" {
  description = "Container image URI in ECR or another registry reachable by ECS."
  type        = string
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

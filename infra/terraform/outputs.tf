output "alb_dns_name" {
  description = "Public DNS name of the application load balancer."
  value       = aws_lb.this.dns_name
}

output "application_url" {
  description = "HTTP URL for the deployed chatbot."
  value       = "http://${aws_lb.this.dns_name}"
}

output "ecr_repository_url" {
  description = "ECR repository URL for the chatbot image."
  value       = aws_ecr_repository.app.repository_url
}

output "image_uri" {
  description = "Container image URI configured on the ECS task definition."
  value       = local.image_uri
}

output "vpc_id" {
  description = "VPC used by the ECS service."
  value       = local.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs used by the ALB."
  value       = local.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs used by ECS tasks."
  value       = local.private_subnet_ids
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.app.name
}

output "cloudwatch_dashboard_name" {
  description = "CloudWatch dashboard created for the ECS Fargate service pack."
  value       = aws_cloudwatch_dashboard.ecs.dashboard_name
}

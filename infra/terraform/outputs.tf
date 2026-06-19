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

output "application_log_group_name" {
  description = "CloudWatch log group for application and chatbot EMF telemetry."
  value       = aws_cloudwatch_log_group.app.name
}

output "vpc_flow_log_group_name" {
  description = "CloudWatch log group for VPC Flow Logs when enabled."
  value       = var.enable_vpc_flow_logs ? aws_cloudwatch_log_group.vpc_flow[0].name : null
}

output "telemetry_table_name" {
  description = "DynamoDB table used for durable chatbot telemetry when enabled."
  value       = var.enable_telemetry_table ? aws_dynamodb_table.telemetry[0].name : null
}

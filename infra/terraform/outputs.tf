output "alb_dns_name" {
  description = "Public DNS name of the application load balancer."
  value       = aws_lb.this.dns_name
}

output "application_url" {
  description = "HTTP URL for the deployed chatbot."
  value       = "http://${aws_lb.this.dns_name}"
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


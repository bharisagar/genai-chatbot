locals {
  container_name      = "advisor"
  app_port            = 8080
  ecr_repository_name = var.ecr_repository_name != "" ? var.ecr_repository_name : var.name
  image_uri           = var.image_uri != "" ? var.image_uri : "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
  common_tags = {
    Application = var.name
    ManagedBy   = "terraform"
  }
  nat_gateway_dashboard_widgets = [
    for nat in aws_nat_gateway.this : {
      type   = "metric"
      x      = 0
      y      = 46
      width  = 12
      height = 6
      properties = {
        title  = "NAT Gateway Egress and Drops"
        view   = "timeSeries"
        region = var.aws_region
        metrics = [
          ["AWS/NATGateway", "BytesOutToDestination", "NatGatewayId", nat.id, { stat = "Sum", label = "Bytes out to internet" }],
          [".", "BytesInFromDestination", ".", ".", { stat = "Sum", label = "Bytes in from internet" }],
          [".", "PacketsDropCount", ".", ".", { stat = "Sum", label = "Dropped packets" }],
          [".", "ErrorPortAllocation", ".", ".", { stat = "Sum", label = "Port allocation errors" }]
        ]
      }
    }
  ]
  vpc_flow_dashboard_widgets = flatten([
    for log_group in aws_cloudwatch_log_group.vpc_flow : [
      {
        type   = "metric"
        x      = 12
        y      = 46
        width  = 12
        height = 6
        properties = {
          title  = "VPC Flow Log Ingestion"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AWS/Logs", "IncomingLogEvents", "LogGroupName", log_group.name, { stat = "Sum" }],
            [".", "IncomingBytes", ".", ".", { stat = "Sum" }]
          ]
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 52
        width  = 24
        height = 6
        properties = {
          title  = "VPC Flow Reject Evidence"
          region = var.aws_region
          query  = "SOURCE '${log_group.name}' | fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, protocol, action, logStatus | filter action = 'REJECT' | sort @timestamp desc | limit 50"
        }
      }
    ]
  ])
  support_resource_dashboard_widgets = concat(
    [
      {
        type   = "text"
        x      = 0
        y      = 44
        width  = 24
        height = 2
        properties = {
          markdown = "# Supporting AWS Resource Observability\nResource-level telemetry for the main services used by the chatbot stack: VPC, NAT, CloudWatch Logs, ECR, ALB, ECS, and optional Bedrock."
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 58
        width  = 12
        height = 6
        properties = {
          title  = "Application Log Ingestion"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AWS/Logs", "IncomingLogEvents", "LogGroupName", aws_cloudwatch_log_group.app.name, { stat = "Sum" }],
            [".", "IncomingBytes", ".", ".", { stat = "Sum" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 58
        width  = 12
        height = 6
        properties = {
          title  = "ECR Repository Pulls"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AWS/ECR", "RepositoryPullCount", "RepositoryName", aws_ecr_repository.app.name, { stat = "Sum" }]
          ]
        }
      }
    ],
    local.nat_gateway_dashboard_widgets,
    local.vpc_flow_dashboard_widgets
  )
}

resource "aws_ecr_repository" "app" {
  name                 = local.ecr_repository_name
  image_tag_mutability = "MUTABLE"
  force_delete         = var.force_delete_ecr

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = local.common_tags
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the latest 20 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 20
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}"
  retention_in_days = 30
  tags              = local.common_tags
}

resource "aws_ecs_cluster" "this" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "Allow HTTP traffic to the advisor ALB"
  vpc_id      = local.vpc_id

  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_security_group" "app" {
  name        = "${var.name}-app"
  description = "Allow ALB traffic to advisor ECS tasks"
  vpc_id      = local.vpc_id

  ingress {
    description     = "App port from ALB"
    from_port       = local.app_port
    to_port         = local.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_lb" "this" {
  name               = var.name
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = local.public_subnet_ids
  tags               = local.common_tags
}

resource "aws_lb_target_group" "app" {
  name        = var.name
  port        = local.app_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = local.vpc_id

  health_check {
    enabled             = true
    path                = "/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = local.common_tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_iam_role" "task_execution" {
  name = "${var.name}-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name = "${var.name}-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy" "bedrock" {
  count = var.enable_bedrock ? 1 : 0
  name  = "${var.name}-bedrock"
  role  = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_ecs_task_definition" "app" {
  family                   = var.name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = local.image_uri
      essential = true
      portMappings = [
        {
          containerPort = local.app_port
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "APPLICATION_NAME"
          value = var.name
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "USE_BEDROCK"
          value = tostring(var.enable_bedrock)
        },
        {
          name  = "BEDROCK_MODEL_ID"
          value = var.bedrock_model_id
        },
        {
          name  = "BEDROCK_INPUT_PRICE_PER_1K"
          value = tostring(var.bedrock_input_price_per_1k)
        },
        {
          name  = "BEDROCK_OUTPUT_PRICE_PER_1K"
          value = tostring(var.bedrock_output_price_per_1k)
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()\""]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }
    }
  ])

  tags = local.common_tags
}

resource "aws_ecs_service" "app" {
  name            = var.name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.private_subnet_ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = local.container_name
    container_port   = local.app_port
  }

  depends_on = [aws_lb_listener.http]
  tags       = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "ecs_high_cpu" {
  alarm_name          = "${var.name}-ecs-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "ECS service CPU utilization is above 80 percent."
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.this.name
    ServiceName = aws_ecs_service.app.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "ecs_high_memory" {
  alarm_name          = "${var.name}-ecs-high-memory"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "ECS service memory utilization is above 80 percent."
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.this.name
    ServiceName = aws_ecs_service.app.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.name}-alb-target-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "ALB target 5xx errors exceeded the demo threshold."
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.app.arn_suffix
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "alb_unhealthy_targets" {
  alarm_name          = "${var.name}-alb-unhealthy-targets"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "One or more ALB targets are unhealthy."
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.app.arn_suffix
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "ecs_running_task_mismatch" {
  alarm_name          = "${var.name}-ecs-running-task-mismatch"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "RunningTaskCount"
  namespace           = "ECS/ContainerInsights"
  period              = 300
  statistic           = "Average"
  threshold           = var.desired_count
  alarm_description   = "Running ECS task count is below the desired count."
  treat_missing_data  = "breaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.this.name
    ServiceName = aws_ecs_service.app.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_log_metric_filter" "vpc_flow_rejects" {
  count          = var.enable_vpc_flow_logs ? 1 : 0
  name           = "${var.name}-vpc-flow-rejects"
  log_group_name = aws_cloudwatch_log_group.vpc_flow[0].name
  pattern        = "[version, account_id, interface_id, srcaddr, dstaddr, srcport, dstport, protocol, packets, bytes, start, end, action = \"REJECT\", log_status]"

  metric_transformation {
    name      = "VpcFlowRejectCount"
    namespace = "AIOpsLens/Network"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "vpc_flow_rejects" {
  count               = var.enable_vpc_flow_logs ? 1 : 0
  alarm_name          = "${var.name}-vpc-flow-rejects"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "VpcFlowRejectCount"
  namespace           = "AIOpsLens/Network"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "VPC Flow Logs captured rejected traffic for the chatbot VPC."
  treat_missing_data  = "notBreaching"

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "nat_packets_dropped" {
  for_each            = { for nat in aws_nat_gateway.this : nat.id => nat.id }
  alarm_name          = "${var.name}-nat-packets-dropped-${each.key}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "PacketsDropCount"
  namespace           = "AWS/NATGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "NAT gateway dropped packets for the chatbot stack."
  treat_missing_data  = "notBreaching"

  dimensions = {
    NatGatewayId = each.value
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "chatbot_errors" {
  alarm_name          = "${var.name}-chatbot-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ErrorCount"
  namespace           = "AIOpsLens/Chatbot"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "One or more chatbot requests failed in the last evaluation period."
  treat_missing_data  = "notBreaching"

  dimensions = {
    Application = var.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "chatbot_high_latency" {
  alarm_name          = "${var.name}-chatbot-high-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "LatencyMs"
  namespace           = "AIOpsLens/Chatbot"
  period              = 300
  statistic           = "Average"
  threshold           = 3000
  alarm_description   = "Average chatbot request latency is above 3 seconds."
  treat_missing_data  = "notBreaching"

  dimensions = {
    Application = var.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "chatbot_low_confidence" {
  alarm_name          = "${var.name}-chatbot-low-confidence"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "LowConfidenceCount"
  namespace           = "AIOpsLens/Chatbot"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "More than five low-confidence chatbot responses were produced in one period."
  treat_missing_data  = "notBreaching"

  dimensions = {
    Application = var.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "chatbot_cost_spike" {
  alarm_name          = "${var.name}-chatbot-cost-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCostUsd"
  namespace           = "AIOpsLens/Chatbot"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Estimated Bedrock chatbot cost exceeded 1 USD in one period."
  treat_missing_data  = "notBreaching"

  dimensions = {
    Application = var.name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_dashboard" "ecs" {
  dashboard_name = "${var.name}-ecs-fargate"

  dashboard_body = jsonencode({
    widgets = concat([
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 2
        properties = {
          markdown = "# ECS Fargate Production Health\nService-pack dashboard for monitoring, observability, security, and adoption evidence."
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 2
        width  = 12
        height = 6
        properties = {
          title  = "ECS CPU and Memory"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.this.name, "ServiceName", aws_ecs_service.app.name],
            [".", "MemoryUtilization", ".", ".", ".", "."]
          ]
          stat = "Average"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 2
        width  = 12
        height = 6
        properties = {
          title  = "ALB Latency and 5xx"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.this.arn_suffix],
            [".", "HTTPCode_Target_5XX_Count", ".", ".", "TargetGroup", aws_lb_target_group.app.arn_suffix]
          ]
          stat = "Average"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 8
        width  = 12
        height = 6
        properties = {
          title  = "Target Health"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", aws_lb.this.arn_suffix, "TargetGroup", aws_lb_target_group.app.arn_suffix],
            [".", "UnHealthyHostCount", ".", ".", ".", "."]
          ]
          stat = "Average"
        }
      },
      {
        type   = "log"
        x      = 12
        y      = 8
        width  = 12
        height = 6
        properties = {
          title  = "Application Errors"
          region = var.aws_region
          query  = "SOURCE '${aws_cloudwatch_log_group.app.name}' | fields @timestamp, @message | filter @message like /(?i)(error|exception|failed)/ | sort @timestamp desc | limit 50"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 14
        width  = 12
        height = 6
        properties = {
          title  = "ECS Running Tasks"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", aws_ecs_cluster.this.name, "ServiceName", aws_ecs_service.app.name],
            [".", "DesiredTaskCount", ".", ".", ".", "."]
          ]
          stat = "Average"
        }
      },
      {
        type   = "text"
        x      = 0
        y      = 20
        width  = 24
        height = 2
        properties = {
          markdown = "# Chatbot Observability, Explainability, Token Usage, and Cost\nMetrics are emitted by the FastAPI application using CloudWatch Embedded Metric Format."
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 22
        width  = 12
        height = 6
        properties = {
          title  = "Request Volume, Success, and Errors"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AIOpsLens/Chatbot", "RequestCount", "Application", var.name, { stat = "Sum" }],
            [".", "SuccessCount", ".", ".", { stat = "Sum" }],
            [".", "ErrorCount", ".", ".", { stat = "Sum" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 22
        width  = 12
        height = 6
        properties = {
          title  = "End-to-End Latency"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AIOpsLens/Chatbot", "LatencyMs", "Application", var.name, { stat = "Average", label = "Average latency" }],
            [".", ".", ".", ".", { stat = "p95", label = "p95 latency" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 28
        width  = 12
        height = 6
        properties = {
          title  = "Token Usage"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AIOpsLens/Chatbot", "InputTokens", "Application", var.name, { stat = "Sum" }],
            [".", "OutputTokens", ".", ".", { stat = "Sum" }],
            [".", "TotalTokens", ".", ".", { stat = "Sum" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 28
        width  = 12
        height = 6
        properties = {
          title  = "Estimated Cost and Governance Signals"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            ["AIOpsLens/Chatbot", "EstimatedCostUsd", "Application", var.name, { stat = "Sum" }],
            [".", "FallbackCount", ".", ".", { stat = "Sum" }],
            [".", "LowConfidenceCount", ".", ".", { stat = "Sum" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 34
        width  = 12
        height = 6
        properties = {
          title  = "Requests by AWS Service"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            [{ expression = "SEARCH('{AIOpsLens/Chatbot,Application,ServiceId} Application=\"${var.name}\" MetricName=\"RequestCount\"', 'Sum', 300)", id = "service_requests", label = "Service requests" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 34
        width  = 12
        height = 6
        properties = {
          title  = "Requests by Intent"
          view   = "timeSeries"
          region = var.aws_region
          metrics = [
            [{ expression = "SEARCH('{AIOpsLens/Chatbot,Application,Intent} Application=\"${var.name}\" MetricName=\"RequestCount\"', 'Sum', 300)", id = "intent_requests", label = "Intent requests" }]
          ]
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 40
        width  = 24
        height = 6
        properties = {
          title  = "Explainability and Decision Evidence"
          region = var.aws_region
          query  = "SOURCE '${aws_cloudwatch_log_group.app.name}' | fields @timestamp, RequestId, ServiceId, Intent, ResponseSource, Confidence, LatencyMs, TotalTokens, EstimatedCostUsd, Explainability.selected_service_reason, Explainability.selected_intent_reason | filter EventType = 'chatbot_observability' | sort @timestamp desc | limit 50"
        }
      }
    ], local.support_resource_dashboard_widgets)
  })
}

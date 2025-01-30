provider "aws" {
  region = "us-west-2"
}

#-----------------------------------------------------------
# Security Groups (Dynamically Created for Each Resource)
#-----------------------------------------------------------
locals {
  # Flatten all security groups from all resources
  all_security_groups = merge(
    { for k, v in local.config.ec2_instances : "ec2_${k}" => v.security_group_rules },
    { for k, v in local.config.load_balancers : "lb_${k}" => v.security_group_rules },
    { for k, v in local.config.rds_databases : "rds_${k}" => v.security_group_rules }
  )
}

resource "aws_security_group" "dynamic_sg" {
  for_each = local.all_security_groups

  name        = "${each.key}-sg"
  description = "Security group for ${each.key}"

  # Dynamic ingress/egress rules
  dynamic "ingress" {
    for_each = try(each.value.ingress, [])
    content {
      from_port   = ingress.value.from_port
      to_port     = ingress.value.to_port
      protocol    = ingress.value.protocol
      cidr_blocks = lookup(ingress.value, "cidr_blocks", null)

      # Resolve security group references (e.g., "lb" -> LB security group)
      security_groups = contains(keys(ingress.value), "source_security_group") ? [
        aws_security_group.dynamic_sg["lb_${ingress.value.source_security_group}"].id
      ] : null
    }
  }

  dynamic "egress" {
    for_each = try(each.value.egress, [])
    content {
      from_port   = egress.value.from_port
      to_port     = egress.value.to_port
      protocol    = egress.value.protocol
      cidr_blocks = egress.value.cidr_blocks
    }
  }
}

#-----------------------------------------------------------
# EC2 Instances
#-----------------------------------------------------------
resource "aws_instance" "ec2_instances" {
  for_each = local.config.ec2_instances

  ami           = each.value.ami
  instance_type = each.value.instance_type
  subnet_id     = each.value.subnet_id
  vpc_security_group_ids = [
    aws_security_group.dynamic_sg["ec2_${each.key}"].id
  ]

  tags = {
    Name = each.key
  }
}

#-----------------------------------------------------------
# Load Balancers
#-----------------------------------------------------------
resource "aws_lb" "load_balancers" {
  for_each = local.config.load_balancers

  name               = each.value.name
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.dynamic_sg["lb_${each.key}"].id]
  subnets            = each.value.subnet_ids

  tags = {
    Name = each.key
  }
}

resource "aws_lb_target_group" "tg" {
  for_each = local.config.load_balancers

  name     = "${each.key}-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_instance.ec2_instances[each.value.target_instances[0]].vpc_id

  health_check {
    path = "/"
  }
}

resource "aws_lb_listener" "listener" {
  for_each = local.config.load_balancers

  load_balancer_arn = aws_lb.load_balancers[each.key].arn
  port              = each.value.listener.port
  protocol          = each.value.listener.protocol

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg[each.key].arn
  }
}

resource "aws_lb_target_group_attachment" "tga" {
  for_each = {
    for lb in local.config.load_balancers : lb.key => lb.value.target_instances
  }

  target_group_arn = aws_lb_target_group.tg[each.key].arn
  target_id        = aws_instance.ec2_instances[each.value].id
  port             = 80
}

#-----------------------------------------------------------
# RDS Databases
#-----------------------------------------------------------
resource "aws_db_subnet_group" "rds_subnet_group" {
  for_each = local.config.rds_databases

  name       = "${each.key}-subnet-group"
  subnet_ids = each.value.subnet_ids

  tags = {
    Name = each.key
  }
}

resource "aws_db_instance" "rds" {
  for_each = local.config.rds_databases

  identifier           = each.key
  allocated_storage    = each.value.allocated_storage
  engine               = "postgres"
  engine_version       = "13.4"
  instance_class       = each.value.instance_class
  db_name              = each.value.db_name
  username             = each.value.username
  password             = each.value.password
  db_subnet_group_name = aws_db_subnet_group.rds_subnet_group[each.key].name
  vpc_security_group_ids = [
    aws_security_group.dynamic_sg["rds_${each.key}"].id
  ]
  skip_final_snapshot  = true
  publicly_accessible  = false
}

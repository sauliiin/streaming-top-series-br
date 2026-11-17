# One-time stack, applied manually by an administrator with local state.
# It creates what the CI/CD pipeline needs before it can run:
#   * the S3 bucket that stores the application stack's Terraform state;
#   * the GitHub Actions OIDC identity provider (no long-lived AWS keys);
#   * the deploy role assumed by the pipeline, restricted to this repository and branch.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}

variable "project" {
  type    = string
  default = "streaming-top-series"
}

variable "aws_region" {
  type    = string
  default = "sa-east-1"
}

variable "github_repository" {
  description = "owner/name of the GitHub repository allowed to deploy."
  type        = string
}

variable "deploy_branch" {
  type    = string
  default = "main"
}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = var.aws_region
  prefix     = var.project
}

# ---------- Terraform state ----------

resource "aws_s3_bucket" "state" {
  bucket = "${local.prefix}-tfstate-${local.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------- GitHub Actions OIDC ----------

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/${var.deploy_branch}",
        "repo:${var.github_repository}:environment:production",
      ]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${local.prefix}-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_trust.json
  max_session_duration = 3600
}

# Scoped to resources named with the project prefix. Refine further with
# IAM Access Analyzer policy generation after the first successful deploys.
data "aws_iam_policy_document" "deploy" {
  statement {
    sid     = "TerraformState"
    actions = ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/app/*",
    ]
  }

  statement {
    sid       = "Lambda"
    actions   = ["lambda:*"]
    resources = ["arn:aws:lambda:${local.region}:${local.account_id}:function:${local.prefix}-*"]
  }

  statement {
    sid = "IamRoles"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateRole", "iam:TagRole", "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy", "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy",
      "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:PassRole",
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/${local.prefix}-lambda",
      "arn:aws:iam::${local.account_id}:role/${local.prefix}-scheduler",
    ]
  }

  statement {
    sid       = "Scheduler"
    actions   = ["scheduler:*"]
    resources = ["arn:aws:scheduler:${local.region}:${local.account_id}:schedule/default/${local.prefix}-*"]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:*"]
    resources = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.prefix}-*"]
  }

  statement {
    sid     = "SnapshotBucket"
    actions = ["s3:*"]
    resources = [
      "arn:aws:s3:::${local.prefix}-snapshots-${local.account_id}",
      "arn:aws:s3:::${local.prefix}-site-${local.account_id}",
      "arn:aws:s3:::${local.prefix}-site-${local.account_id}/*",
    ]
  }

  statement {
    sid     = "Messaging"
    actions = ["sns:*", "sqs:*"]
    resources = [
      "arn:aws:sns:${local.region}:${local.account_id}:${local.prefix}-*",
      "arn:aws:sqs:${local.region}:${local.account_id}:${local.prefix}-*",
    ]
  }

  statement {
    sid       = "Alarms"
    actions   = ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:TagResource", "cloudwatch:ListTagsForResource"]
    resources = ["arn:aws:cloudwatch:${local.region}:${local.account_id}:alarm:${local.prefix}-*"]
  }

  statement {
    sid = "CloudFront" # distribution ids are unknown before creation
    actions = [
      "cloudfront:CreateDistribution", "cloudfront:UpdateDistribution", "cloudfront:DeleteDistribution",
      "cloudfront:GetDistribution", "cloudfront:GetDistributionConfig", "cloudfront:TagResource",
      "cloudfront:ListTagsForResource", "cloudfront:CreateOriginAccessControl", "cloudfront:GetOriginAccessControl",
      "cloudfront:UpdateOriginAccessControl", "cloudfront:DeleteOriginAccessControl", "cloudfront:ListCachePolicies",
      "cloudfront:GetCachePolicy", "cloudfront:CreateResponseHeadersPolicy", "cloudfront:GetResponseHeadersPolicy",
      "cloudfront:UpdateResponseHeadersPolicy", "cloudfront:DeleteResponseHeadersPolicy", "cloudfront:CreateInvalidation",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "ReadOnlyDescribe"
    actions   = ["cloudwatch:DescribeAlarms", "logs:DescribeLogGroups", "iam:GetOpenIDConnectProvider", "sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "${local.prefix}-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN repository variable in GitHub."
  value       = aws_iam_role.deploy.arn
}

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # Partial configuration: bucket/key/region come from backend.hcl (see backend.hcl.example).
  # use_lockfile (Terraform >= 1.10) removes the need for a DynamoDB lock table.
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project    = var.project
      ManagedBy  = "terraform"
      Repository = "streaming-top-series-br"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

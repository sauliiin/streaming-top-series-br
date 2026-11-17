output "function_name" {
  value = aws_lambda_function.sync.function_name
}

output "snapshot_bucket" {
  value = aws_s3_bucket.snapshots.bucket
}

output "feeds_base_url" {
  description = "Set as the FEEDS_BASE_URL repository variable; the Pages workflow injects it into the site."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}/data/"
}

output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "ssm_parameters_to_create" {
  description = "Create these SecureString parameters before the first run (see docs/runbook.md)."
  value       = ["${var.ssm_prefix}/tmdb_api_key", "${var.ssm_prefix}/mdblist_api_key"]
}

locals {
  function_name = "${var.project}-sync"
  ssm_arn_base  = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_prefix}"
}

# The artifact is just the source tree: the app uses the stdlib only (+ boto3 from the runtime).
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../src"
  output_path = "${path.module}/build/lambda.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc", "*.egg-info/**"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "sync" {
  function_name    = local.function_name
  description      = "Daily sync of recent series and movie releases (Netflix/HBO Max/Prime Video, BR) to MDBList"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "streaming_top_series.entrypoints.lambda_handler.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 512
  timeout          = 600 # movies widen their window step by step; observed runtime is ~40 s

  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = merge(
      {
        TMDB_API_KEY_PARAM    = "${var.ssm_prefix}/tmdb_api_key"
        MDBLIST_API_KEY_PARAM = "${var.ssm_prefix}/mdblist_api_key"
        SNAPSHOT_BUCKET       = aws_s3_bucket.snapshots.bucket
        IMDB_CACHE_DIR        = "/tmp/imdb" # dataset reused by warm containers for up to 20 h
        SITE_BUCKET           = aws_s3_bucket.site.bucket
      },
      var.app_env,
    )
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# Asynchronous invocation (Scheduler): one Lambda-level retry, then the event lands in the DLQ.
resource "aws_lambda_function_event_invoke_config" "sync" {
  function_name                = aws_lambda_function.sync.function_name
  maximum_retry_attempts       = 1
  maximum_event_age_in_seconds = 3600

  destination_config {
    on_failure {
      destination = aws_sqs_queue.dlq.arn
    }
  }
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project}-sync-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

# ---------- IAM: least privilege ----------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "ReadSecrets"
    actions   = ["ssm:GetParameters"]
    resources = ["${local.ssm_arn_base}/*"]
    # SecureString encrypted with the AWS-managed aws/ssm key: its key policy already allows use via SSM.
  }

  statement {
    sid       = "WriteSnapshots"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.snapshots.arn}/snapshots/*"]
  }

  statement {
    sid       = "WebsiteFeeds"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.site.arn}/data/*"]
  }

  statement {
    sid       = "ListWebsite" # lets GetObject on a missing feed return 404 instead of 403
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.site.arn]
  }

  statement {
    sid       = "DeadLetter"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.project}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

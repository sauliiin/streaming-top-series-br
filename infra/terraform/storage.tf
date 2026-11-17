# Daily audit trail: snapshots/YYYY-MM-DD.json with the ranking and the applied diff.
resource "aws_s3_bucket" "snapshots" {
  bucket = "${var.project}-snapshots-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "snapshots" {
  bucket                  = aws_s3_bucket.snapshots.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id
  rule {
    id     = "expire-snapshots"
    status = "Enabled"
    filter {
      prefix = "snapshots/"
    }
    expiration {
      days = var.snapshot_retention_days
    }
  }
}

data "aws_iam_policy_document" "snapshots_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.snapshots.arn, "${aws_s3_bucket.snapshots.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "snapshots" {
  bucket     = aws_s3_bucket.snapshots.id
  policy     = data.aws_iam_policy_document.snapshots_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.snapshots]
}

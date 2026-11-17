variable "project" {
  description = "Name prefix for every resource (must match the bootstrap stack)."
  type        = string
  default     = "streaming-top-series"
}

variable "aws_region" {
  type    = string
  default = "sa-east-1"
}

variable "schedules" {
  description = "Job name => EventBridge Scheduler cron, evaluated in schedule_timezone."
  type        = map(string)
  default = {
    series = "cron(0 6 * * ? *)"
    movies = "cron(15 6 * * ? *)"
  }

  validation {
    condition     = alltrue([for job in keys(var.schedules) : contains(["series", "movies"], job)])
    error_message = "Valid jobs are \"series\" and \"movies\"."
  }
}

variable "schedule_timezone" {
  type    = string
  default = "America/Sao_Paulo"
}

variable "ssm_prefix" {
  description = "Prefix of the SecureString parameters created out of band (secrets never enter the state)."
  type        = string
  default     = "/streaming-top-series"
}

variable "app_env" {
  description = "Extra 12-factor application settings (TOP_N, MIN_VOTE, MIN_VOTE_COUNT, PROVIDERS, DRY_RUN...)."
  type        = map(string)
  default     = {}
}

variable "alert_email" {
  description = "E-mail address subscribed to alarms (empty = no subscription)."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "snapshot_retention_days" {
  type    = number
  default = 365
}

variable "reserved_concurrency" {
  description = "1 prevents concurrent runs on the same lists. -1 = unreserved (new accounts have a low quota)."
  type        = number
  default     = -1
}

variable "site_origins" {
  description = "Origins (scheme://host) allowed to read the feeds via CORS: the GitHub Pages site."
  type        = list(string)
  default     = ["https://sauliiin.github.io"]
}

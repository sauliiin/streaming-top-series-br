# Runbook

## 1. First-time setup

### 1.1 Bootstrap (once, with administrator credentials)

```bash
cd infra/bootstrap
terraform init
terraform apply -var 'github_repository=<owner>/streaming-top-series-br'
```

Outputs: `state_bucket` and `deploy_role_arn`.

### 1.2 Secrets

Create the parameters **outside Terraform** so that the values never reach the state file:

```bash
aws ssm put-parameter --name /streaming-top-series/tmdb_api_key    --type SecureString --value '<TMDB key>'
aws ssm put-parameter --name /streaming-top-series/mdblist_api_key --type SecureString --value '<MDBList key>'
```

To rotate a key, run the same command with `--overwrite`. Running containers pick up the new value
on their next cold start.

### 1.3 GitHub configuration

| Kind | Name | Value |
| --- | --- | --- |
| Variable | `AWS_REGION` | `sa-east-1` |
| Variable | `AWS_DEPLOY_ROLE_ARN` | bootstrap output `deploy_role_arn` |
| Variable | `TF_STATE_BUCKET` | bootstrap output `state_bucket` |
| Secret | `ALERT_EMAIL` | address that receives alarms (optional) |
| Variable | `FEEDS_BASE_URL` | Terraform output `feeds_base_url` (enables the Pages workflow) |
| Environment | `production` | add required reviewers to gate deployments if desired |

### 1.4 First deployment

Push to `main`, or run the **Deploy** workflow manually. For the first days, consider setting
`DRY_RUN = "true"` in `app_env` and checking the logged diffs before going live.

To deploy from a workstation instead:

```bash
cd infra/terraform
cp backend.hcl.example backend.hcl && cp terraform.tfvars.example terraform.tfvars   # edit both
make tf-init tf-plan tf-apply
```

## 2. Day-to-day operations

### Run on demand

```bash
aws lambda invoke --function-name streaming-top-series-sync \
  --cli-binary-format raw-in-base64-out --payload '{"dry_run": true}' /dev/stdout
# One job / one provider:  --payload '{"job": "movies", "providers": ["hbo"]}'
```

### Useful Logs Insights queries

```
fields @timestamp, event, provider, selected, add, remove, error
| filter event in ["selection_completed", "list_synced", "provider_failed", "removals_skipped"]
| sort @timestamp desc
```

### Inspect a snapshot

```bash
aws s3 cp s3://streaming-top-series-snapshots-<account>/snapshots/series/$(date +%F).json - | jq '.results[] | {provider, added, removed}'
aws s3 cp s3://streaming-top-series-snapshots-<account>/snapshots/movies/$(date +%F).json - | jq '{status, added, removed}'
```

## 3. Alarms and troubleshooting

| Alarm | Likely cause | Action |
| --- | --- | --- |
| `*-sync-errors` | A provider failed: TMDB/MDBList outage, invalid key or timeout | Filter the logs on `provider_failed`. HTTP 401 means rotate the key (§1.2); 429/5xx are usually transient, so re-run on demand |
| `*-sync-missed` | Schedule disabled, throttling, or the function was not deployed | Check the schedule state and Lambda throttles; invoke manually |
| `*-sync-dlq` | Async retries exhausted | Inspect the DLQ message, fix the cause, re-run, then purge the queue |
| `removals_skipped` (log warning) | The catalog returned fewer titles than `SAFETY_MIN_SELECTED`, or (movies) a provider failed | Usually upstream degradation; resolves on its own the next day. Confirm with a dry run |
| `provider_failed` mentioning `title.ratings` | IMDb dataset download failed | Transient: the job retries on the next schedule. Disable temporarily with `IMDB_RATINGS=false` (TMDB-only scores) |

## 4. Changing the selection criteria

All rules are environment variables (see `.env.example`). In AWS, change `app_env` in
`terraform.tfvars` (or the pipeline variables) and redeploy. No code changes are required.

## 5. Local scheduler (optional)

Before the AWS deployment, or as a fallback, the sync can run on a workstation with a systemd user
timer. Keep secrets outside the repository, in a file with mode 600:

```ini
# ~/.config/systemd/user/streaming-top-series-movies.timer
[Timer]
OnCalendar=*-*-* 06:15:00
Persistent=true

# ~/.config/systemd/user/streaming-top-series-movies.service
[Service]
Type=oneshot
ExecStart=%h/.config/streaming-top-series/run.sh movies
```

```bash
systemctl --user enable --now streaming-top-series-movies.timer
journalctl --user -u streaming-top-series-movies.service -n 50
```

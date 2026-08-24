#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$project_root/backups"
file_name="hr_agent_$(date -u +%Y%m%d_%H%M%S).dump"
cd "$project_root"
docker compose --env-file .env.production --profile tools run --rm db-tools \
  pg_dump --format=custom --no-owner --no-acl --file="/backups/$file_name"
printf 'Backup created: %s\n' "$project_root/backups/$file_name"

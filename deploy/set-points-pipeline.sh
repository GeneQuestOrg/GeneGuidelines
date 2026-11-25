#!/usr/bin/env bash
# Switch the guideline-points pipeline on both production apps (gg-public runs the backfill endpoint, gg-worker the after-synthesis hook) and read both back.
#
#   deploy/set-points-pipeline.sh bricks   # or: loop (the default, and the rollback)
#
# Each app restarts on the same image (a new revision; no code is deployed). Run it when the research queue is idle. Changing the pipeline rebuilds nothing by itself: follow it with a forced backfill (POST /api/pipeline/guideline-points/backfill {"force": true}) when the stored blocks should be rebuilt with the new pipeline. Docs plan "cegiełki", step 5.
set -euo pipefail

pipeline="${1:-}"
if [[ "$pipeline" != "loop" && "$pipeline" != "bricks" ]]; then
  echo "usage: $0 loop|bricks" >&2
  exit 2
fi
group="${AZURE_RESOURCE_GROUP:-geneguidelines-demo}"
subscription="${AZURE_SUBSCRIPTION:-e80c0793-8fcd-419f-8941-5dbe93598b39}"

for app in gg-public gg-worker; do
  az containerapp update --subscription "$subscription" -n "$app" -g "$group" --set-env-vars "GUIDELINE_POINTS_PIPELINE=$pipeline" -o none
done
for app in gg-public gg-worker; do
  value=$(az containerapp show --subscription "$subscription" -n "$app" -g "$group" --query "properties.template.containers[0].env[?name=='GUIDELINE_POINTS_PIPELINE'].value | [0]" -o tsv)
  echo "$app: GUIDELINE_POINTS_PIPELINE=$value"
  [[ "$value" == "$pipeline" ]] || { echo "$app did not take the new value" >&2; exit 1; }
done

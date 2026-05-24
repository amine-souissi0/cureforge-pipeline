#!/bin/bash
# Push the CI workflow file to GitHub.
#
# Your current GitHub PAT lacks the `workflow` scope.
# Steps:
#   1. Visit https://github.com/settings/tokens
#   2. Click your token → Edit → check the `workflow` checkbox → Update token
#   3. If using HTTPS, update your git credential:
#        git remote set-url origin https://<YOUR_TOKEN>@github.com/saipavan05/cureforge-pipeline.git
#   4. Run this script: bash scripts/push_ci_workflow.sh

set -e

echo "Pushing .github/workflows/ci.yml ..."
git add .github/workflows/ci.yml
git commit -m "CI: add GitHub Actions workflow (pytest on push/PR)"
git push origin main
echo "Done — CI workflow is live on GitHub."

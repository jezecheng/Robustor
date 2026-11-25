#!/usr/bin/env bash
# 端到端验收（M3）。前置：make install && make seed && make dev
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
API="${API:-http://localhost:8888}"
DEMO="apps/api/app/fixtures/demo"

echo "1) 健康检查"
curl -sf "$API/api/health" > /dev/null

echo "2) 上传 3 页样例"
RESP=$(curl -s -F "files=@${DEMO}/p1.jpg" -F "files=@${DEMO}/p2.jpg" \
            -F "files=@${DEMO}/p3.jpg" -F "subject=math" "$API/api/documents")
DOC=$(echo "$RESP" | jq -r .document_id)
JOB=$(echo "$RESP" | jq -r .job_id)
echo "   document=$DOC job=$JOB"

echo "3) 等待流水线"
STATUS=queued
for _ in $(seq 1 60); do
  STATUS=$(curl -s "$API/api/jobs/$JOB" | jq -r .status)
  if [ "$STATUS" = "done" ]; then break; fi
  if [ "$STATUS" = "failed" ]; then
    curl -s "$API/api/jobs/$JOB" | jq -r .error
    exit 1
  fi
  sleep 1
done
echo "   status=$STATUS"
[ "$STATUS" = "done" ] || { echo "job timeout"; exit 1; }

echo "4) 校验区域"
REGIONS=$(curl -s "$API/api/documents/$DOC/regions")
COUNT=$(echo "$REGIONS" | jq 'length')
TYPES=$(echo "$REGIONS" | jq -r '[.[].block_type] | unique | length')
echo "   regions=$COUNT block_types=$TYPES"
[ "$COUNT" -ge 5 ] || { echo "regions < 5"; exit 1; }
[ "$TYPES" -ge 5 ] || { echo "block types < 5"; exit 1; }

echo "5) 确认入库"
PID=$(curl -s -X POST -H 'content-type: application/json' \
      -d "{\"document_id\":\"$DOC\",\"region_ids\":[],\"stem_latex\":\"x^2-5x+6=0\",\"subject\":\"math\"}" \
      "$API/api/problems" | jq -r .id)
echo "   problem=$PID"
[ "$PID" != "null" ] || { echo "problem create failed"; exit 1; }

echo "6) 统计变化"
TOTAL=$(curl -s "$API/api/stats/overview" | jq -r .total)
echo "   total=$TOTAL"
[ "$TOTAL" -ge 1 ] || { echo "stats total < 1"; exit 1; }

echo "PASS"

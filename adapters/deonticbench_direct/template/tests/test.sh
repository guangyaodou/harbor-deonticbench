#!/bin/bash

set -euo pipefail

EXPECTED=$(cat /tests/expected_label.txt | tr -d '[:space:]')
ANSWER_FILE="/app/output/answer.txt"

mkdir -p /logs/verifier

if [ ! -f "$ANSWER_FILE" ]; then
    echo "No answer file found at $ANSWER_FILE"
    echo "0" > /logs/verifier/reward.txt
    exit 0
fi

ANSWER=$(grep -i "^Answer:" "$ANSWER_FILE" | sed 's/^[Aa]nswer:[[:space:]]*//' | tr -d '[:space:]' | tail -1)

echo "Expected: $EXPECTED"
echo "Got:      $ANSWER"

# Normalize for comparison:
# - If expected is an integer, strip decimal places from both sides
# - Otherwise, compare case-insensitively
if echo "$EXPECTED" | grep -qE '^-?[0-9]+$'; then
    EXPECTED_NORM="$EXPECTED"
    ANSWER_NORM=$(echo "$ANSWER" | sed 's/\..*//')
else
    EXPECTED_NORM=$(echo "$EXPECTED" | tr '[:upper:]' '[:lower:]')
    ANSWER_NORM=$(echo "$ANSWER" | tr '[:upper:]' '[:lower:]')
fi

echo "Normalized expected: $EXPECTED_NORM"
echo "Normalized got:      $ANSWER_NORM"

if [ "$ANSWER_NORM" = "$EXPECTED_NORM" ]; then
    echo "1" > /logs/verifier/reward.txt
else
    echo "0" > /logs/verifier/reward.txt
fi

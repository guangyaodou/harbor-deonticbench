#!/bin/bash
# Set up an SSH port-forward tunnel to a vLLM server running on a DSAI compute node.
#
# Usage:
#   bash deontic-scripts/vllm_tunnel.sh <compute-node>
#   bash deontic-scripts/vllm_tunnel.sh h06
#
# The compute node hostname is printed in the SLURM job log:
#   "Node hostname: h06"
#
# After this tunnel is running, the vLLM server is reachable at:
#   http://localhost:9009/v1
#
# To use with Harbor:
#   harbor run \
#     --path datasets/deonticbench-direct \
#     --agent terminus-2 \
#     --model openai/<model-name> \
#     --ae OPENAI_API_BASE=http://localhost:9009/v1 \
#     --ae OPENAI_API_KEY=token-abc123 \
#     --jobs-dir jobs/deontic-direct

set -euo pipefail

NODE="${1:-}"
PORT="${PORT:-9009}"

if [ -z "${NODE}" ]; then
    echo "Usage: bash deontic-scripts/vllm_tunnel.sh <compute-node>"
    echo "  Example: bash deontic-scripts/vllm_tunnel.sh h06"
    echo ""
    echo "Find the compute node in the SLURM job log: 'Node hostname: <node>'"
    exit 1
fi

echo "Forwarding localhost:${PORT} -> ${NODE}:${PORT} via dsai"
echo "Press Ctrl+C to stop the tunnel."
echo ""
echo "To check the tunnel and list served models (run in another terminal):"
echo "  curl -sf http://localhost:${PORT}/v1/models -H 'Authorization: Bearer token-abc123' | python3 -c \"import sys,json; [print(' ', m['id']) for m in json.load(sys.stdin)['data']]\""
echo ""

# Bind to 0.0.0.0 so Docker containers can reach the tunnel via 172.17.0.1
ssh -N -L "0.0.0.0:${PORT}:${NODE}:${PORT}" dsai

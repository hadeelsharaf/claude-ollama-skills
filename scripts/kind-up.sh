#!/usr/bin/env bash
# Opt-in, local-only. Stand up a throwaway kind cluster, deploy a deliberately
# crashlooping pod, capture the kubectl fixtures from REAL output, then tear down.
# Windows: run under Git Bash or WSL. Requires: docker, kind, kubectl.
# This is the graduated "test-environment provisioning" task (T9). It runs ALONE —
# do not have a second Ollama model loaded while a kind control plane is up.
set -euo pipefail

CLUSTER="ollama-skills-e2e"
FIX="$(cd "$(dirname "$0")/.." && pwd)/tests/fixtures/kubectl"

kind create cluster --name "$CLUSTER"

kubectl apply -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: crashloop
  namespace: default
  labels: { app: crashloop }
spec:
  containers:
    - name: api
      image: busybox:1.36
      env:
        - { name: API_TOKEN, value: SECRET_TOKEN_ENVMARKER }
        - { name: LOG_LEVEL, value: debug }
      command: ["sh", "-c", "echo starting api; echo 'ERROR could not connect to database: connection refused'; sleep 2; exit 1"]
YAML

echo "waiting for the pod to crashloop..."
sleep 40

kubectl get pods                                                  > "$FIX/get-pods.txt"
kubectl get pods -o json                                          > "$FIX/get-pods.json"
kubectl describe pod crashloop                                    > "$FIX/describe-pod-crashloop.txt"
kubectl get events --field-selector involvedObject.name=crashloop > "$FIX/events.txt"
kubectl logs crashloop --tail 200            > "$FIX/logs-crashloop.txt"          || true
kubectl logs crashloop --tail 200 --previous > "$FIX/logs-crashloop-previous.txt" || true

echo "fixtures written to $FIX — review them before committing."
kind delete cluster --name "$CLUSTER"
echo "done."

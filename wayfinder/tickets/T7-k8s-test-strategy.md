---
id: T7
title: "k8s test strategy on a machine with no cluster"
type: grilling
status: open
assignee: ""
blocked-by: [T5]
---

## Question

kubectl has zero contexts here. Decide how v0.2's k8s parts get tested: (a) kind
cluster inside the running Docker daemon (real e2e; needs a kind install task),
(b) canned kubectl output fixtures only (fast, no cluster, weaker), (c) both —
fixtures in CI, kind locally. Weigh RAM headroom (~6 GB free) against a kind
control plane (~500 MB–1 GB). The choice graduates the "test-environment
provisioning" fog into a task ticket or removes it.

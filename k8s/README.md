# Kubernetes manifests — Sprint 25-28

Plain manifests, not Helm — simpler to review line-by-line for a
single-environment deployment. Apply order matters (Secret/ConfigMap must
exist before the Deployments that reference them):

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
cp k8s/secret.example.yaml k8s/secret.yaml   # then fill in real values
kubectl apply -f k8s/secret.yaml             # never commit this file
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/api.yaml
kubectl apply -f k8s/worker.yaml
kubectl apply -f k8s/ingress.yaml
```

Build and push the image first (`api.yaml`/`worker.yaml` reference
`qrp-api:latest`):

```bash
docker build -t qrp-api:latest .
# push to your registry, or `kind load docker-image qrp-api:latest --name <cluster>`
# for local kind/minikube testing.
```

## What's real vs. what needs your environment

Verified in this session, against an actual local `kind` cluster and a real
`docker build`:
- The image builds and its full dependency set (including ones that were
  silently missing from `pyproject.toml` before this sprint — torch,
  sentence-transformers, prometheus-client, alembic, scikit-learn,
  lightgbm, xgboost, celery, redis, and a few more) actually installs.
- `/ready` and `/live` are real checks now (`/ready` does a genuine
  `SELECT 1` against the DB), not hardcoded "always healthy" responses —
  the `api.yaml` readiness/liveness probes wired to them mean something.
- The manifests are valid Kubernetes YAML (`kubectl apply` accepted them,
  redis reached Ready in the kind cluster).

Not fully verified end-to-end in this environment (slow/limited network
made a full `postgres` image pull + running pod time out during this
session, and there's no real ingress controller or cloud LoadBalancer
here): the api/worker Deployments actually reaching `Ready` in a live
cluster, and the Ingress routing real traffic. Both should be checked
against your actual cluster before relying on this for production traffic.

## Image size

`qrp-api:latest` is currently ~3.7GB (content) — mostly torch +
sentence-transformers + scikit-learn/xgboost/lightgbm. Worth revisiting:
a CPU-only torch wheel (`--index-url
https://download.pytorch.org/whl/cpu`) would shrink this substantially if
GPU inference is never needed, which matters for pod scheduling/scaling
speed under the HPA in `api.yaml`. Not done here — a real optimization
pass, not a quick edit.

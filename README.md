# Veeam Kasten — Kopia Repository Sizing Calculator

A self-hosted web application that estimates the Kopia repository capacity required to protect Kubernetes workloads with **Veeam Kasten**.

---

> [!CAUTION]
> **IMPORTANT — Estimation only.**
>
> This tool is provided for **informational and planning purposes only**. Results represent a
> directional estimate based on the inputs supplied and standard Kopia repository modelling
> assumptions. They do **not** constitute a commitment, guarantee, warranty, or contractual
> obligation of any kind by **Veeam Software** or any of its affiliates.
>
> Actual repository size and storage costs may differ significantly depending on real workload
> characteristics, data change patterns, Kopia version behaviour, object storage provider
> specifics, and maintenance scheduling.

---

## Table of contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Build the Docker image](#3-build-the-docker-image)
4. [Deploy on Kubernetes](#4-deploy-on-kubernetes)
   - 4.1 [Apply the manifest](#41-apply-the-manifest)
   - 4.2 [Service configuration](#42-service-configuration)
   - 4.3 [RBAC — why the app needs cluster access](#43-rbac--why-the-app-needs-cluster-access)
5. [How to use the application](#5-how-to-use-the-application)
   - 5.1 [Backup Policy Parameters (shared panel)](#51-backup-policy-parameters-shared-panel)
   - 5.2 [Manual Calculator tab](#52-manual-calculator-tab)
   - 5.3 [Cluster Scan tab](#53-cluster-scan-tab)
   - 5.4 [Capacity Planning chart](#54-capacity-planning-chart)
   - 5.5 [Downloading the PDF report](#55-downloading-the-pdf-report)
6. [Uninstall](#6-uninstall)

---

## 1. Overview

The tool implements the sizing formula from the official **K10 / Kopia Repository Sizing Calculator** spreadsheet:

```
S_repo ≈ κ × [ P × (1/DR) + Δ × (N_eff − 1 + L_snap + L_imm) ] × (1 + m) × (1 + ε)
```

| Symbol | Meaning |
|--------|---------|
| `P` | Primary PVC data (GiB) — per namespace |
| `κ = 1 − c` | Compression multiplier |
| `DR` | Deduplication ratio |
| `Δ = r × P / DR` | Per-snapshot delta |
| `N_eff = MAX(1, N_raw − O)` | Effective retained snapshots after overlap deduction |
| `L_snap = 2 × f` | GC catch-up buffer (2 full-maintenance cycles) |
| `L_imm = (imm + 20) × f` | Immutability buffer (0 when immutability is disabled) |
| `m = m_index + m_files` | Metadata overhead |
| `ε` | Compaction churn buffer (fixed at 5%) |

**Key features:**

- **Manual Calculator** — size a single namespace by entering its total PVC capacity and policy parameters.
- **Cluster Scan** — connects to the live cluster via the Kubernetes API, discovers all namespaces and their PVC capacities, lets you select which ones to protect, set workload types per PVC, and aggregates the total recommended repository size.
- **Storage Composition bar** — visual breakdown of Base / Historical / Metadata / Compaction / Headroom.
- **Capacity Planning chart** — shows repository growth from Day 0 to steady state.
- **PDF report** — one-click export of all inputs, per-namespace PVC details, results, charts, and the legal disclaimer.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Kubernetes ≥ 1.24 | Any distribution (k3s, RKE2, EKS, AKS, GKE, OCP …) |
| `kubectl` configured | Pointing to the target cluster |
| Container registry | Any registry reachable from the cluster (Docker Hub, Harbor, ECR, ACR …) |
| Docker or Podman | To build and push the image |

---

## 3. Build the Docker image

```bash
# Clone the repository
git clone https://github.com/<your-org>/kasten-sizing-tool.git
cd kasten-sizing-tool

# Build and push — edit REGISTRY and TAG as needed
REGISTRY="your-registry.example.com/library"
IMAGE="${REGISTRY}/kasten-sizing-tool"
TAG="latest"

docker build -t "${IMAGE}:${TAG}" .
docker push "${IMAGE}:${TAG}"
```

> The provided `build-push.sh` script is pre-configured for a private Harbor registry.
> Edit `REGISTRY` at the top of the script before using it.

---

## 4. Deploy on Kubernetes

### 4.1 Apply the manifest

The `sizing-tool.yaml` file creates:

- `Namespace` — `sizing-tool`
- `ServiceAccount` — used by the pod to query the Kubernetes API
- `ClusterRole` / `ClusterRoleBinding` — read-only access to `namespaces` and `persistentvolumeclaims`
- `Deployment` — single replica, ~64 MiB RAM
- `Service` — exposes port 80 → container port 8000

**Before applying**, edit `sizing-tool.yaml` to:

1. Replace the image reference with your registry:
   ```yaml
   image: your-registry.example.com/library/kasten-sizing-tool:latest
   ```
2. Configure the `Service` for your environment (see [section 4.2](#42-service-configuration)).

Then apply:

```bash
kubectl apply -f sizing-tool.yaml

# Verify the pod is running
kubectl get pods -n sizing-tool

# Check logs if the pod doesn't reach Running state
kubectl logs -n sizing-tool deployment/sizing-tool
```

---

### 4.2 Service configuration

The `Service` section in `sizing-tool.yaml` must be adapted to your cluster's ingress or load-balancer setup.
Four common options are shown below.

#### Option A — MetalLB (bare-metal, default in the manifest)

Assign a fixed IP from your MetalLB pool:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: sizing-tool
  namespace: sizing-tool
  annotations:
    metallb.io/loadBalancerIPs: "192.168.1.209"   # ← change to a free IP in your pool
spec:
  selector:
    app: sizing-tool
  ports:
    - port: 80
      targetPort: 8000
  type: LoadBalancer
```

Access the app at `http://192.168.1.209`.

---

#### Option B — Cloud provider LoadBalancer (EKS / AKS / GKE)

Remove the MetalLB annotation. The cloud provider will allocate an external IP automatically:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: sizing-tool
  namespace: sizing-tool
spec:
  selector:
    app: sizing-tool
  ports:
    - port: 80
      targetPort: 8000
  type: LoadBalancer
```

Find the assigned IP / hostname:

```bash
kubectl get svc -n sizing-tool sizing-tool
# EXTERNAL-IP will show the provisioned address once ready
```

---

#### Option C — NodePort (no load balancer)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: sizing-tool
  namespace: sizing-tool
spec:
  selector:
    app: sizing-tool
  ports:
    - port: 80
      targetPort: 8000
      nodePort: 30209        # choose any free port in 30000–32767
  type: NodePort
```

Access at `http://<any-node-IP>:30209`.

---

#### Option D — ClusterIP + `kubectl port-forward` (dev / test, no permanent exposure)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: sizing-tool
  namespace: sizing-tool
spec:
  selector:
    app: sizing-tool
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
```

Forward a local port on demand:

```bash
kubectl port-forward -n sizing-tool svc/sizing-tool 8080:80
# Then open http://localhost:8080 in your browser
# Press Ctrl+C to stop forwarding
```

---

#### Option E — Ingress

Keep the Service as `ClusterIP` (Option D above) and add an Ingress resource.
Adjust `host` and `ingressClassName` for your controller (nginx, traefik, etc.):

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sizing-tool
  namespace: sizing-tool
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
    - host: sizing-tool.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: sizing-tool
                port:
                  number: 80
```

---

### 4.3 RBAC — why the app needs cluster access

The **Cluster Scan** feature queries the Kubernetes API from inside the pod to list namespaces and PVC capacities. The provided `ClusterRole` grants **read-only** permissions to exactly two resources:

```yaml
rules:
- apiGroups: [""]
  resources: ["namespaces"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["persistentvolumeclaims"]
  verbs: ["get", "list"]
```

No write permissions are granted. If you only need the **Manual Calculator** tab, you can delete the `ClusterRole`, `ClusterRoleBinding`, and `ServiceAccount` resources — the app will start normally but the Cluster Scan feature will return a 503 error.

---

## 5. How to use the application

### 5.1 Backup Policy Parameters (shared panel)

The left panel is visible on both tabs and contains parameters that apply to all calculations:

| Field | Description | Default |
|-------|-------------|---------|
| **Backup cadence** | How often Kasten runs a backup (daily / 2×/day / 4×/day / hourly) | Daily |
| **Change rate basis** | Whether the change rate is expressed per day or per backup | Per backup |
| **Change rate** | Fraction of data that changes per backup (or per day) | 5% |
| **Compressibility c** | Fraction of data eliminated by Kopia compression *(Manual tab only)* | 10% |
| **Deduplication ratio DR** | Logical ÷ physical bytes after dedup *(Manual tab only)* | 1.1 |
| **Retention H / D / W / M / Y** | Number of hourly / daily / weekly / monthly / yearly restore points | D = 7 |
| **Immutability period (days)** | Location Profile Protection period. Kasten adds 20 days internally. Set to 0 to disable. | 0 |
| **Number of files (optional)** | Used for small-file metadata overhead. Leave 0 for block-mode volumes. | 0 |
| **Operational headroom** | Extra capacity above S_repo (10% = add 10%) | 10% |
| **Storage cost / GiB / month** | Used to estimate monthly and yearly object storage cost | $0.02 |

> **Compaction buffer ε** is fixed at **5%** and is not editable — this matches the reference spreadsheet default.
> **Index overhead m_index** is fixed at **1%** and is not editable.

---

### 5.2 Manual Calculator tab

Use this tab to size the repository for **one namespace at a time**.

1. Enter the **Total PVC capacity across protected namespace (GiB)** — sum of all PVC sizes that Kasten will back up in this namespace.
2. Set the workload type via **Compressibility c** and **Deduplication ratio DR** in the left panel (use the Reference tables at the bottom of the tab as a guide).
3. Results update in real time:
   - **Recommended capacity with headroom (GiB / TiB)** — the value to provision in your object storage.
   - **Repository size S_repo** — before headroom.
   - **Calculation steps** — every intermediate value in the formula.

Repeat for each namespace you plan to protect and sum the results manually — or use the **Cluster Scan** tab to do this automatically.

---

### 5.3 Cluster Scan tab

Use this tab to size the repository for **all namespaces** in one step.

**Step 1 — Scan**

Click **Scan Cluster**. The app queries the Kubernetes API and lists all namespaces with their PVC counts and total PVC capacity.

> The scan is **read-only** — it calls `list namespaces` and `list persistentvolumeclaims` only.

**Step 2 — Select namespaces and PVCs**

- Namespaces that have PVCs are pre-selected automatically.
- Click the **▶ expand arrow** on a namespace row to see its individual PVCs.
- Use the row checkboxes to include or exclude entire namespaces or individual PVCs.
  - A **filled checkbox** means all PVCs in that namespace are selected.
  - A **dash (indeterminate)** means only some PVCs are selected.

**Step 3 — Set workload type per PVC**

In the expanded PVC list, each PVC has a **Workload Type** dropdown. Select the type that best matches the data stored in that volume. The app applies the median compressibility (c) and deduplication ratio (DR) for that type:

| Workload Type | c (compressibility) | DR (dedup ratio) |
|---------------|---------------------|------------------|
| Text logs / YAML / JSON | 55% | 1.65 |
| Source code / scripts / docs | 45% | 1.40 |
| Web apps (mixed) | 30% | 1.20 |
| Databases (MySQL / PG) | 12.5% | 1.10 |
| Binary app data | 15% | 1.10 |
| Media files | 2.5% | 1.00 |
| Encrypted / random | 0% | 1.00 |

**Step 4 — Read the results**

Once at least one PVC is selected:

- **Storage Composition bar** — proportional breakdown of Base, Historical, Metadata, Compaction buffer, and Headroom.
- **Summary cards** — total recommended capacity in GiB and TiB, estimated monthly and yearly cost.
- **Per-namespace breakdown table** — S_repo and recommended capacity per namespace, with selected PVC counts.

---

### 5.4 Capacity Planning chart

Click **Capacity Planning** (next to the Download button) to open a chart showing how the repository grows from the first backup to steady state.

- **X-axis** — time (days / months / years)
- **Y-axis** — GiB
- **Stacked areas** — Base data (green), Historical deltas (blue), Metadata (purple), Compaction buffer (orange)
- **Headroom zone** — shaded grey area above S_repo up to recommended capacity
- **Dashed lines** — S_repo (purple) and Recommended capacity (grey)
- **Vertical markers** — Retention window end (green) and Immutability window end (orange, only shown when immutability > 0)

The x-axis extends to the later of the retention window and the immutability window, ensuring the full growth profile is visible.

---

### 5.5 Downloading the PDF report

Click **Download Report (PDF)** to generate a PDF containing:

- Generation date and time
- All backup policy parameters used
- Per-namespace PVC table with workload type, c, and DR per PVC
- Per-namespace S_repo and recommended capacity
- Summary totals (GiB, TiB, monthly and yearly cost)
- Storage Composition bar (SVG — colours always print correctly)
- Capacity Planning chart (SVG)
- Legal disclaimer

The report opens in a new browser tab and the **Print / Save as PDF** dialog opens automatically. In the dialog, set:

- **Destination** → Save as PDF
- **Paper size** → A4
- **Margins** → Default
- Enable **Background graphics** if the option is available (ensures the chart colours print)

If the print dialog does not open automatically, use the **Print / Save as PDF** button at the top of the report page.

---

## 6. Uninstall

```bash
kubectl delete -f sizing-tool.yaml
```

This removes the `sizing-tool` namespace and all resources within it (Deployment, Service, ServiceAccount, ClusterRole, ClusterRoleBinding).

---

> [!CAUTION]
> **IMPORTANT — Estimation only.**
>
> This tool is provided for **informational and planning purposes only**. Results represent a
> directional estimate based on the inputs supplied and standard Kopia repository modelling
> assumptions. They do **not** constitute a commitment, guarantee, warranty, or contractual
> obligation of any kind by **Veeam Software** or any of its affiliates.
>
> Actual repository size and storage costs may differ significantly depending on real workload
> characteristics, data change patterns, Kopia version behaviour, object storage provider
> specifics, and maintenance scheduling.

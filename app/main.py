#!/usr/bin/env python3
"""K10 / Kopia Repository Sizing Calculator"""

import logging
import re

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sizing-tool")

# Kubernetes client — optional, only needed for cluster scan
k8s_available = False
try:
    from kubernetes import client, config
    try:
        config.load_incluster_config()
        log.info("In-cluster config loaded")
    except Exception:
        try:
            config.load_kube_config()
            log.info("Local kubeconfig loaded")
        except Exception:
            log.warning("No kubeconfig found — cluster scan unavailable")
    k8s_available = True
except ImportError:
    log.warning("kubernetes package not installed — cluster scan unavailable")

app = FastAPI(title="K10 Sizing Calculator", docs_url=None, redoc_url=None)


def parse_storage_gib(q: str) -> float:
    """Convert a Kubernetes storage quantity string to GiB."""
    if not q:
        return 0.0
    m = re.match(r'^(\d+(?:\.\d+)?)([KMGTPE]i?)?$', str(q).strip())
    if not m:
        return 0.0
    val = float(m.group(1))
    suffix = m.group(2) or ''
    factors: dict[str, float] = {
        '':   1 / (1024 ** 3),
        'K':  1e3 / (1024 ** 3),
        'M':  1e6 / (1024 ** 3),
        'G':  1e9 / (1024 ** 3),
        'T':  1e12 / (1024 ** 3),
        'Ki': 1 / (1024 ** 2),
        'Mi': 1 / 1024,
        'Gi': 1.0,
        'Ti': 1024.0,
        'Pi': 1024.0 ** 2,
    }
    return val * factors.get(suffix, 1.0)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/namespaces")
def list_namespaces():
    if not k8s_available:
        raise HTTPException(status_code=503, detail="Kubernetes client not available")
    try:
        core = client.CoreV1Api()
        ns_list  = core.list_namespace()
        pvc_list = core.list_persistent_volume_claim_for_all_namespaces()

        pvc_by_ns: dict[str, list] = {}
        for pvc in pvc_list.items:
            ns = pvc.metadata.namespace
            storage = ""
            if pvc.spec.resources and pvc.spec.resources.requests:
                storage = pvc.spec.resources.requests.get("storage", "")
            pvc_by_ns.setdefault(ns, []).append({
                "name":    pvc.metadata.name,
                "storage": storage,
                "gib":     round(parse_storage_gib(storage), 3),
                "phase":   pvc.status.phase or "Unknown",
            })

        result = []
        for ns in ns_list.items:
            name  = ns.metadata.name
            pvcs  = pvc_by_ns.get(name, [])
            total = sum(p["gib"] for p in pvcs)
            result.append({
                "name":      name,
                "phase":     ns.status.phase or "Active",
                "pvc_count": len(pvcs),
                "total_gib": round(total, 3),
                "pvcs":      pvcs,
            })

        result.sort(key=lambda x: (-x["pvc_count"], x["name"]))
        return result
    except Exception as e:
        log.error("Error listing namespaces: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/", StaticFiles(directory="static", html=True), name="static")

"""Извлечь из HAR только релевантные запросы для t2v-recon.

Фильтры:
  - POST /api/v2/tasks/                     -> submit (тело payload)
  - POST .../config_history/                 -> config (тело)
  - GET  /api/v2/tasks/<id>/                 -> task_status (последний на task)
  - GET  /api/v2/queue-position/<id>/        -> queue (последний на task)
  - GET  /api/v2/storage-object/.../download-links

Дополнительно: группирует по task_id (если виден в URL/payload), пишет
по одному JSON-файлу на task в `parsed/`.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if len(sys.argv) < 2:
    print("usage: parse_har_t2v.py <path-to-har>")
    sys.exit(1)

HAR = Path(sys.argv[1])
OUT = HAR.parent / "parsed"
OUT.mkdir(exist_ok=True)

print(f"Reading {HAR} ({HAR.stat().st_size/1024/1024:.1f} MB)...")
data = json.loads(HAR.read_text(encoding="utf-8"))
entries = data["log"]["entries"]
print(f"Total entries: {len(entries)}")

TASK_URL = re.compile(r"/api/v2/tasks/(\d+)")
QUEUE_URL = re.compile(r"/api/v2/queue-position/(\d+)")
CONFIG_URL = re.compile(r"/api/v2/.*?/config_history")
DL_URL = re.compile(r"/api/v2/storage-object/.*download-links")
PRICE_URL = re.compile(r"/api/v2/.*?credits.*?price", re.IGNORECASE)


def body(req_or_res: dict) -> str | None:
    pd = req_or_res.get("postData") or req_or_res.get("content")
    if not pd:
        return None
    return pd.get("text")


def parse_json(s: str | None) -> object:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s[:500]


by_task: dict[str, list[dict]] = defaultdict(list)
orphan: list[dict] = []
submits: list[dict] = []
configs: list[dict] = []

for e in entries:
    req = e["request"]
    res = e["response"]
    url = req["url"]
    method = req["method"]
    status = res.get("status")

    rec_base = {
        "method": method,
        "url": url,
        "status": status,
        "started": e.get("startedDateTime"),
    }

    # Submit task
    if method == "POST" and url.endswith("/api/v2/tasks/"):
        rec = {
            **rec_base,
            "kind": "submit",
            "request_body": parse_json(body(req)),
            "response_body": parse_json(body(res)),
        }
        submits.append(rec)
        # task_id в response.id
        resp = rec["response_body"]
        if isinstance(resp, dict):
            tid = resp.get("id") or resp.get("task_id")
            if tid:
                by_task[str(tid)].append(rec)
                continue
        orphan.append(rec)
        continue

    # Config history
    if method == "POST" and CONFIG_URL.search(url):
        m = re.search(r"/(\d+)/config_history", url)
        tid = m.group(1) if m else None
        rec = {
            **rec_base,
            "kind": "config_history",
            "task_id": tid,
            "request_body": parse_json(body(req)),
        }
        configs.append(rec)
        if tid:
            by_task[tid].append(rec)
        else:
            orphan.append(rec)
        continue

    # Task status (GET /api/v2/tasks/<id>/)
    if method == "GET":
        m = TASK_URL.search(url)
        if m:
            tid = m.group(1)
            rec = {
                **rec_base,
                "kind": "task_status",
                "task_id": tid,
                "response_body": parse_json(body(res)),
            }
            by_task[tid].append(rec)
            continue
        m = QUEUE_URL.search(url)
        if m:
            tid = m.group(1)
            rec = {
                **rec_base,
                "kind": "queue_position",
                "task_id": tid,
                "response_body": parse_json(body(res)),
            }
            by_task[tid].append(rec)
            continue
        if DL_URL.search(url):
            rec = {
                **rec_base,
                "kind": "download_links",
                "response_body": parse_json(body(res)),
            }
            orphan.append(rec)
            continue

    # Price lookup (POST /api/v2/.../credits/price)
    if method == "POST" and PRICE_URL.search(url):
        rec = {
            **rec_base,
            "kind": "price",
            "request_body": parse_json(body(req)),
            "response_body": parse_json(body(res)),
        }
        orphan.append(rec)
        continue

# Write
print(f"\nFound submits: {len(submits)}")
for s in submits:
    rb = s["request_body"] if isinstance(s["request_body"], dict) else {}
    nid = rb.get("id")
    print(f"  -> node_id={nid} status={s['status']}")

print(f"Found configs: {len(configs)}")
print(f"Tasks grouped: {len(by_task)}")

# Сводка
summary = {
    "submits_count": len(submits),
    "configs_count": len(configs),
    "tasks": list(by_task.keys()),
    "submits_summary": [
        {
            "node_id": (s["request_body"] or {}).get("id") if isinstance(s["request_body"], dict) else None,
            "status": s["status"],
            "task_id": (s["response_body"] or {}).get("id") if isinstance(s["response_body"], dict) else None,
        }
        for s in submits
    ],
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nSummary -> {OUT/'summary.json'}")

# Один файл на submit (наш главный артефакт)
for i, s in enumerate(submits):
    rb = s["request_body"] if isinstance(s["request_body"], dict) else {}
    nid = rb.get("id", "unknown")
    resp = s["response_body"] if isinstance(s["response_body"], dict) else {}
    tid = resp.get("id", f"orphan{i}")
    fname = f"submit_node{nid}_task{tid}.json"
    (OUT / fname).write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {fname}")

for c in configs:
    tid = c.get("task_id", "unknown")
    fname = f"config_task{tid}.json"
    (OUT / fname).write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {fname}")

# По task — финальный task_status (тот, в котором последний раз видим outputs)
for tid, recs in by_task.items():
    statuses = [r for r in recs if r["kind"] == "task_status"]
    if not statuses:
        continue
    # последний по времени
    last = statuses[-1]
    fname = f"task{tid}_final_status.json"
    (OUT / fname).write_text(json.dumps(last, indent=2, ensure_ascii=False), encoding="utf-8")

orphan_path = OUT / "orphan.json"
orphan_path.write_text(json.dumps(orphan, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"  wrote orphan.json ({len(orphan)} entries)")

print("\nDone.")

"""Controlled local model experiment; no downloads and no private input."""

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import httpx

ROOT = Path(os.environ.get("RFQ_MODEL_BENCH_DIR", "docs/rfq/phase1_1/results/models"))
URL = "http://localhost:11434"


class Memory(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong)
        for name in (
            "total_physical",
            "available_physical",
            "total_page",
            "available_page",
            "total_virtual",
            "available_virtual",
            "available_extended",
        )
    ]


def sample():
    data = {"monotonic": time.monotonic()}
    try:
        values = (
            subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=3,
            )
            .strip()
            .split(",")
        )
        data.update(
            {
                "gpu_memory_mib": int(values[0]),
                "gpu_utilization_percent": int(values[1]),
            }
        )
        if os.name == "nt":
            memory = Memory()
            memory.length = ctypes.sizeof(memory)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
            data["system_ram_used_bytes"] = (
                memory.total_physical - memory.available_physical
            )
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return data


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=30, trust_env=False)
    tags = {m["name"]: m for m in client.get(URL + "/api/tags").json()["models"]}
    models = os.environ.get("RFQ_BENCH_MODELS", "qwen3:4b,qwen3:8b,qwen3.8:27b").split(
        ","
    )
    missing = [m for m in models if m not in tags]
    if missing:
        raise SystemExit("Models missing; no automatic download: " + str(missing))
    for model in models:
        client.post(URL + "/api/generate", json={"model": model, "keep_alive": 0})
    experiments = []
    selected_profile = os.environ.get("RFQ_BENCH_PROFILE", "compact")
    profiles = [(m, selected_profile) for m in models]
    if os.environ.get("RFQ_BENCH_INCLUDE_FULL", "1") == "1":
        profiles.append(("qwen3.8:27b", "full"))
    for model, profile in profiles:
        # Explicit unload makes the first call cold. The next document uses resident weights.
        for resident in client.get(URL + "/api/ps").json().get("models", []):
            client.post(
                URL + "/api/generate", json={"model": resident["name"], "keep_alive": 0}
            )
        detail = client.post(URL + "/api/show", json={"model": model}).json()
        name = model.replace(":", "-").replace(".", "_") + "-" + profile
        output = ROOT / (name + ".json")
        samples = []
        stop = threading.Event()

        def monitor():
            while not stop.is_set() and len(samples) < 1000:
                samples.append(sample())
                stop.wait(0.5)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        command = [
            sys.executable,
            "-m",
            "api.rfq.evaluation.quality_run",
            "--dataset",
            "data/evaluation/rfq-v2",
            "--split",
            "dev",
            "--mode",
            "llm",
            "--model",
            model,
            "--profile",
            profile,
            "--ids",
            "v2-03-00"
            if profile == "full" and os.environ.get("RFQ_BENCH_FULL_WARM", "0") == "0"
            else "v2-03-00,v2-03-01",
            "--output-tokens",
            "4096" if profile == "full" else "2048",
            "--output",
            str(output),
        ]
        completed = subprocess.run(command, check=False)
        stop.set()
        thread.join(timeout=5)
        resident = client.get(URL + "/api/ps").json()
        observed = subprocess.check_output(["ollama", "ps"], text=True)
        experiment = {
            "model": model,
            "profile": profile,
            "exit_code": completed.returncode,
            "tag": tags[model],
            "details": detail.get("details"),
            "model_info": {
                k: v
                for k, v in detail.get("model_info", {}).items()
                if "parameter_count" in k or "context_length" in k
            },
            "resident_after": resident,
            "ollama_ps": observed,
            "resource_samples": samples,
            "resource_scope": "Whole-GPU and whole-system RAM observations, not per-process allocation; first document cold, second warm with different content; no layer-count inference.",
        }
        (ROOT / (name + "-resources.json")).write_text(
            json.dumps(experiment, indent=2) + "\n", encoding="utf-8"
        )
        experiments.append(
            {
                "model": model,
                "profile": profile,
                "exit_code": completed.returncode,
                "report": str(output),
            }
        )
    (ROOT / "experiments.json").write_text(
        json.dumps(experiments, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

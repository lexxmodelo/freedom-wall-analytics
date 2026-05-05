"""Interactive launcher: `python -m topic_modeling`.

Menu-driven UI so a researcher can:
  1. Set up their researcher config (pick assigned files from a checkbox list).
  2. Run the embedding bake-off (one-time per project).
  3. Run the full pipeline (training + labeling).
  4. Show status (which universities are done, which are pending).
  5. Resume / re-run a single university.
  0. Quit.

`.env` autoload happens on entry so the API key is picked up without manual
exports. If no `.env` exists, the launcher walks the user through pasting
their key and writes it to topic_modeling/.env.

Designed for plain stdin/stdout — no extra deps, works in any terminal.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .checkpoint import checkpoint_exists, list_completed
from .dotenv import autoload as autoload_dotenv
from .io_utils import load_json, load_yaml, write_json


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONFIGS = ROOT / "configs"


# ---------- low-level UI helpers ----------

def _input(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or (default or "")


def _yesno(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    val = input(f"{prompt} ({d}): ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def _menu(title: str, options: list[tuple[str, str]]) -> str:
    """options: list of (key, label). Returns the chosen key."""
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)
    for k, lbl in options:
        print(f"  {k}. {lbl}")
    while True:
        choice = input("Choose: ").strip()
        if any(choice == k for k, _ in options):
            return choice
        print("Invalid choice. Try again.")


def _multiselect(title: str, items: list[tuple[str, str]]) -> list[str]:
    """items: list of (value, label). Returns chosen values.

    User enters comma-separated indices, 'all', or empty (none)."""
    print()
    print(title)
    for i, (val, lbl) in enumerate(items, start=1):
        print(f"  {i:2d}. {lbl}")
    print("  Enter comma-separated numbers (e.g. 1,3,4), 'all', or blank for none.")
    raw = input("Selection: ").strip().lower()
    if not raw:
        return []
    if raw == "all":
        return [v for v, _ in items]
    chosen: list[str] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok.isdigit():
            continue
        idx = int(tok)
        if 1 <= idx <= len(items):
            chosen.append(items[idx - 1][0])
    return chosen


# ---------- .env bootstrap ----------

def ensure_dotenv() -> None:
    autoload_dotenv(ROOT)
    if os.environ.get("NVIDIA_NIM_API_KEY"):
        return

    print()
    print("No NVIDIA_NIM_API_KEY found in environment or .env.")
    print("Get a free key at https://build.nvidia.com (sign up, generate API key).")
    print("Skipping for now is OK if you only want to run the bake-off (no API needed).")
    if not _yesno("Paste your API key now?", default=True):
        return
    key = input("Paste key (starts with nvapi-...): ").strip()
    if not key:
        print("No key entered. Continuing without one.")
        return
    env_path = ROOT / ".env"
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "NVIDIA_NIM_API_KEY" in existing:
        # Replace the line
        new_lines = []
        for line in existing.splitlines():
            if line.lstrip().startswith("NVIDIA_NIM_API_KEY"):
                new_lines.append(f"NVIDIA_NIM_API_KEY={key}")
            else:
                new_lines.append(line)
            content = "\n".join(new_lines) + "\n"
    else:
        content = (existing + ("\n" if existing and not existing.endswith("\n") else "")
                   + f"NVIDIA_NIM_API_KEY={key}\n")
    env_path.write_text(content, encoding="utf-8")
    os.environ["NVIDIA_NIM_API_KEY"] = key
    print(f"Saved to {env_path}.")


# ---------- listing helpers ----------

def list_active_files() -> list[tuple[str, str]]:
    """Return [(filename, "fname  ->  CODE  (alias, region)"), ...] for active mappings."""
    mapping = load_yaml(CONFIGS / "university_mapping.yaml")
    out: list[tuple[str, str]] = []
    for fname, m in mapping["mappings"].items():
        if not m.get("active", True):
            continue
        if str(m.get("code", "")).upper() == "TBD":
            continue
        label = f"{fname:30s} -> {m['code']:14s} ({m.get('school_alias', '?')}, {m.get('region', '?')})"
        out.append((fname, label))
    return out


def list_researcher_configs() -> list[str]:
    return sorted([p.stem for p in CONFIGS.glob("*.json")
                   if p.name not in ("bertopic_config.json", "gpu_config.json",
                                     "researcher_template.json")])


# ---------- actions ----------

def action_setup_researcher() -> None:
    print()
    print("--- Set up a new researcher config ---")
    rid = _input("Researcher ID (e.g. researcher_1, alexx, lead)", default="researcher_1")
    cfg_path = CONFIGS / f"{rid}.json"
    if cfg_path.exists():
        if not _yesno(f"{cfg_path.name} exists. Overwrite?", default=False):
            print("Cancelled.")
            return

    template = load_json(CONFIGS / "researcher_template.json")
    template["researcher_id"] = rid
    template["checkpoint_dir"] = f"checkpoints/{rid}"

    items = list_active_files()
    if not items:
        print("No active mappings found in university_mapping.yaml.")
        return
    chosen = _multiselect("Pick the universities you'll process:", items)
    if not chosen:
        print("No files selected; cancelled.")
        return
    template["assigned_files"] = chosen

    write_json(cfg_path, template)
    print(f"Wrote {cfg_path}")


def action_run_bakeoff() -> None:
    rid = pick_researcher("Run bake-off as which researcher?")
    if rid is None:
        return
    from .pipeline import load_config_bundle, run
    cfg = load_config_bundle(ROOT, rid, bakeoff_only=True)
    run(cfg)


def action_run_pipeline() -> None:
    rid = pick_researcher("Run full pipeline as which researcher?")
    if rid is None:
        return
    from .pipeline import load_config_bundle, run
    bertopic_cfg = load_json(CONFIGS / "bertopic_config.json")
    skip = bertopic_cfg.get("embedding_model_id") not in (None, "TBD_FROM_BAKEOFF")
    if skip:
        print(f"Embedding already locked: {bertopic_cfg['embedding_model_id']}")
    cfg = load_config_bundle(ROOT, rid, skip_bakeoff=skip)
    run(cfg)


def action_show_status() -> None:
    rid = pick_researcher("Show status for which researcher?", allow_none=True)
    print()
    print("--- Status ---")
    bertopic_cfg = load_json(CONFIGS / "bertopic_config.json")
    print(f"Locked embedding: {bertopic_cfg.get('embedding_model_id')}")
    print()
    items = list_active_files()
    print(f"Active mappings ({len(items)}):")
    for _, lbl in items:
        print(f"  {lbl}")
    if rid is None:
        return
    rcfg = load_json(CONFIGS / f"{rid}.json")
    cp_dir = ROOT / rcfg["checkpoint_dir"]
    done = set(list_completed(cp_dir))
    mapping = load_yaml(CONFIGS / "university_mapping.yaml")
    print()
    print(f"Researcher {rid} — assigned files:")
    for fname in rcfg["assigned_files"]:
        code = mapping["mappings"].get(fname, {}).get("code", "?")
        mark = "[DONE]" if code in done else "[pending]"
        print(f"  {mark} {fname} -> {code}")


def action_tune_gpu() -> None:
    """Interactive GPU/hardware tuning. Auto-detects the local GPU and offers
    presets covering the common cases (small/medium/large card, or no GPU at
    all). Falls back to per-key custom input. Writes configs/gpu_config.json
    after a confirmation step."""
    cfg_path = CONFIGS / "gpu_config.json"
    cfg = load_json(cfg_path)

    print()
    print("--- GPU / Hardware Tuning ---")

    # Auto-detect (only if torch is installed)
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram_mb = int(torch.cuda.get_device_properties(0).total_memory // (1024 * 1024))
            print(f"Detected GPU: {name} ({vram_mb} MB total VRAM)")
            if vram_mb < 9000:
                print("  -> Recommendation: preset 1 (small GPU)")
            elif vram_mb < 17000:
                print("  -> Recommendation: preset 2 (medium GPU)")
            else:
                print("  -> Recommendation: preset 3 (large GPU)")
        else:
            print("Detected: no CUDA GPU available")
            print("  -> Recommendation: preset 4 (no GPU)")
    except ImportError:
        print("torch not installed yet — auto-detect skipped. Pick the preset that matches your hardware.")

    print()
    print("Current settings:")
    print(f"  encode_batch_initial:        {cfg.get('encode_batch_initial')}")
    print(f"  large_corpus_initial_batch:  {cfg.get('large_corpus_initial_batch')}")
    print(f"  require_gpu_for_xlm_roberta: {cfg.get('require_gpu_for_xlm_roberta')}")
    print(f"  cpu_fallback_allowed:        {cfg.get('cpu_fallback_allowed')}")

    presets: list[tuple[str, str, dict | None]] = [
        ("1", "Small GPU (6-8 GB) — RTX 4050/4060 — defaults", {
            "encode_batch_initial": 16,
            "encode_batch_halving_sequence": [16, 8, 4],
            "large_corpus_initial_batch": 8,
            "require_gpu_for_xlm_roberta": True,
            "cpu_fallback_allowed": True,
        }),
        ("2", "Medium GPU (10-16 GB) — RTX 3080/4070/4080", {
            "encode_batch_initial": 32,
            "encode_batch_halving_sequence": [32, 16, 8],
            "large_corpus_initial_batch": 16,
            "require_gpu_for_xlm_roberta": True,
            "cpu_fallback_allowed": True,
        }),
        ("3", "Large GPU (24+ GB) — RTX 4090/A100", {
            "encode_batch_initial": 64,
            "encode_batch_halving_sequence": [64, 32, 16],
            "large_corpus_initial_batch": 32,
            "require_gpu_for_xlm_roberta": True,
            "cpu_fallback_allowed": True,
        }),
        ("4", "No GPU — CPU only (MiniLM will win bake-off; XLM-R-L too slow)", {
            "require_gpu_for_xlm_roberta": False,
            "cpu_fallback_allowed": True,
        }),
        ("5", "Custom (enter values manually)", None),
        ("0", "Cancel", None),
    ]

    print()
    print("Presets:")
    for k, lbl, _ in presets:
        print(f"  {k}. {lbl}")

    choice = input("Choose: ").strip()
    matched = next((p for p in presets if p[0] == choice), None)
    if matched is None:
        print("Invalid choice; cancelled.")
        return
    if choice == "0":
        return

    if choice == "5":
        updates: dict = {}
        for key, prompt, kind in [
            ("encode_batch_initial", "encode_batch_initial", "int"),
            ("large_corpus_initial_batch", "large_corpus_initial_batch", "int"),
            ("require_gpu_for_xlm_roberta", "require_gpu_for_xlm_roberta (true/false)", "bool"),
            ("cpu_fallback_allowed", "cpu_fallback_allowed (true/false)", "bool"),
        ]:
            val = input(f"  {prompt} [{cfg.get(key)}]: ").strip()
            if not val:
                continue
            if kind == "int":
                try:
                    updates[key] = int(val)
                except ValueError:
                    print(f"  invalid int; keeping {cfg.get(key)}")
            else:
                if val.lower() in ("true", "yes", "y", "1"):
                    updates[key] = True
                elif val.lower() in ("false", "no", "n", "0"):
                    updates[key] = False
                else:
                    print(f"  invalid bool; keeping {cfg.get(key)}")
        if not updates:
            print("No changes.")
            return
    else:
        updates = matched[2] or {}

    print()
    print("Changes to apply:")
    for k, v in updates.items():
        old = cfg.get(k)
        if old != v:
            print(f"  {k}: {old}  ->  {v}")
        else:
            print(f"  {k}: (unchanged) {v}")
    if not _yesno("Apply these changes?", default=True):
        print("Cancelled.")
        return

    cfg.update(updates)
    write_json(cfg_path, cfg)
    print(f"Wrote {cfg_path.relative_to(ROOT)}")


def action_clear_checkpoint() -> None:
    rid = pick_researcher("Clear checkpoint for which researcher?")
    if rid is None:
        return
    rcfg = load_json(CONFIGS / f"{rid}.json")
    cp_dir = ROOT / rcfg["checkpoint_dir"]
    done = list_completed(cp_dir)
    if not done:
        print(f"No completed checkpoints under {cp_dir}.")
        return
    items = [(c, c) for c in done]
    chosen = _multiselect("Pick checkpoints to clear (will force re-run):", items)
    for code in chosen:
        p = cp_dir / f"{code}_state.json"
        if p.exists():
            p.unlink()
            print(f"Removed {p}")


def pick_researcher(prompt: str, *, allow_none: bool = False) -> str | None:
    rids = list_researcher_configs()
    if not rids:
        print("No researcher configs found. Run option 1 to create one.")
        return None
    items = [(r, r) for r in rids]
    if allow_none:
        items.append(("__skip__", "(skip — show generic status only)"))
    print()
    print(prompt)
    for i, (val, lbl) in enumerate(items, start=1):
        print(f"  {i:2d}. {lbl}")
    raw = input("Choose: ").strip()
    if not raw.isdigit():
        return None
    idx = int(raw)
    if not (1 <= idx <= len(items)):
        return None
    val = items[idx - 1][0]
    return None if val == "__skip__" else val


# ---------- main loop ----------

MENU = [
    ("1", "Set up a researcher config"),
    ("2", "Run embedding bake-off (one-time)"),
    ("3", "Run full pipeline (train + label)"),
    ("4", "Show status / list checkpoints"),
    ("5", "Clear a checkpoint (force re-run)"),
    ("6", "GPU / hardware tuning"),
    ("0", "Quit"),
]


def main() -> int:
    ensure_dotenv()
    while True:
        choice = _menu("Topic Modeling — Interactive Launcher", MENU)
        try:
            if choice == "1":
                action_setup_researcher()
            elif choice == "2":
                action_run_bakeoff()
            elif choice == "3":
                action_run_pipeline()
            elif choice == "4":
                action_show_status()
            elif choice == "5":
                action_clear_checkpoint()
            elif choice == "6":
                action_tune_gpu()
            elif choice == "0":
                print("Bye.")
                return 0
        except KeyboardInterrupt:
            print("\nInterrupted; back to menu.")
        except Exception as e:
            import traceback
            print(f"\nERROR: {e}")
            traceback.print_exc()
            input("Press Enter to return to menu.")


if __name__ == "__main__":
    sys.exit(main())

"""Pure schedule, source-freeze and lossless archive helpers for repeated lab runs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import tarfile


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def source_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_sources(root, expected):
    for name, value in expected.items():
        if source_digest(root / name) != value:
            raise RuntimeError("Frozen source changed: " + name)


def make_cases(seed=20261126):
    rng = random.Random(seed)
    cases = []
    for round_index, node in enumerate(("w1", "w2", "w1"), 1):
        blocks = ["S0", "S1", "S2", "S3", "S4", "S5"]
        rng.shuffle(blocks)
        for family in blocks:
            variants = ["control", "action"] if family in ("S4", "S5") else ["action"]
            if family in ("S4", "S5") and round_index == 2:
                variants.reverse()
            for variant in variants:
                scenario = "S0" if variant == "control" else family
                args = ["--scenario", scenario, "--mode", "official", "--node", node,
                        "--warmup", "400", "--pre", "120", "--recovery", "120"]
                if family == "S0":
                    args.extend(["--measurement", "900"])
                elif family == "S2":
                    args.extend(["--s2-calls", "30"])
                elif family == "S3":
                    args.extend(["--s3-profile", "runtime", "--s3-rounds", "3"])
                elif family in ("S4", "S5"):
                    args.extend(["--loadgen-node", "w1", "--locust-seed", str(seed + round_index)])
                    if variant == "control":
                        args.append("--" + family.lower() + "-control")
                    if family == "S4":
                        args.extend(["--s4-duration", "90", "--s4-concurrency", "4"])
                        if variant == "action":
                            args.extend(["--s4-rate", "10"])
                    else:
                        args.extend(["--s5-calls", "60"])
                cases.append({"case_id": f"r{round_index}-{family.lower()}-{variant}",
                              "round": round_index, "family": family, "variant": variant,
                              "actor_node": node if family != "S0" else None,
                              "args": args, "timeout_seconds": 2400 if family == "S0" else 1800})
    return cases


def archive_run(run, runs_root):
    """Release disk only after a complete byte-for-byte round trip into a new archive."""
    run, runs_root = Path(run).resolve(), Path(runs_root).resolve()
    if run.parent != runs_root or run.is_symlink():
        raise ValueError("Archive target must be a direct owned run")
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed" or manifest.get("dataset_status") != "validated":
        raise ValueError("Retain failed or incomplete runs without repacking")
    destination = run / "dataset.tar.gz"
    if destination.exists():
        raise FileExistsError("Never overwrite an existing evidence archive")
    names = ("raw", "source", "normalized.ndjson", "labeled-windows.ndjson")
    files = sorted(p for name in names for p in ([run/name] if (run/name).is_file() else (run/name).rglob("*")) if p.is_file())
    if not files or not (run / "raw").is_dir():
        raise ValueError("No raw capture to archive")
    hashes = {}
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(run):
            raise ValueError("Symlink or escaped source")
        hashes[path.relative_to(run).as_posix()] = source_digest(path)
    partial = run / "dataset.tar.gz.partial"
    with tarfile.open(partial, "w:gz", compresslevel=3) as archive:
        for name in names:
            if (run/name).exists():
                archive.add(run/name, arcname=name)
    with tarfile.open(partial, "r:gz") as archive:
        members = {m.name: m for m in archive.getmembers() if m.isfile()}
        if set(members) != set(hashes):
            raise RuntimeError("Archive membership mismatch; plain files retained")
        for name, expected in hashes.items():
            digest = hashlib.sha256()
            with archive.extractfile(members[name]) as stream:
                while block := stream.read(1024*1024):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise RuntimeError("Archive content mismatch; plain files retained: " + name)
    partial.replace(destination)
    # All source bytes have been verified in the committed archive before unlinking.
    for path in files:
        path.unlink()
    for name in ("raw", "source"):
        folder = run/name
        if folder.is_dir():
            for directory in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p:len(p.parts), reverse=True):
                directory.rmdir()
            folder.rmdir()
    record = {"archive": destination.name, "archive_sha256": source_digest(destination),
              "verified_member_sha256": hashes, "plain_files_released_after_verification": True,
              "verified_at": now()}
    save(run / "archive-integrity.json", record)
    return record

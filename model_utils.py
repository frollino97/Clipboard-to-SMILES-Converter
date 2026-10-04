import os
from pathlib import Path


MODEL_REPOSITORY = "models--yujieq--MolScribe"
MODEL_FILENAME = "swin_base_char_aux_1m.pth"


def find_molscribe_checkpoint(resource_root: Path) -> Path:
    cache_roots = []
    for variable in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        cache_path = os.environ.get(variable)
        if cache_path:
            cache_roots.append(Path(cache_path))

    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        cache_roots.append(Path(hf_home) / "hub")

    cache_roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    model_roots = [resource_root / MODEL_REPOSITORY]
    model_roots.extend(cache_root / MODEL_REPOSITORY for cache_root in cache_roots)

    checkpoints = []
    for model_root in model_roots:
        checkpoints.extend(
            checkpoint
            for checkpoint in model_root.glob(f"snapshots/*/{MODEL_FILENAME}")
            if checkpoint.is_file()
        )

    if not checkpoints:
        expected_path = resource_root / MODEL_REPOSITORY / "snapshots" / "*" / MODEL_FILENAME
        raise FileNotFoundError(
            f"MolScribe model weights were not found. Expected them at "
            f"{expected_path} or in the Hugging Face model cache."
        )

    return max(checkpoints, key=lambda checkpoint: checkpoint.stat().st_mtime)

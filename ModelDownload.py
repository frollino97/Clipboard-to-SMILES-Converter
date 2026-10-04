from huggingface_hub import hf_hub_download

checkpoint_path = hf_hub_download(
    repo_id="yujieq/MolScribe",
    filename="swin_base_char_aux_1m.pth",
)
print(f"MolScribe checkpoint is ready: {checkpoint_path}")
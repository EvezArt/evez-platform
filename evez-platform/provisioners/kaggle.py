# EVEZ Kaggle GPU Notebook
!pip install torch transformers
import torch, json, time
print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None'}")

def run_sim():
    n = 10000
    pos = torch.randn(n, 3, device='cuda' if torch.cuda.is_available() else 'cpu')
    vel = torch.randn(n, 3, device=pos.device) * 0.1
    for i in range(1000):
        diff = pos.unsqueeze(0) - pos.unsqueeze(1)
        dist = torch.norm(diff, dim=2, keepdim=True) + 1e-6
        force = (diff / dist.pow(3)).sum(1)
        vel += force * 0.01
        pos += vel * 0.01
        if i % 100 == 0:
            print(f"Step {i}: E={0.5 * vel.pow(2).sum().item():.4f}")

run_sim()
print("Kaggle compute cycle complete")

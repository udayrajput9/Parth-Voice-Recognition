import sys
import os
import torch
from pathlib import Path

# Add third_party/aasist to sys.path
aasist_dir = Path("third_party/aasist").resolve()
sys.path.insert(0, str(aasist_dir))

try:
    from models import AASIST
    
    d_args = {
        "architecture": "AASIST",
        "nb_samp": 64600,
        "first_conv": 128,
        "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]],
        "gat_dims": [64, 32],
        "pool_ratios": [0.5, 0.7, 0.5, 0.5],
        "temperatures": [2.0, 2.0, 100.0, 100.0]
    }
    
    model = AASIST.Model(d_args)
    
    checkpoint_dir = Path("models/aasist/checkpoint")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    torch.save(model.state_dict(), checkpoint_dir / "best_model.pth")
    print("Successfully created mock AASIST checkpoint.")
except Exception as e:
    print(f"Error: {e}")

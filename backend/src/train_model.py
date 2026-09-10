import os
import cv2
import numpy as np
from pathlib import Path

def generate_augmented_sample(img: np.ndarray, mask: np.ndarray):
    """
    Applies spatial and color data augmentations to floorplan training samples:
    - Orthogonal Rotations (90, 180, 270 deg)
    - Horizontal/Vertical Flips
    - Random Color Inversion (dark-mode vs light-mode)
    - Random Contrast Scaling (CLAHE / Gain)
    """
    # 1. Random Rotation
    k = np.random.choice([0, 1, 2, 3])
    img_aug = np.rot90(img, k).copy()
    mask_aug = np.rot90(mask, k).copy()

    # 2. Random Flip
    if np.random.rand() > 0.5:
        img_aug = cv2.flip(img_aug, 1)
        mask_aug = cv2.flip(mask_aug, 1)
    if np.random.rand() > 0.5:
        img_aug = cv2.flip(img_aug, 0)
        mask_aug = cv2.flip(mask_aug, 0)

    # 3. Random Dark-Mode Inversion
    if np.random.rand() > 0.5:
        img_aug = 255 - img_aug

    # 4. Random Contrast adjustment
    alpha = np.random.uniform(0.8, 1.2)
    img_aug = np.clip(img_aug.astype(np.float32) * alpha, 0, 255).astype(np.uint8)

    return img_aug, mask_aug

def train_floorplan_model(epochs: int = 15, save_dir: str = None):
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        print("PyTorch is not installed yet. Skipping PyTorch training execution.")
        return

    save_dir = save_dir or str(Path(__file__).resolve().parent / "weights")
    os.makedirs(save_dir, exist_ok=True)
    weights_path = os.path.join(save_dir, "floorplan_model.pth")

    from services.floorplan_model import FloorplanMLService
    service = FloorplanMLService()
    model = service.model
    if model is None:
        print("Model architecture initialization failed.")
        return

    model.train()
    optimizer = optim.AdamW(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    print(f"Starting floorplan segmentation model training for {epochs} epochs...")

    # Create synthetic training tensors simulating multi-class floorplans
    for epoch in range(1, epochs + 1):
        running_loss = 0.0
        for batch in range(10):
            # Synthetic floorplan tile: 512x512
            img_tile = np.full((512, 512), 240, dtype=np.uint8)
            mask_tile = np.zeros((512, 512), dtype=np.int64)

            # Draw outer walls (black) & rooms (white)
            cv2.rectangle(img_tile, (50, 50), (450, 450), 30, 8)
            cv2.line(img_tile, (250, 50), (250, 450), 30, 6)

            # Class annotations: 1=room, 2=corridor, 3=stairs
            mask_tile[60:440, 60:240] = 1   # Room 1
            mask_tile[60:440, 260:440] = 2  # Corridor

            img_aug, mask_aug = generate_augmented_sample(img_tile, mask_tile)

            inp_t = torch.from_numpy(img_aug).float().unsqueeze(0).unsqueeze(0) / 255.0
            target_t = torch.from_numpy(mask_aug).long().unsqueeze(0)

            optimizer.zero_grad()
            out = model(inp_t)
            loss = criterion(out, target_t)
            loss.backward()
            optimizer.step()

            running_loss += loss.item()

        avg_loss = running_loss / 10
        print(f"Epoch [{epoch}/{epochs}] - Loss: {avg_loss:.4f}")

    torch.save(model.state_dict(), weights_path)
    print(f"Successfully trained and saved model weights to: {weights_path}")

if __name__ == "__main__":
    train_floorplan_model()

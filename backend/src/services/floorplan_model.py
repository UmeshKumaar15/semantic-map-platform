import os
import cv2
import numpy as np
import shapely.geometry as sg
from shapely.validation import make_valid
from pathlib import Path
from typing import List, Tuple, Dict, Any

CLASSES = ["background", "room", "corridor", "stairs", "elevator"]
CLASS_MAP = {1: "room", 2: "corridor", 3: "stairs", 4: "elevator"}

class FloorplanMLService:
    """
    Floorplan Machine Learning Segmentation Service.
    Loads PyTorch / ONNX trained model weights and produces multi-class spatial segmentations.
    """
    def __init__(self, weights_path: str = None):
        self.weights_path = weights_path or str(Path(__file__).resolve().parent.parent / "weights" / "floorplan_model.pth")
        self.model = None
        self.use_torch = False
        self._init_model()

    def _init_model(self):
        try:
            import torch
            import torch.nn as nn

            class SimpleSegmenter(nn.Module):
                def __init__(self, num_classes=5):
                    super().__init__()
                    self.enc1 = nn.Sequential(nn.Conv2d(1, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU())
                    self.enc2 = nn.Sequential(nn.Conv2d(32, 64, 3, padding=1, stride=2), nn.BatchNorm2d(64), nn.ReLU())
                    self.enc3 = nn.Sequential(nn.Conv2d(64, 128, 3, padding=1, stride=2), nn.BatchNorm2d(128), nn.ReLU())
                    self.dec2 = nn.Sequential(nn.ConvTranspose2d(128, 64, 4, stride=2, padding=1), nn.BatchNorm2d(64), nn.ReLU())
                    self.dec1 = nn.Sequential(nn.ConvTranspose2d(64, 32, 4, stride=2, padding=1), nn.BatchNorm2d(32), nn.ReLU())
                    self.final = nn.Conv2d(32, num_classes, 1)

                def forward(self, x):
                    e1 = self.enc1(x)
                    e2 = self.enc2(e1)
                    e3 = self.enc3(e2)
                    d2 = self.dec2(e3)
                    d1 = self.dec1(d2)
                    return self.final(d1)

            self.model = SimpleSegmenter(num_classes=5)
            if os.path.exists(self.weights_path):
                self.model.load_state_dict(torch.load(self.weights_path, map_location="cpu"))
                self.model.eval()
                self.use_torch = True
        except Exception as e:
            self.use_torch = False

    def predict_mask(self, img_gray: np.ndarray) -> np.ndarray:
        """
        Runs model inference on grayscale floorplan image and returns pixel class predictions.
        """
        h, w = img_gray.shape
        if self.use_torch and self.model is not None:
            import torch
            resized = cv2.resize(img_gray, (512, 512), interpolation=cv2.INTER_AREA)
            inp = torch.from_numpy(resized).float().unsqueeze(0).unsqueeze(0) / 255.0
            with torch.no_grad():
                out = self.model(inp)
                pred = torch.argmax(out, dim=1).squeeze(0).cpu().numpy().astype(np.uint8)
            return cv2.resize(pred, (w, h), interpolation=cv2.INTER_NEAREST)
        else:
            return np.zeros((h, w), dtype=np.uint8)

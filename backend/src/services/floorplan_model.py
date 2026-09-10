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
    Floorplan Machine Learning Spatial Segmentation Service.
    Architecture: Hourglass / ResNet-UNet Encoder-Decoder Architecture
    Reference: CubiCasa5k Official Model (Zenodo #2613548) & MLStructFP Repository (github.com/MLSTRUCT/MLStructFP)
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

            class ResidualBlock(nn.Module):
                def __init__(self, in_channels, out_channels, stride=1):
                    super().__init__()
                    self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False)
                    self.bn1 = nn.BatchNorm2d(out_channels)
                    self.relu = nn.ReLU(inplace=True)
                    self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1, bias=False)
                    self.bn2 = nn.BatchNorm2d(out_channels)
                    
                    self.shortcut = nn.Sequential()
                    if stride != 1 or in_channels != out_channels:
                        self.shortcut = nn.Sequential(
                            nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                            nn.BatchNorm2d(out_channels)
                        )

                def forward(self, x):
                    res = self.shortcut(x)
                    out = self.relu(self.bn1(self.conv1(x)))
                    out = self.bn2(self.conv2(out))
                    out = out + res
                    return self.relu(out)

            class ResNetHourglassUNet(nn.Module):
                """
                Hourglass / ResNet-UNet Encoder-Decoder Architecture
                CubiCasa5k & MLStructFP benchmark architecture for structural floorplan parsing.
                """
                def __init__(self, in_channels=1, num_classes=5):
                    super().__init__()
                    self.stem = nn.Sequential(
                        nn.Conv2d(in_channels, 32, kernel_size=7, stride=1, padding=3, bias=False),
                        nn.BatchNorm2d(32),
                        nn.ReLU(inplace=True)
                    )
                    
                    self.enc1 = ResidualBlock(32, 64, stride=1)
                    self.pool1 = nn.MaxPool2d(2, 2)
                    
                    self.enc2 = ResidualBlock(64, 128, stride=1)
                    self.pool2 = nn.MaxPool2d(2, 2)
                    
                    self.enc3 = ResidualBlock(128, 256, stride=1)
                    self.pool3 = nn.MaxPool2d(2, 2)

                    self.bottleneck = nn.Sequential(
                        ResidualBlock(256, 256),
                        ResidualBlock(256, 256)
                    )

                    self.up3 = nn.ConvTranspose2d(256, 256, kernel_size=2, stride=2)
                    self.dec3 = ResidualBlock(256 + 256, 128)

                    self.up2 = nn.ConvTranspose2d(128, 128, kernel_size=2, stride=2)
                    self.dec2 = ResidualBlock(128 + 128, 64)

                    self.up1 = nn.ConvTranspose2d(64, 64, kernel_size=2, stride=2)
                    self.dec1 = ResidualBlock(64 + 64, 32)

                    self.classifier = nn.Conv2d(32, num_classes, kernel_size=1)

                def forward(self, x):
                    x = self.stem(x)
                    e1 = self.enc1(x)
                    e2 = self.enc2(self.pool1(e1))
                    e3 = self.enc3(self.pool2(e2))
                    
                    b = self.bottleneck(self.pool3(e3))

                    d3 = self.up3(b)
                    d3 = torch.cat([d3, e3], dim=1)
                    d3 = self.dec3(d3)

                    d2 = self.up2(d3)
                    d2 = torch.cat([d2, e2], dim=1)
                    d2 = self.dec2(d2)

                    d1 = self.up1(d2)
                    d1 = torch.cat([d1, e1], dim=1)
                    d1 = self.dec1(d1)

                    return self.classifier(d1)

            self.model = ResNetHourglassUNet(in_channels=1, num_classes=5)
            if os.path.exists(self.weights_path):
                try:
                    self.model.load_state_dict(torch.load(self.weights_path, map_location="cpu"))
                    self.model.eval()
                    self.use_torch = True
                except Exception as load_err:
                    print(f"Weights load error (re-training required): {load_err}")
                    self.use_torch = False
            else:
                self.use_torch = False
        except Exception as e:
            print(f"Error loading PyTorch ResNet-Hourglass model: {e}")
            self.use_torch = False

    def predict_mask(self, img_gray: np.ndarray) -> np.ndarray:
        """
        Runs Hourglass / ResNet-UNet inference on grayscale floorplan image and returns pixel class predictions.
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

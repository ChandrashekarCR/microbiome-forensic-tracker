from pathlib import Path

from omegaconf import OmegaConf

config = OmegaConf.load(Path(__file__).parent / "config.yaml")

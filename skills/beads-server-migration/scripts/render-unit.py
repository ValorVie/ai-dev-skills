#!/usr/bin/env python3
"""Print the configured service unit; this command never installs it."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import target_config

parser = argparse.ArgumentParser()
parser.add_argument('--config', required=True, type=Path)
args = parser.parse_args()
print(target_config.render_unit(target_config.load(args.config)), end='')

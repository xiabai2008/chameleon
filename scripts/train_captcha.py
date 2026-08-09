"""验证码模板训练 CLI（P8-8）。

用法: uv run python scripts/train_captcha.py data/captcha_samples data/captcha_model.npz
"""

from __future__ import annotations

import sys

from chameleon.anti_detection.captcha_trainer import TemplateTrainer


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    sample_dir, model_path = sys.argv[1], sys.argv[2]
    summary = TemplateTrainer(sample_dir).train(model_path)
    print(f"训练完成: {summary['char_count']} 个字符模板 → {summary['path']}")


if __name__ == "__main__":
    main()

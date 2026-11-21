#!/usr/bin/env python3
"""Valida pares de contraste dos tokens GEDIV sem dependências externas.
Uso: python3 scripts/check_contrast.py [references/DESIGN_TOKENS.json]
Não substitui verificação visual real, inclusive em gráficos e overlays.
"""
import json
import sys
from pathlib import Path

def luminance(color):
    color = color.lstrip("#")
    if len(color) != 6:
        raise ValueError(f"hex RGB inválido: {color}")
    values = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    values = [n / 12.92 if n <= 0.04045 else ((n + 0.055) / 1.055) ** 2.4 for n in values]
    return .2126 * values[0] + .7152 * values[1] + .0722 * values[2]

def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + .05) / (lo + .05)

def main():
    default = Path(__file__).resolve().parents[1] / "references" / "DESIGN_TOKENS.json"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    data = json.loads(path.read_text(encoding="utf-8"))
    failed = 0
    for name in ("light", "dark"):
        print(f"\n{name.upper()}")
        colors = data[name]
        for item in data["test_pairs"]:
            f, b, minimum = item["foreground"], item["background"], item["minimum"]
            ratio = contrast(colors[f], colors[b])
            passed = ratio >= minimum
            failed += not passed
            print(f'{"OK" if passed else "FALHA"} {f}/{b}: {ratio:.2f}:1 (mín {minimum}:1)')
    print(f"\n{'APROVADO' if failed == 0 else 'REPROVADO'} — {failed} pares abaixo do mínimo")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()

"""Diagnóstico da estrutura do arquivo pontosLinha."""

import lzma
from pathlib import Path

RAIZ_EXT = Path("data") / "external"


def main() -> None:
    arquivos = sorted(RAIZ_EXT.glob("*ontosLinha*.json.xz"))
    if not arquivos:
        raise FileNotFoundError("Nenhum pontosLinha em data/external/.")

    arquivo = arquivos[-1]
    print("Arquivo:", arquivo.name)
    print()

    with lzma.open(arquivo, "rt", encoding="utf-8") as f:
        for i, linha in enumerate(f):
            print(f"--- linha {i + 1} ---")
            print(linha.strip()[:500])
            print()
            if i >= 4:
                break


if __name__ == "__main__":
    main()
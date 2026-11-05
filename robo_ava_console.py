"""Entrada do executável Windows: menu de texto, sem exigir Python no destino."""

from __future__ import annotations

import sys

from ava_py.__main__ import main


def menu() -> None:
    print("\nRobo AVA — console Windows")
    while True:
        print("\n1. Começar")
        print("0. Sair")
        try:
            choice = input("Escolha uma opção: ").strip()
        except EOFError:
            return
        if choice == "0":
            return
        if choice != "1":
            print("Opção inválida.")
            continue
        sys.argv = [sys.argv[0], "run", "--profile", "principal"]
        try:
            main()
        except SystemExit as exc:
            if str(exc) and str(exc) != "0":
                print(f"Aviso: {exc}")
        except KeyboardInterrupt:
            print("\nOperação interrompida. O progresso já registrado permanece salvo.")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        menu()
    else:
        main()

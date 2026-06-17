"""Emisor de licencias Ed25519 — USO INTERNO, NO se distribuye al cliente.

Flujo:

  # 1) Genera el par de claves UNA sola vez. Guarda la PRIVADA a buen
  #    recaudo (gestor de secretos); la pública va al .env del cliente.
  python tools/make_license.py keygen

  # 2) Pide al cliente su huella de equipo (la muestra el panel /license,
  #    o este mismo script con `fingerprint` corriendo en su máquina).
  python tools/make_license.py fingerprint

  # 3) Emite la licencia para ese cliente/equipo:
  python tools/make_license.py sign \
        --private <PRIVADA_B64> --client "Ayto. de X" \
        --fingerprint <FP> --days 365 --features regulador,analitica

Pon en el .env del cliente:
  PHOENIX_LICENSE_REQUIRED=true
  PHOENIX_LICENSE_PUBLIC_KEY=<PUBLICA_B64>
  PHOENIX_LICENSE_KEY=<la-licencia-firmada>

La PRIVADA nunca sale de aquí: por eso el cliente no puede fabricar licencias.
"""
import argparse
import sys
import time
from pathlib import Path

# Permitir importar el paquete del backend sin instalarlo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import licensing  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("keygen", help="Genera un par de claves Ed25519 (una vez).")
    sub.add_parser("fingerprint", help="Muestra la huella de ESTA máquina.")

    s = sub.add_parser("sign", help="Emite (firma) una licencia.")
    s.add_argument("--private", required=True, help="Clave privada (base64).")
    s.add_argument("--client", required=True, help="Nombre del cliente.")
    s.add_argument("--fingerprint", default="*",
                   help="Huella del equipo destino, o '*' para sin atar.")
    s.add_argument("--days", type=int, default=None,
                   help="Validez en días (omite para licencia perpetua).")
    s.add_argument("--features", default="*",
                   help="Lista de funciones separadas por coma (def: '*').")

    args = p.parse_args()

    if args.cmd == "keygen":
        priv, pub = licensing.generate_keypair()
        print("# Guarda la PRIVADA en secreto (NO al cliente):")
        print(f"PRIVATE_KEY={priv}")
        print("# La PÚBLICA va al .env del cliente:")
        print(f"PHOENIX_LICENSE_PUBLIC_KEY={pub}")
        return 0

    if args.cmd == "fingerprint":
        print(licensing.machine_fingerprint())
        return 0

    if args.cmd == "sign":
        exp = int(time.time()) + args.days * 86400 if args.days else None
        features = [f.strip() for f in args.features.split(",") if f.strip()]
        lic = licensing.generate_license(
            private_key_b64=args.private, client=args.client,
            fingerprint=args.fingerprint, expires_epoch=exp, features=features,
        )
        print(f"PHOENIX_LICENSE_KEY={lic}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())

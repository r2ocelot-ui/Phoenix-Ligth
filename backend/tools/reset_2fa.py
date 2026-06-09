"""Rescate de 2FA: quita el doble factor de un usuario por línea de comandos.

Para cuando alguien pierde el móvil Y las claves de recuperación. Requiere
acceso al servidor (a la base de datos), así que no es un agujero remoto:
quien puede ejecutar esto ya tiene la máquina.

Uso (desde la carpeta backend):
    python -m tools.reset_2fa <usuario>
    python -m tools.reset_2fa --list        # ver quién tiene 2FA activo
"""
import sys

from app.core.database import SessionLocal, init_db
from app.models.user import User


def main(argv: list[str]) -> int:
    init_db()
    with SessionLocal() as db:
        if not argv or argv[0] in ("-h", "--help"):
            print(__doc__)
            return 0
        if argv[0] == "--list":
            users = db.query(User).filter(User.totp_enabled.is_(True)).all()
            if not users:
                print("Ningún usuario tiene 2FA activado.")
            for u in users:
                print(f"  {u.username} · claves de recuperación restantes: {len(u.totp_recovery or [])}")
            return 0

        username = argv[0]
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"❌ Usuario '{username}' no encontrado.")
            return 1
        if not user.totp_enabled and not user.totp_secret:
            print(f"ℹ️  '{username}' no tiene 2FA configurado. Nada que hacer.")
            return 0
        user.totp_enabled = False
        user.totp_secret = None
        user.totp_recovery = []
        db.commit()
        print(f"✅ 2FA eliminado de '{username}'. Ya puede entrar sin código y reconfigurarlo.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

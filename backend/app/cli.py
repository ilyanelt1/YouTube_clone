import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Role, User


def main() -> None:
    parser = argparse.ArgumentParser(description="Управление ролями пользователей YouTube Clone")
    parser.add_argument("username", help="Имя пользователя")
    parser.add_argument("role", choices=("user", "moderator", "admin"), help="Назначаемая роль")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username.casefold()))
        role = db.scalar(select(Role).where(Role.name == args.role))
        if user is None:
            raise SystemExit(f"Пользователь @{args.username} не найден")
        if role is None:
            raise SystemExit(f"Роль {args.role} не найдена. Сначала выполните миграции.")
        if role not in user.roles:
            user.roles.append(role)
            db.commit()
        print(f"Роль {args.role} назначена пользователю @{user.username}")


if __name__ == "__main__":
    main()

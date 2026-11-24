"""Crear el primer usuario jefe y el registro de estación. Ejecutar una sola vez."""
import getpass
from app.db import Base, engine, SessionLocal
from app.models import User, Station
from app.security import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    if db.query(User).count():
        print("Ya existe al menos un usuario; no se creó otro administrador.")
    else:
        username = input("Usuario del Jefe de Estación: ").strip()
        full_name = input("Nombre completo: ").strip()
        password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
        if not username or not full_name or len(password) < 12:
            raise SystemExit("Datos incompletos o contraseña demasiado corta.")
        db.add(User(username=username, full_name=full_name, password_hash=hash_password(password), role="jefe_estacion"))
        if not db.query(Station).first():
            db.add(Station())
        db.commit()
        print("Usuario inicial creado. Inicie sesión y no comparta estas credenciales.")
finally:
    db.close()

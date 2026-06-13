from app.models import Base

print(f"Registered {len(Base.metadata.tables)} SQLAlchemy tables")

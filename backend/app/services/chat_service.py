# Re-export shim (CARD 3 refactor): real impl lives in app/services/chat/.
# Preserves the public surface `from app.services.chat_service import X` for all callers.
from app.services.chat import *

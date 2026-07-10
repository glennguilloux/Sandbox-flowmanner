# Chunk 9 Notepad — Issues

## Known Issues / Watch Items
- The plan references a nonexistent `test_community_models.py`; use `backend/tests/test_substrate_replay.py` instead.
- `deploy-backend.sh` has duplicate inline validation logic that must not be forgotten.
- `backend/Dockerfile` copies `scripts/` to `/app/scripts/`, so all snapshot scripts must live under `backend/scripts/`.
- `make validate-migration` currently fails on pre-existing drift; the new gate must make that silent.
- The active chunk is still `prompt-written-awaiting-deepseek`.

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass
class GenerationStore:
    path: Path
    data: Dict[str, Any]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _drafts(self) -> Dict[str, Dict[str, Any]]:
        drafts = self.data.setdefault("drafts", {})
        if not isinstance(drafts, dict):
            drafts = {}
            self.data["drafts"] = drafts
        return drafts

    def get_draft(self, draft_id: str) -> Optional[Dict[str, Any]]:
        raw = self._drafts().get(str(draft_id))
        if not isinstance(raw, dict):
            return None
        return copy.deepcopy(raw)

    def upsert_draft(
        self,
        *,
        user_id: int,
        template_code: str,
        answers: Dict[str, Any],
        draft_id: Optional[str] = None,
    ) -> str:
        now = _now_iso()
        uid = int(user_id)
        code = str(template_code)
        drafts = self._drafts()

        candidate_id = str(draft_id or "").strip()
        draft_raw = drafts.get(candidate_id) if candidate_id else None
        can_update_existing = (
            isinstance(draft_raw, dict)
            and _to_int(draft_raw.get("user_id"), default=-1) == uid
        )

        if can_update_existing:
            out_id = candidate_id
            draft = draft_raw
        else:
            out_id = uuid4().hex
            draft = {
                "draft_id": out_id,
                "user_id": uid,
                "template_code": code,
                "answers": {},
                "status": "ready",
                "attempts": 0,
                "last_error": "",
                "created_at": now,
                "updated_at": now,
            }

        draft["draft_id"] = out_id
        draft["user_id"] = uid
        draft["template_code"] = code
        draft["answers"] = copy.deepcopy(answers or {})
        draft["status"] = "ready"
        draft["last_error"] = ""
        draft["updated_at"] = now

        drafts[out_id] = draft
        self.save()
        return out_id

    def mark_attempt_started(self, draft_id: str) -> bool:
        draft = self._drafts().get(str(draft_id))
        if not isinstance(draft, dict):
            return False

        draft["attempts"] = _to_int(draft.get("attempts"), default=0) + 1
        draft["status"] = "processing"
        draft["last_error"] = ""
        draft["updated_at"] = _now_iso()
        self.save()
        return True

    def mark_failed(self, draft_id: str, error_text: str) -> bool:
        draft = self._drafts().get(str(draft_id))
        if not isinstance(draft, dict):
            return False

        draft["status"] = "failed"
        draft["last_error"] = str(error_text or "")[:1000]
        draft["updated_at"] = _now_iso()
        self.save()
        return True

    def mark_done(self, draft_id: str) -> bool:
        draft = self._drafts().get(str(draft_id))
        if not isinstance(draft, dict):
            return False

        draft["status"] = "done"
        draft["last_error"] = ""
        draft["updated_at"] = _now_iso()
        self.save()
        return True


def load_generation_store(path: Path) -> GenerationStore:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("generation drafts json is not an object")
        except Exception:
            data = {}
    else:
        data = {}

    data.setdefault("drafts", {})
    store = GenerationStore(path=path, data=data)
    if not path.exists():
        store.save()
    return store

import json
from typing import Dict

def json_dumps(obj: Dict) -> bytes:
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")

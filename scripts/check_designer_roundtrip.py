#!/usr/bin/env python3
"""Check that the Collection Designer can rewrite YAML definitions without changing them.

For every collection and template file it verifies, without any HTTP server:

  1. dump(load(file)) parses back to exactly the same dict (also after a JSON
     round trip – the path the model takes through the browser),
  2. the canonical output is stable (dumping it again changes nothing),
  3. templates resolve + normalize to the same structure before and after,
  4. the designer checks (lint + strict validation) accept the file.

It only reads – nothing is written. Run it before letting the designer loose on
hand-written definitions, or after changing designer_service.dump_yaml():

    python scripts/check_designer_roundtrip.py [collections_dir] [schemas_dir]
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uniforms.services import designer_service as ds  # noqa: E402
from uniforms.services.template_service import _normalize_template, _resolve_extends  # noqa: E402


def _normalized(data: dict, directory: Path) -> dict:
    return _normalize_template(_resolve_extends(copy.deepcopy(data), [directory]))


def main() -> int:
    collections_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data/collections")
    schemas_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "data/schemas")
    failures = 0
    files = sorted(collections_dir.glob("*.yaml")) + sorted(schemas_dir.glob("*/*.yaml"))
    for path in files:
        source = path.read_text(encoding="utf-8")
        data = yaml.safe_load(source)
        problems = []
        reason = ds.json_unsafe_reason(data) if isinstance(data, dict) else "not a mapping"
        if reason:
            print(f"SKIP  {path}  – raw editor only ({reason})")
            continue
        out = ds.dump_yaml(data, ds._split_header(source))
        if yaml.safe_load(out) != data:
            problems.append("dump changes the parsed content")
        if yaml.safe_load(ds.dump_yaml(json.loads(json.dumps(data)))) != data:
            problems.append("JSON round trip changes the content")
        if not ds.analyze_source(out, data)["canonical"]:
            problems.append("canonical output is not stable")
        info = ds.analyze_source(source, data)
        if path.parent == collections_dir:
            check = ds.check_collection(data, path.stem)
        else:
            check = ds.check_template(path.parent, copy.deepcopy(data), filename=path.name)
            with tempfile.TemporaryDirectory() as tmp:
                # rewrite the whole collection into a scratch dir and compare the runtime view
                for sibling in path.parent.glob("*.yaml"):
                    sib = yaml.safe_load(sibling.read_text(encoding="utf-8"))
                    (Path(tmp) / sibling.name).write_text(ds.dump_yaml(sib), encoding="utf-8")
                rewritten = yaml.safe_load((Path(tmp) / path.name).read_text(encoding="utf-8"))
                if _normalized(rewritten, Path(tmp)) != _normalized(data, path.parent):
                    problems.append("normalized template differs after rewrite")
        errors = [i["message"] for i in check["issues"] if i["level"] == "error"]
        problems += [f"designer check: {e}" for e in errors]
        status = "FAIL" if problems else "OK  "
        print(f"{status}  {path}  comments={info['comments']} (lost on rewrite: {info['comments_lost']})"
              f"  warnings={len(check['issues']) - len(errors)}")
        for problem in problems:
            print(f"        {problem}")
        failures += bool(problems)
    print(f"\n{len(files)} files checked, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

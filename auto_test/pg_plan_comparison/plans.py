"""Strict plan/measurement readers for three-table benchmark-derived cases."""

import hashlib
import json
import re


REAL_JOINS = {"HASH_JOIN", "NESTED_LOOP_JOIN", "BLOCKWISE_NL_JOIN",
              "PIECEWISE_MERGE_JOIN", "IE_JOIN", "CROSS_PRODUCT"}
PG_WRAPPERS = {"Hash", "Sort", "Incremental Sort", "Materialize", "Memoize"}
DUCK_WRAPPERS = {"PROJECTION", "FILTER", "ORDER_BY"}


def query_text(path):
    # Deliberately narrower than a SQL parser: these two queries have no strings,
    # subqueries, quoted identifiers, or inline/block comments.
    sql = "\n".join(line for line in path.read_text().splitlines()
                    if not line.lstrip().startswith("--")).strip()
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    if (not re.match(r"SELECT\b", sql, re.I) or
            re.search(r"[;'\"\\$]|--|/\*", sql) or
            len(re.findall(r"\bSELECT\b", sql, re.I)) != 1):
        raise ValueError("expected one simple SELECT: " + str(path))
    return sql


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pg_tree(node, schema, aliases, occurrences=None):
    kind = node["Node Type"]
    children = node.get("Plans", [])
    if kind in PG_WRAPPERS and len(children) == 1:
        return pg_tree(children[0], schema, aliases, occurrences)
    if kind in {"Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan"}:
        def bitmap(child):
            return child["Node Type"] in {"Bitmap Index Scan", "BitmapAnd", "BitmapOr"} and all(
                bitmap(c) for c in child.get("Plans", []))
        if children and (kind != "Bitmap Heap Scan" or not all(bitmap(c) for c in children)):
            raise ValueError("unexpected subtree beneath PG scan")
        if node.get("Schema") != schema:
            raise ValueError("PG scan resolved outside the experiment schema")
        relation = node["Relation Name"].lower()
        alias = node["Alias"].lower()
        if aliases.get(alias) != relation:
            raise ValueError("PG scan does not match the manifest's table/alias binding")
        return {"op": "scan", "schema": "public", "relation": relation,
                "alias": alias, "occurrence": occurrences[alias] if occurrences is not None else 0}
    if kind in {"Hash Join", "Merge Join", "Nested Loop"} and len(children) == 2:
        sides = {c.get("Parent Relationship"): c for c in children}
        join_type = node["Join Type"].lower()
        if set(sides) != {"Outer", "Inner"} or join_type not in {"inner", "left", "right", "full"}:
            raise ValueError("unsupported PG join orientation or type")
        return {"op": "join", "join_type": join_type,
                "left": pg_tree(sides["Outer"], schema, aliases, occurrences),
                "right": pg_tree(sides["Inner"], schema, aliases, occurrences)}
    raise ValueError("unsupported PG node: " + kind)


def nodes(tree):
    yield tree
    if tree["op"] == "join":
        yield from nodes(tree["left"])
        yield from nodes(tree["right"])


def leaves(tree):
    return frozenset(n["relation"] for n in nodes(tree) if n["op"] == "scan")


def validate_tree(tree, expected_relations=None):
    scans = [n["relation"] for n in nodes(tree) if n["op"] == "scan"]
    if len(scans) != 3 or len(set(scans)) != 3:
        raise ValueError("plan must contain exactly three distinct base tables")
    if expected_relations is not None and set(scans) != set(expected_relations):
        raise ValueError("plan does not match the manifest's base tables")


def grouping(tree):
    """Stable identities; discard join kinds, orientation, and unary wrappers."""
    if tree["op"] == "scan":
        return tree["relation"] + "#" + str(tree.get("occurrence", 0))
    return "(" + ",".join(sorted([grouping(tree["left"]), grouping(tree["right"])])) + ")"


def semantic(tree):
    if tree["op"] == "scan":
        return tree["relation"] + "#" + str(tree.get("occurrence", 0))
    left, right = semantic(tree["left"]), semantic(tree["right"])
    kind = tree["join_type"]
    if kind == "right":
        kind, left, right = "left", right, left
    elif kind in {"inner", "full"}:
        left, right = sorted([left, right])
    return f"{kind}({left},{right})"


def duck_tree(node, profiled=False):
    name = node["operator_name" if profiled else "name"].strip()
    children = node.get("children", [])
    info = node.get("extra_info", {})
    if name.startswith("SJ_") or name in DUCK_WRAPPERS:
        if len(children) != 1:
            raise ValueError("expected one data child for " + name)
        return duck_tree(children[0], profiled)
    if name in {"SEQ_SCAN", "TABLE_SCAN"} and not children:
        relation = info["Table"].split(".")[-1].lower()
        if relation.startswith('"') and relation.endswith('"'):
            relation = relation[1:-1].replace('""', '"')
        return {"op": "scan", "relation": relation}
    if name in REAL_JOINS and len(children) == 2:
        kind = info.get("Join Type", "").lower()
        if kind not in {"inner", "left", "right", "full"}:
            raise ValueError("unsupported DuckDB join kind: " + kind)
        result = {"op": "join", "join_type": kind,
                  "left": duck_tree(children[0], profiled),
                  "right": duck_tree(children[1], profiled)}
        if profiled:
            cards = [c.get("operator_cardinality") for c in children]
            cards.append(node.get("operator_cardinality"))
            if any(type(c) is not int or c < 0 for c in cards):
                raise ValueError("missing or invalid actual cardinality")
            result.update(input_rows=sum(cards[:2]), output_rows=cards[2])
        return result
    raise ValueError("unsupported DuckDB node: " + name)


def explain_tree(text, expected_relations=None):
    # DuckDB's CLI renders EXPLAIN specially even in CSV/JSON mode. It prints a
    # title before the JSON array; require one complete JSON value after it.
    start = text.find("[\n")
    if start < 0:
        raise ValueError("EXPLAIN FORMAT JSON array missing")
    parsed = json.loads(text[start:])
    if len(parsed) != 1:
        raise ValueError("expected one physical plan")
    tree = duck_tree(parsed[0])
    validate_tree(tree, expected_relations)
    return tree


def profile_metrics(profile, sql, expected_relations=None):
    if profile.get("query_name", "").strip().rstrip(";").strip() != sql:
        raise ValueError("profile does not belong to the bare query")
    if len(profile["children"]) != 1:
        raise ValueError("expected one profile root")
    tree = duck_tree(profile["children"][0], True)
    validate_tree(tree, expected_relations)
    joins = [n for n in nodes(tree) if n["op"] == "join"]
    return tree, {
        "real_join_input_rows": sum(n["input_rows"] for n in joins),
        "max_intermediate_rows": max(n["output_rows"] for n in joins),
        "max_nonroot_intermediate_rows": max((n["output_rows"] for n in joins[1:]), default=0),
        "result_rows": profile["rows_returned"],
    }


def decision(text):
    lines = [line for line in text.splitlines() if line.startswith("[OY_DECISION]")]
    if len(lines) != 1:
        raise ValueError("expected exactly one OuterYan decision record")
    return dict(re.findall(r"(\w+)=([^\s]+)", lines[0]))


def replay_verified(text, expected_count):
    events = []
    for line in text.splitlines():
        if line.startswith("[PGPLAN] "):
            events.append(json.loads(line[len("[PGPLAN] "):]))
    verified = [e for e in events if e.get("event") == "verified"]
    imported = [e for e in events if e.get("query_sha256_verified") is True]
    if len(verified) != expected_count or len(imported) != expected_count:
        raise ValueError("PG replay did not verify every execution")
    if any(e["expected_semantic_signature"] != e["final_semantic_signature"] for e in verified):
        raise ValueError("PG replay changed semantic signature")


def accepted_pair(text, base_relids, relations):
    """Associate accepted results with a two-base proposal, ignoring only known OJ RTEs."""
    ids = {int(k): v for k, v in base_relids.items()}
    expected, proposed = frozenset(relations), None
    for line in text.splitlines():
        if "PGOJ PAIR_PROPOSE " in line:
            match = re.search(r"union=\(b((?: \d+)*)\)", line)
            proposed = frozenset(ids[int(v)] for v in match[1].split() if int(v) in ids) if match else None
        elif "PGOJ PAIR_RESULT " in line:
            match = re.search(r"canonical=\(b((?: \d+)*)\)", line)
            actual = frozenset(ids[int(v)] for v in match[1].split() if int(v) in ids) if match else None
            if "accepted=1" in line and proposed == actual == expected:
                return True
            proposed = None
    return False


def trace_evidence(text, tree, case, base_relids):
    # RTE IDs follow the fixed SQL parse trees, including the lower JOIN RTE in
    # B. Do not infer base-table identities by removing arbitrary OJ numbers.
    ids = {int(k): v for k, v in base_relids.items()}

    def relset(line, key):
        match = re.search(r"\b" + key + r"=\(b((?: \d+)*)\)", line)
        return (frozenset(ids[int(v)] for v in match[1].split() if int(v) in ids)
                if match else frozenset())

    groups = {leaves(n) for n in nodes(tree) if n["op"] == "join" and len(leaves(n)) == 2}
    lines = [line[line.index("PGOJ "):] for line in text.splitlines() if "PGOJ " in line]
    evidence = {"status": "unproven", "critical_groups": [sorted(g) for g in sorted(groups, key=sorted)],
                "records": [], "rte_base_map": ids}
    if case == "A":
        for group in sorted(groups, key=sorted):
            outcomes, rejected, proposal = [], [], None
            for line in lines:
                if line.startswith("PGOJ PAIR_PROPOSE "):
                    proposal = relset(line, "union")
                elif (line.startswith("PGOJ LEGAL_REJECT ") and proposal == group
                      and relset(line, "candidate") == group):
                    rejected.append(line)
                elif line.startswith("PGOJ PAIR_RESULT "):
                    candidate = relset(line, "canonical" if "accepted=1" in line else "union")
                    if proposal == group and candidate == group:
                        outcomes.append("accepted=1" in line)
                    proposal = None
            # A two-base subset has only one unordered split. A rejection of
            # one split of a larger subset would not prove it unavailable.
            if rejected and outcomes and not any(outcomes):
                evidence.update(status="two_base_group_rejected", group=sorted(group), records=rejected)
                break
    else:
        for line in lines:
            if line.startswith("PGOJ FULL_BARRIER "):
                boundary = relset(line, "left") | relset(line, "right")
                for group in groups:
                    if group & boundary and group - boundary and boundary - group:
                        evidence.update(status="crosses_full_barrier", group=sorted(group),
                                        boundary=sorted(boundary))
                        evidence["records"].append(line)
    return evidence

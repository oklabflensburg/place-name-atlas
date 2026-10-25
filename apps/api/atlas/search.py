"""One filter compiler for list, statistics, exports and MVT."""
from atlas.schemas import Filter, Group, Pattern, normalize


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def literal_like(value: str) -> str:
    return escape_like(normalize(value))


def pattern_sql(pattern: Pattern, column: str, key: str, params: dict) -> str:
    value = literal_like(pattern.value)
    if pattern.mode == "suffix":
        column = "n.reversed" if column == "n.normalized" else f"reverse({column})"
        # Reversal is an index representation, not Unicode text to normalize again.
        value = escape_like(normalize(pattern.value)[::-1]) + "%"
    elif pattern.mode == "prefix":
        value += "%"
    elif pattern.mode == "contains":
        value = "%" + value + "%"
    if pattern.mode == "exact":
        params[key] = normalize(pattern.value)
        return f"{column} = :{key}"
    params[key] = value
    return f"{column} LIKE :{key} ESCAPE E'\\\\'"


def group_sql(group: Group, i: int, params: dict, admin: bool = False) -> str:
    def section(patterns, tag):
        expressions = [pattern_sql(p, "a.normalized_name" if admin else "n.normalized",
                                   f"g{i}_{tag}{j}", params) for j, p in enumerate(patterns)]
        sql = "(" + " OR ".join(expressions) + ")" if expressions else "FALSE"
        return sql if admin else f"EXISTS (SELECT 1 FROM place_name n WHERE n.record_id=p.id AND {sql})"
    return f"({section(group.patterns, 'p')} AND NOT {section(group.exclusions, 'e')})"


def compile_filter(f: Filter, dataset: str):
    params: dict = {"dataset": dataset}
    base = ["p.dataset_id=:dataset"]
    if f.kinds:
        params["kinds"] = f.kinds
        base.append("p.kind = ANY(:kinds)")
    if f.regions:
        params["regions"] = f.regions
        base.append("""EXISTS (SELECT 1 FROM admin_area r WHERE r.dataset_id=p.dataset_id
            AND r.identity_id=ANY(:regions) AND ST_Covers(r.geom,p.geom))""")
    if f.bbox:
        params.update(dict(zip(("west", "south", "east", "north"), f.bbox)))
        base.append("p.geom && ST_MakeEnvelope(:west,:south,:east,:north,4326)")
    groups = [group_sql(g, i, params) for i, g in enumerate(f.groups)]
    base_sql = " AND ".join(base)
    where = base_sql + (" AND (" + " OR ".join(groups) + ")" if groups else "")
    return base_sql, where, groups, params

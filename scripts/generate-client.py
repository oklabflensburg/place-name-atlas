"""Generate typed fetch operations from the checked OpenAPI document (no hand-maintained schemas)."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
schema=json.loads((root/"packages/api-client/openapi.json").read_text())

def ts(s):
    if "$ref" in s:
        return s["$ref"].split("/")[-1]
    if "anyOf" in s or "oneOf" in s:
        return " | ".join(ts(x) for x in s.get("anyOf",s.get("oneOf")))
    if "enum" in s:
        return " | ".join(json.dumps(v) for v in s["enum"])
    if "const" in s:
        return json.dumps(s["const"])
    kind=s.get("type")
    if kind=="array":
        if "prefixItems" in s:
            return "["+", ".join(ts(x) for x in s["prefixItems"])+"]"
        return "Array<"+ts(s.get("items",{}))+">"
    if kind=="object" or "properties" in s:
        if "properties" in s:
            fields=[]
            for name,prop in s["properties"].items():
                # The application serializes complete models, including defaulted fields.
                optional=""
                fields.append(f"{json.dumps(name)}{optional}: {ts(prop)}")
            return "{ "+"; ".join(fields)+" }"
        additional=s.get("additionalProperties")
        return "Record<string, "+(ts(additional) if isinstance(additional,dict) else "unknown")+">"
    return {"string":"string","number":"number","integer":"number","boolean":"boolean","null":"null"}.get(kind,"unknown")

parts=["// Generated from openapi.json by scripts/generate-client.py. Do not edit."]
for name,value in schema["components"]["schemas"].items():
    parts.append(f"export type {name} = {ts(value)}")
operations=[]
for path,methods in schema["paths"].items():
    if "get" not in methods:
        continue
    op=methods["get"]
    content=op["responses"].get("200",{}).get("content",{})
    response=content.get("application/json",{}).get("schema",{})
    response_type=ts(response) if "application/json" in content else "Response"
    params=[]
    for p in op.get("parameters",[]):
        params.append(f"{json.dumps(p['name'])}{'' if p.get('required') else '?'}: {ts(p['schema'])}")
    operations.append(f"{json.dumps(path)}: {{ params: {{ {'; '.join(params)} }}; response: {response_type} }}")
parts.append("export interface Operations {\n  "+"\n  ".join(operations)+"\n}")
parts.append('''
export async function api<P extends keyof Operations>(path: P, params: Operations[P]['params'] = {} as Operations[P]['params'], init: RequestInit = {}): Promise<Operations[P]['response']> {
  let url: string = path
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    if (url.includes(`{${key}}`)) url = url.replace(`{${key}}`, encodeURIComponent(String(value)))
    else query.set(key, String(value))
  }
  const response = await fetch(`${url}${query.size ? '?' + query.toString() : ''}`, init)
  if (!response.ok) {
    const body: { message?: string } = await response.json().catch(() => ({}))
    throw new Error(body.message || `Anfrage fehlgeschlagen (${response.status})`)
  }
  if (!response.headers.get('content-type')?.includes('application/json')) return response as Operations[P]['response']
  // Read the body before timing JSON parsing, so transfer is not charged to parsing.
  const bytes = await response.arrayBuffer()
  const start = performance.now()
  const result = JSON.parse(new TextDecoder().decode(bytes))
  performance.measure('atlas:json', { start, end: performance.now(), detail: { path, bytes: bytes.byteLength } })
  return result as Operations[P]['response']
}
''')
(root/"packages/api-client/index.ts").write_text("\n\n".join(parts))

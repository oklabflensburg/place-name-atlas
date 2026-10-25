"""Audit fixed GN250 source and import selection without changing a database."""
import csv,hashlib,json
from collections import Counter
from pathlib import Path
from atlas.schemas import normalize
root=Path(__file__).resolve().parents[1]
manifest_path=root/'data/manifest-r3.json'
manifest=json.loads(manifest_path.read_text())
source=next(s for s in manifest['sources'] if s['product']=='GN250')
path=manifest_path.parent/source['path']
with path.open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f,delimiter=';'))
settlements=[r for r in rows if r['OBA']=='AX_Ortslage']
real=[r for r in settlements if r['VIRTUELL']!='Ja' and r['NAME'].strip()]
archive=manifest_path.parent/source['archive']
assert hashlib.sha256(archive.read_bytes()).hexdigest()==source['sha256']
assert not manifest.get('municipalities'), 'This audit expects a national import'
assert len({r['NNID'] for r in real})==len(real)
endings=['ach','ingen','zell','heim','hausen','dorf','bach','itz','ow','by']
counts={s:sum(any(normalize(n).endswith(s) for n in [r['NAME'],r['NAME2']] if n) for r in real) for s in endings}
result={'source':source['url'],'archive_sha256':source['sha256'],'manifest':str(manifest_path.relative_to(root)),
    'all_source_rows':len(rows),'ortslage_rows':len(settlements),'virtual_excluded':sum(r['VIRTUELL']=='Ja' for r in settlements),
    'invalid_name_excluded':sum(not r['NAME'].strip() for r in settlements if r['VIRTUELL']!='Ja'),
    'accepted':len(real),'unique_NNID':len({r['NNID'] for r in real}),'GEMTEIL':dict(Counter(r['GEMTEIL'] for r in real)),
    'with_alternative_name':sum(bool(r['NAME2']) for r in real),'municipality_subset':manifest.get('municipalities',[]),
    'AX_Gemeinde_not_counted_as_settlement':sum(r['OBA']=='AX_Gemeinde' for r in rows),'suffix_counts':counts,
    'conclusion':'9790 equals GEMTEIL=Nein; default must also include 36068 GEMTEIL=Ja. No source subset or invented objects. NNID identities, never merge by name.'}
(root/'docs/reports/gn250-selection-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))

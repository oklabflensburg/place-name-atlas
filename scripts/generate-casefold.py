"""Browser casefold uses exactly the backend's Unicode table (not locale lowercasing)."""
import json,unicodedata
from pathlib import Path
mapping={chr(i):chr(i).casefold() for i in range(0x110000) if chr(i).casefold()!=chr(i).lower()}
Path('apps/web/app/utils/casefold.json').write_text(json.dumps(mapping,ensure_ascii=False,separators=(',',':'))+'\n')
print(unicodedata.unidata_version,len(mapping))

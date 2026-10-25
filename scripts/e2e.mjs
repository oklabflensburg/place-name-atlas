// Full-stack E2E entrypoint: install the locked Python environment before starting services.
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
const result=spawnSync('uv',['sync','--cache-dir','/tmp/atlas-uv-cache',...(existsSync('uv.lock')?['--locked']:[])],{stdio:'inherit',env:process.env})
if(result.status!==0)process.exit(result.status||1)
if(process.argv.includes('--status')) {
  const check=spawnSync('.venv/bin/python',['scripts/local-status.py'],{stdio:'inherit',env:process.env})
  process.exit(check.status||0)
}
if(process.argv.includes('--cancel-import')) {
  const check=spawnSync('.venv/bin/python',['scripts/cancel-local-import.py'],{stdio:'inherit',env:process.env})
  process.exit(check.status||0)
}
if(process.argv.includes('--production'))process.env.TEST_PRODUCTION='1'
if(process.argv.includes('--backend')) {
  const check=spawnSync('.venv/bin/python',['scripts/local-checks.py'],{stdio:'inherit',env:process.env})
  process.exit(check.status||0)
}
if(process.argv.includes('--restore')) {
  const check=spawnSync('.venv/bin/python',['scripts/backup-restore-check.py'],{stdio:'inherit',env:process.env})
  process.exit(check.status||0)
}
if(process.argv.includes('--restore-real')) {
  const check=spawnSync('.venv/bin/python',['scripts/backup-restore-check.py'],{stdio:'inherit',env:{...process.env,RESTORE_SOURCE_DATABASE:'atlas_dev'}})
  process.exit(check.status||0)
}
if(process.argv.includes('--benchmark')) {
  const check=spawnSync('.venv/bin/python',['scripts/benchmark.py','--url','postgresql+psycopg://atlas_runtime@127.0.0.1:55439/atlas_dev'],{stdio:'inherit',env:{...process.env,PYTHONPATH:'apps/api'}})
  process.exit(check.status||0)
}
if(process.argv.includes('--benchmark-short')) {
  const check=spawnSync('.venv/bin/python',['scripts/benchmark.py','--short-only','--url','postgresql+psycopg://atlas_runtime@127.0.0.1:55439/atlas_dev'],{stdio:'inherit',env:{...process.env,PYTHONPATH:'apps/api'}})
  process.exit(check.status||0)
}
if(process.argv.includes('--import-bkg')) {
  const check=spawnSync('.venv/bin/python',['scripts/import-local.py'],{stdio:'inherit',env:{...process.env,PYTHONPATH:'apps/api'}})
  process.exit(check.status||0)
}
if(process.argv.includes('--real-fixture')) {
  const check=spawnSync('.venv/bin/python',['scripts/create-real-fixture.py'],{stdio:'inherit',env:{...process.env,PYTHONPATH:'apps/api'}})
  process.exit(check.status||0)
}
if(process.argv.includes('--check-published')) {
  const check=spawnSync('.venv/bin/python',['scripts/check-published-data.py'],{stdio:'inherit',env:process.env})
  process.exit(check.status||0)
}
if(process.argv.includes('--real-browser')) {
  const check=spawnSync('pnpm',['exec','playwright','test','--config','playwright.real.config.ts'],{stdio:'inherit',env:process.env})
  process.exit(check.status||0)
}
if(process.argv.includes('--preview-real')) {
  const check=spawnSync('node',['scripts/preview.mjs'],{stdio:'inherit',env:process.env})
  process.exit(check.status||0)
}
if(!process.argv.includes('--prepare')) {
  const test=spawnSync('pnpm',['exec','playwright','test',...process.argv.slice(2).filter(v=>v!=='--production')],{stdio:'inherit',env:process.env})
  process.exit(test.status||0)
}

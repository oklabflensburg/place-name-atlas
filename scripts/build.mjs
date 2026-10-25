import {spawnSync} from 'node:child_process'
import {writeFileSync} from 'node:fs'
import {join} from 'node:path'
import {root,webBuild} from './local-runtime.mjs'
const before=webBuild()
const result=spawnSync('pnpm',['--filter','@atlas/web','build'],{cwd:root,stdio:'inherit'})
if(result.status!==0)process.exit(result.status||1)
if(before!==webBuild())throw new Error('Quelldateien wurden während des Builds geändert. Bitte pnpm build wiederholen.')
writeFileSync(join(root,'apps/web/.output/atlas-build.json'),JSON.stringify({build:before})+'\n')

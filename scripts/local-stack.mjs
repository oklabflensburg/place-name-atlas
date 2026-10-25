// The manager owns only children it spawns. Existing identified services are borrowed.
import {spawn} from 'node:child_process'
import {mkdirSync,readFileSync,writeFileSync,rmSync,existsSync} from 'node:fs'
import {join} from 'node:path'
import {setTimeout as delay} from 'node:timers/promises'
import {pathToFileURL} from 'node:url'
import {writeNginxConfig} from './serve-nginx.mjs'
import {root,config,runtime,entry,project,identities,planServices,jsonAt,matches,processIdentity,liveManager} from './local-runtime.mjs'

export class Children {
  items=[]; stopping=false
  constructor(spawnChild=spawn,signal=(pid,signal)=>process.kill(pid,signal)){this.spawnChild=spawnChild;this.signal=signal}
  start(command,args,options={}){
    if(this.stopping)throw new Error('Projekt wird beendet; keine weiteren Dienste gestartet.')
    const child=this.spawnChild(command,args,{cwd:root,stdio:'inherit',detached:true,...options})
    this.items.push(child)
    return child
  }
  async stop(){
    if(this.stopping)return
    this.stopping=true
    await Promise.all(this.items.map(child=>new Promise(resolve=>{
      if(child.exitCode!==null||child.signalCode){resolve();return}
      const timer=setTimeout(()=>{try{this.signal(-child.pid,'SIGKILL')}catch{}},8000)
      child.once('exit',()=>{clearTimeout(timer);resolve()})
      child.once('error',()=>{clearTimeout(timer);resolve()})
      try{this.signal(-child.pid,child.spawnfile==='nginx'?'SIGQUIT':'SIGTERM')}catch{clearTimeout(timer);resolve()}
    })))
  }
}
export async function startStack(mode='preview'){
  process.chdir(root)
  const expected=identities(mode),children=new Children()
  if(mode==='preview'){
    let built
    try{built=JSON.parse(readFileSync('apps/web/.output/atlas-build.json','utf8'))}catch{}
    if(!built||built.build!==expected.web.build)throw new Error('Produktionsbuild fehlt oder ist veraltet. Zuerst pnpm build ausführen.')
  }
  mkdirSync(runtime,{recursive:true})
  const lock=join(runtime,'manager'),recordPath=join(lock,'instance.json')
  let locked=false,finished=false,shutdown
  const stop=(code=0)=>{
    if(shutdown)return shutdown
    finished=true
    shutdown=(async()=>{
      await children.stop()
      if(locked)rmSync(lock,{recursive:true,force:true})
      process.exitCode=code
    })()
    return shutdown
  }
  try{
    if(existsSync(lock)){
      let old
      try{old=JSON.parse(readFileSync(recordPath,'utf8'))}catch{throw new Error('Ein Projektstart wird gerade vorbereitet. Kurz warten und erneut starten; keine zweite Instanz angelegt.')}
      if(liveManager(old)){
        if(old.mode!==mode)throw new Error(`Der Projektmanager läuft bereits im Modus ${old.mode}. Mit pnpm local:stop regulär beenden, bevor der Modus gewechselt wird.`)
        const plan=await planServices(expected)
        if(plan.every(s=>s.reuse)){await verifyApi();console.log(`Projekt läuft bereits: ${entry}. Keine weitere Instanz gestartet.`);return}
        throw new Error('Projektmanager läuft, aber die Dienste sind noch nicht bereit. pnpm local:status zeigt den Zustand.')
      }
      rmSync(lock,{recursive:true})
    }
    mkdirSync(lock);locked=true
    writeFileSync(recordPath,JSON.stringify({pid:process.pid,startTime:processIdentity(process.pid),root,project,mode})+'\n')
    // Inspect every port before starting the first child.
    const plan=await planServices(expected)
    if(plan.every(s=>s.reuse)){await verifyApi();console.log(`Projekt läuft bereits: ${entry}. Keine weitere Instanz gestartet.`);await stop();return}
    for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{void stop()})
    const launch=async(service,command,args,environment={})=>{
      const env={...process.env,...environment}
      if(mode==='dev'&&service.name==='web')for(const key of ['PORT','NUXT_PORT','NITRO_PORT'])delete env[key]
      const child=children.start(command,args,{env})
      let failure
      child.once('error',e=>{failure=e;void stop(1)})
      child.once('exit',(code,signal)=>{if(!children.stopping){failure=new Error(`${service.name} wurde beendet (${code??signal}).`);console.error(failure.message);void stop(1)}})
      const deadline=Date.now()+120000
      while(Date.now()<deadline){
        if(failure||finished)throw failure||new Error('Projektstart abgebrochen.')
        try{const actual=await jsonAt(`http://${config.host}:${service.port}${service.path}`);if(matches(actual,expected[service.name]))return}catch{}
        await delay(250)
      }
      throw new Error(`${service.name} wurde auf Port ${service.port} nicht bereit. Alle selbst gestarteten Dienste werden beendet.`)
    }
    for(const service of plan){
      if(service.reuse){console.log(`${service.name} auf Port ${service.port} wird wiederverwendet.`);if(service.name==='api')await verifyApi();continue}
      if(service.name==='api'){
        await launch(service,join(root,'.venv/bin/python'),['scripts/serve-real.py'],{PYTHONPATH:join(root,'apps/api'),ATLAS_LOCAL_ID:project,ATLAS_LOCAL_BUILD:expected.api.build})
        await verifyApi()
      }else if(service.name==='web'){
        const env={ATLAS_LOCAL_ID:project,ATLAS_LOCAL_BUILD:expected.web.build,ATLAS_LOCAL_MODE:mode,NUXT_API_PROXY:`http://${config.host}:${config.apiPort}`,HOST:config.host,NUXT_HOST:config.host,PORT:String(config.webPort),NITRO_HOST:config.host,NITRO_PORT:String(config.webPort)}
        const args=mode==='dev'?['--max-http-header-size=65536','apps/web/node_modules/nuxt/bin/nuxt.mjs','dev','apps/web','--no-fork','--no-clear']:['--max-http-header-size=65536','apps/web/.output/server/index.mjs']
        await launch(service,process.execPath,args,env)
      }else await launch(service,'nginx',['-c',writeNginxConfig(),'-g','daemon off;'])
    }
    // Verify both upstreams through the actual browser entry.
    if(!matches(await jsonAt(`${entry}/health/web`),expected.web)||!matches(await jsonAt(`${entry}/health/instance`),expected.api))throw new Error('nginx liefert nicht die vorgesehenen Upstreams.')
    console.log(`Ortsnamenatlas bereit: ${entry} · ${mode} · Beenden mit Strg+C oder pnpm local:stop`)
    await new Promise(resolve=>{const check=setInterval(()=>{if(finished){clearInterval(check);resolve()}},250)})
  }catch(e){await stop(1);throw e}
}
async function verifyApi(){
  try{await jsonAt(`http://${config.host}:${config.apiPort}/health/ready`)}catch(e){throw new Error(`Backend nicht bereit: ${e.message}. Datenbank, Veröffentlichung und Migration 0002 prüfen (MIGRATION_DATABASE_URL=… uv run alembic upgrade head).`)}
  const datasets=await jsonAt(`http://${config.host}:${config.apiPort}/api/v1/datasets`)
  if(!datasets.some(d=>d.active&&!d.synthetic))throw new Error('Kein veröffentlichter echter Datenbestand verfügbar. Es wird kein Testbestand importiert.')
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
  try{await startStack(process.argv.includes('--dev')?'dev':'preview')}catch(e){console.error(e.message);process.exitCode=1}
}

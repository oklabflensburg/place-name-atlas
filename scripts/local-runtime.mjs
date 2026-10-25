import {readFileSync,readdirSync,realpathSync,existsSync} from 'node:fs'
import {fileURLToPath} from 'node:url'
import {join} from 'node:path'
import {createHash} from 'node:crypto'
import {tmpdir} from 'node:os'
import {createServer} from 'node:net'
export const root=realpathSync(fileURLToPath(new URL('../',import.meta.url)))
export const config=JSON.parse(readFileSync(process.env.ATLAS_LOCAL_CONFIG||join(root,'infra/local.json'),'utf8'))
if(config.host!=='127.0.0.1'||['apiPort','webPort','nginxPort'].some(k=>!Number.isInteger(config[k])||config[k]<1024||config[k]>65535)||new Set([config.apiPort,config.webPort,config.nginxPort]).size!==3)throw new Error('Ungültige Ports in infra/local.json')
export const project=createHash('sha256').update(root+JSON.stringify(config)).digest('hex').slice(0,16)
export const runtime=join(tmpdir(),`ortsnamenatlas-${project}`)
export const entry=`http://${config.host}:${config.nginxPort}`
export function fingerprint(paths){
  const hash=createHash('sha256')
  function add(path){
    const full=join(root,path)
    const entries=readdirSync(full,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))
    for(const e of entries){if(e.name==='__pycache__'||e.name==='node_modules')continue;const rel=`${path}/${e.name}`;if(e.isDirectory())add(rel);else{hash.update(rel);hash.update(readFileSync(join(root,rel)))}}
  }
  for(const path of paths){if(existsSync(join(root,path))){if(readdirIsDirectory(path))add(path);else{hash.update(path);hash.update(readFileSync(join(root,path)))}}}
  return hash.digest('hex')
}
// Directory checks without following arbitrary generated output trees.
import {statSync} from 'node:fs'
function readdirIsDirectory(path){return statSync(join(root,path)).isDirectory()}
export const apiBuild=()=>fingerprint(['apps/api/atlas','apps/api/migrations','pyproject.toml','uv.lock'])
export const webBuild=()=>fingerprint(['apps/web/app','apps/web/server','apps/web/nuxt.config.ts','apps/web/package.json','packages/api-client','pnpm-lock.yaml'])
export const proxyBuild=()=>fingerprint(['infra/local.json','infra/nginx.conf','scripts/serve-nginx.mjs'])
export function identities(mode){return {
  api:{service:'api',project,build:apiBuild()},
  web:{service:'web',project,build:webBuild(),mode},
  nginx:{service:'nginx',project,build:proxyBuild(),api:`http://${config.host}:${config.apiPort}`,web:`http://${config.host}:${config.webPort}`}
}}
export const services=[{name:'api',port:config.apiPort,path:'/health/instance'}, {name:'web',port:config.webPort,path:'/health/web'}, {name:'nginx',port:config.nginxPort,path:'/health/proxy'}]
export async function jsonAt(url){const r=await fetch(url,{signal:AbortSignal.timeout(2000)});if(!r.ok)throw new Error(`${url}: HTTP ${r.status}`);return r.json()}
export function matches(actual,expected){return Object.entries(expected).every(([k,v])=>actual?.[k]===v)}
export async function occupied(port){
  return new Promise((resolve,reject)=>{const server=createServer();server.once('error',e=>e.code==='EADDRINUSE'?resolve(true):reject(new Error(`Port ${port} kann nicht geprüft werden: ${e.code}. Keine Dienste gestartet.`)));server.listen({host:config.host,port,exclusive:true},()=>server.close(e=>e?reject(e):resolve(false)))})
}
export async function planServices(expected,probe=async service=>{
  if(!await occupied(service.port))return null
  try{return await jsonAt(`http://${config.host}:${service.port}${service.path}`)}catch{return {unidentified:true}}
}){
  const plan=[]
  for(const service of services){
    const actual=await probe(service)
    if(actual&&!matches(actual,expected[service.name]))throw new Error(`Port ${service.port} (${service.name}) ist durch einen fremden, veralteten oder anders gestarteten Dienst belegt. Keine zweite Instanz gestartet. pnpm local:stop erkennt und beendet verifizierte aktuelle und ältere Projektstarts regulär. Bei fehlender Zuordnung pnpm local:status prüfen. Fremde Prozesse werden nicht automatisch beendet.`)
    plan.push({...service,reuse:!!actual})
  }
  return plan
}
export function processIdentity(pid){
  try{const raw=readFileSync(`/proc/${pid}/stat`,'utf8');return raw.slice(raw.lastIndexOf(')')+2).split(' ')[19]}catch{return null}
}
export function liveManager(record){return record?.project===project&&record?.root===root&&processIdentity(record.pid)===record.startTime&&!!record.startTime}

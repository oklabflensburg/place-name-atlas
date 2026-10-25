// Recover known local project launches from live socket/process evidence.
// Never use old PID lists, process-name matching alone, or process-group kills.
import {readFileSync,readlinkSync} from 'node:fs'
import {resolve,basename,join} from 'node:path'
import {setTimeout as delay} from 'node:timers/promises'
import {root,runtime,processIdentity} from './local-runtime.mjs'

const pairedOptions=new Set(['--require','-r','--import','--loader','--experimental-loader','--conditions','-C','--icu-data-dir','--max-http-header-size'])
function scriptArgument(command){
  for(let i=1;i<command.length;i++){
    const value=command[i]
    if(['-e','--eval','-p','--print','-i','--interactive','-c','-m'].includes(value)||/^--(?:eval|print)=/.test(value))return null
    if(value==='--')return command[i+1]||null
    if(pairedOptions.has(value)){i++;continue}
    if(value.startsWith('-'))continue
    return value
  }
  return null
}
export function classifyProjectProcess(record,projectRoot=root,nginxFiles=[join(runtime,'nginx/nginx.conf'),'/tmp/ortsnamenatlas-nginx/nginx.conf']){
  if(!record?.cwd||!record.command?.length||!(record.cwd===projectRoot||record.cwd.startsWith(projectRoot+'/')))return null
  const executable=basename(record.command[0]),entry=scriptArgument(record.command)
  const path=entry?resolve(record.cwd,entry):null
  if(/^node(?:js)?$/.test(executable)){
    if([join(projectRoot,'scripts/preview.mjs'),join(projectRoot,'scripts/local-stack.mjs')].includes(path))return {role:'manager',signal:'SIGTERM'}
    if(path===join(projectRoot,'scripts/serve-nginx.mjs'))return {role:'nginx-wrapper',signal:'SIGTERM'}
    if(path===join(projectRoot,'apps/web/.output/server/index.mjs'))return {role:'web',signal:'SIGTERM'}
    if(path&&/\/node_modules\/(?:nuxt\/bin\/nuxt|@nuxt\/cli\/bin\/nuxi)\.mjs$/.test(path)&&record.command.includes('dev')&&
        (record.cwd===join(projectRoot,'apps/web')||record.command.some(v=>!v.startsWith('-')&&resolve(record.cwd,v)===join(projectRoot,'apps/web'))))return {role:'web-dev',signal:'SIGTERM'}
  }
  if(/^python(?:\d+(?:\.\d+)*)?$/.test(executable)){
    if(path===join(projectRoot,'scripts/serve-real.py'))return {role:'api',signal:'SIGTERM'}
    if(record.command.includes('atlas.main:app')&&(
      (record.command.includes('-m')&&record.command[record.command.indexOf('-m')+1]==='uvicorn')||path===join(projectRoot,'.venv/bin/uvicorn')))return {role:'api',signal:'SIGTERM'}
  }
  if(executable==='uvicorn'&&resolve(record.cwd,record.command[0])===join(projectRoot,'.venv/bin/uvicorn')&&record.command.includes('atlas.main:app'))return {role:'api',signal:'SIGTERM'}
  // nginx rewrites argv into a process title; workers must go through the master.
  const title=record.command.join(' ')
  const file=title.match(/(?:^|\s)-c\s+(\S+)/)?.[1]
  if((executable==='nginx'||title.startsWith('nginx: master process '))&&file&&nginxFiles.includes(resolve(record.cwd,file)))return {role:'nginx',signal:'SIGQUIT'}
  return null
}
function supervisor(chain){
  for(const p of chain){
    if(/(?:^|[/\s])(?:PM2|pm2|supervisord|s6-supervise|runsv|circusd|foreman)(?:[\s:]|$)/.test(p.command.join(' ')))return p.command.join(' ')
  }
  for(const p of chain.slice(0,1)){
    const unit=p.cgroup?.split('/').filter(s=>s.endsWith('.service')&&!/^user@\d+\.service$/.test(s)&&!/terminal(?:-server)?\.service$/.test(s)).at(-1)
    if(unit)return unit
  }
  return null
}
export function planLegacyStops(report,{projectRoot=root,uid=process.getuid(),nginxFiles}={}){
  const records=new Map(report.processes.map(p=>[p.pid,p])),targets=new Map(),blocked=[]
  for(const listener of report.listeners){
    const owners=listener.pids|| (listener.pid?[listener.pid]:[])
    if(!owners.length){blocked.push({port:listener.port,reason:'Socketbesitzer nicht lesbar'});continue}
    for(const owner of owners){
      const chain=[],seen=new Set()
      for(let p=records.get(owner);p&&!seen.has(p.pid);p=records.get(p.ppid)){seen.add(p.pid);chain.push(p)}
      const known=chain.map(p=>({record:p,kind:classifyProjectProcess(p,projectRoot,nginxFiles)})).filter(p=>p.kind)
      // Prefer the enclosing project manager; otherwise the component's lifecycle.
      const target=known.findLast(p=>p.kind.role==='manager')||known.findLast(p=>['web-dev','nginx-wrapper'].includes(p.kind.role))||known[0]
      if(!target){blocked.push({port:listener.port,pid:owner,reason:'Kein bekannter Projektstart mit passendem Arbeitsverzeichnis'});continue}
      const service=records.get(owner),record=target.record
      if(record.uid!==uid||service?.uid!==uid||!record.startTime){blocked.push({port:listener.port,pid:owner,reason:'Benutzer oder Prozessstart nicht eindeutig zugeordnet'});continue}
      const managedBy=supervisor(chain)
      if(managedBy){blocked.push({port:listener.port,pid:owner,reason:`Extern beaufsichtigt (${managedBy}); ausschließlich den zugehörigen Projektdienst über dessen Manager stoppen`});continue}
      const existing=targets.get(record.pid)
      if(existing){if(!existing.ports.includes(listener.port))existing.ports.push(listener.port)}
      else targets.set(record.pid,{...record,...target.kind,ports:[listener.port]})
    }
  }
  return {targets:[...targets.values()],blocked}
}
export function readLiveProcess(pid){
  try{
    const directory=`/proc/${pid}`,status=readFileSync(join(directory,'status'),'utf8')
    return {pid,ppid:Number(status.match(/^PPid:\s+(\d+)/m)?.[1]||0),uid:Number(status.match(/^Uid:\s+(\d+)/m)?.[1]??-1),
      cwd:readlinkSync(join(directory,'cwd')),command:readFileSync(join(directory,'cmdline'),'utf8').split('\0').filter(Boolean),
      startTime:processIdentity(pid),cgroup:readFileSync(join(directory,'cgroup'),'utf8').trim()}
  }catch{return null}
}
export function sameProcess(expected,actual){
  return !!expected.startTime&&actual?.pid===expected.pid&&actual.startTime===expected.startTime&&actual.uid===expected.uid&&actual.ppid===expected.ppid&&
    actual.cwd===expected.cwd&&JSON.stringify(actual.command)===JSON.stringify(expected.command)&&actual.cgroup===expected.cgroup
}
export async function stopLegacyTargets(targets,{lookup=readLiveProcess,signal=(pid,name)=>process.kill(pid,name),sleep=delay,attempts=40,onSignal=()=>{}}={}){
  const stopped=[]
  for(const target of targets){
    const current=lookup(target.pid)
    if(!current){stopped.push({pid:target.pid,alreadyExited:true});continue}
    if(!sameProcess(target,current))throw new Error(`PID ${target.pid} hat sich seit der Zuordnung verändert. Kein Signal gesendet.`)
    // Target only the verified process. Its normal handlers stop its own children.
    signal(target.pid,target.signal);onSignal(target)
    for(let i=0;i<attempts;i++){
      const live=lookup(target.pid)
      if(!live||live.startTime!==target.startTime)break
      await sleep(250)
    }
    const remaining=lookup(target.pid)
    if(remaining?.startTime===target.startTime)throw new Error(`Projektprozess ${target.pid} reagiert noch nicht auf ${target.signal}. Kein SIGKILL gesendet; zuständigen Start/Manager prüfen.`)
    stopped.push({pid:target.pid,signal:target.signal})
  }
  return stopped
}

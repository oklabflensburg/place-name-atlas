// Read-only diagnostic: commands, cwd, ancestry, sockets, health and nginx upstreams.
import {readFileSync,readdirSync,readlinkSync,existsSync} from 'node:fs'
import {join} from 'node:path'
import {spawnSync} from 'node:child_process'
import {pathToFileURL} from 'node:url'
import {root,runtime,config,services,jsonAt,processIdentity} from './local-runtime.mjs'
export async function inspectLocal(){
const ports=new Set([...services.map(s=>s.port),3001])
const report={at:new Date().toISOString(),project:root,visibility:'Only the current /proc and network namespace; an empty list does not prove the host is free.',ports:[...ports],listeners:[],processes:[],health:[],nginx:[],limitations:[]}
const inodes=new Map()
for(const path of ['/proc/net/tcp','/proc/net/tcp6'])try{
  for(const row of readFileSync(path,'utf8').trim().split('\n').slice(1)){
    const fields=row.trim().split(/\s+/),port=parseInt(fields[1].split(':')[1],16)
    if(fields[3]==='0A'&&ports.has(port)){inodes.set(fields[9],port);report.listeners.push({port,address:fields[1],inode:fields[9]})}
  }
}catch(e){report.limitations.push(`${path}: ${e.code}`)}
const seen=new Set()
function processInfo(pid){
  if(seen.has(pid))return
  seen.add(pid)
  try{
    const directory=`/proc/${pid}`,status=readFileSync(join(directory,'status'),'utf8'),ppid=Number(status.match(/^PPid:\s+(\d+)/m)?.[1]||0)
    const command=readFileSync(join(directory,'cmdline'),'utf8').split('\0').filter(Boolean)
    let cwd;try{cwd=readlinkSync(join(directory,'cwd'))}catch{cwd='unreadable'}
    const process={pid,ppid,command,cwd,startTime:processIdentity(pid),uid:Number(status.match(/^Uid:\s+(\d+)/m)?.[1]??-1),currentProject:cwd===root||cwd.startsWith(root+'/'),cgroup:readFileSync(join(directory,'cgroup'),'utf8').trim()}
    report.processes.push(process)
    if(command.some(v=>v.includes('nginx'))){
      const file=command.join(' ').match(/(?:^|\s)-c\s+(\S+)/)?.[1]
      if(file&&existsSync(file)){
        const detail={pid,file,configuration:readFileSync(file,'utf8'),activeProcess:true}
        if(process.currentProject){const expanded=spawnSync('nginx',['-T','-c',file],{encoding:'utf8',timeout:5000});detail.expanded=expanded.stdout;detail.validation=expanded.stderr;detail.validationStatus=expanded.status}
        report.nginx.push(detail)
      }
    }
    if(ppid>1)processInfo(ppid)
  }catch(e){report.limitations.push(`Prozess ${pid}: ${e.code}`)}
}
for(const item of readdirSync('/proc'))if(/^\d+$/.test(item)){
  try{for(const fd of readdirSync(`/proc/${item}/fd`)){
    let link;try{link=readlinkSync(`/proc/${item}/fd/${fd}`)}catch{continue}
    const inode=link.match(/^socket:\[(\d+)\]$/)?.[1]
    if(inodes.has(inode)){processInfo(Number(item));for(const listener of report.listeners)if(listener.inode===inode){listener.pid=Number(item);listener.pids??=[];if(!listener.pids.includes(Number(item)))listener.pids.push(Number(item))}}
  }}catch{}
}
const ss=spawnSync('ss',['-ltnp'],{encoding:'utf8'})
if(ss.status!==0||ss.stderr)report.limitations.push(`ss: ${ss.stderr?.trim()||ss.error?.message||ss.status}`)
for(const port of ports)for(const path of port===config.apiPort?['/health/live','/health/ready','/health/instance']:port===config.nginxPort?['/health/proxy','/health/instance','/health/web','/health/ready']:['/health/web']){
  const url=`http://${config.host}:${port}${path}`
  try{report.health.push({url,value:await jsonAt(url)})}catch(e){report.health.push({url,error:e.message,cause:e.cause?.code})}
}
for(const file of [join(runtime,'nginx/nginx.conf'),'/tmp/ortsnamenatlas-nginx/nginx.conf'])if(existsSync(file)&&!report.nginx.some(n=>n.file===file))report.nginx.push({file,configuration:readFileSync(file,'utf8'),active:false,note:'Datei vorhanden; kein sichtbarer zugehöriger Prozess. Keine Aussage über aktive Upstreams.'})
try{report.manager=JSON.parse(readFileSync(join(runtime,'manager/instance.json'),'utf8'))}catch{}
return report
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)console.log(JSON.stringify(await inspectLocal(),null,2))

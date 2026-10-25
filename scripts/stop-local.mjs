import {readFileSync} from 'node:fs'
import {join} from 'node:path'
import {runtime,root,liveManager} from './local-runtime.mjs'
import {inspectLocal} from './inspect-local.mjs'
import {planLegacyStops,classifyProjectProcess,readLiveProcess,stopLegacyTargets} from './legacy-processes.mjs'

function printEvidence(report){
  console.log(`Geprüfte Projektports: ${report.ports.join(', ')}`)
  for(const p of report.processes)console.log(`PID ${p.pid} · Elternprozess ${p.ppid} · UID ${p.uid} · Arbeitsverzeichnis ${p.cwd}\n  Kommando: ${JSON.stringify(p.command)}\n  Prozessmanager/Cgroup: ${p.cgroup}`)
  for(const h of report.health)console.log(`Health ${h.url}: ${h.value?JSON.stringify(h.value):h.cause||h.error}`)
  for(const n of report.nginx){
    const upstreams=[...new Set([...n.configuration.matchAll(/proxy_pass\s+([^;]+);/g)].map(m=>m[1]))]
    console.log(`nginx ${n.file}${n.activeProcess?` · aktiver Prozess ${n.pid}`:' · Datei ohne zugeordneten sichtbaren Prozess'} · Upstreams: ${upstreams.join(', ')}`)
  }
  for(const limitation of report.limitations)console.log(`Diagnosegrenze: ${limitation}`)
}
async function stopLocal(){
  // Diagnostics also cover older launches that predate the manager's PID record.
  const report=await inspectLocal()
  printEvidence(report)
  const plan=planLegacyStops(report)
  let record
  try{record=JSON.parse(readFileSync(join(runtime,'manager/instance.json'),'utf8'))}catch{}
  if(liveManager(record)){
    const manager=readLiveProcess(record.pid)
    if(manager?.uid!==process.getuid()||manager.cwd!==root||classifyProjectProcess(manager)?.role!=='manager')throw new Error('Manager-Kommando, Benutzer oder Arbeitsverzeichnis passen nicht. Kein Signal gesendet.')
    if(manager.startTime!==record.startTime)throw new Error('Manager hat sich während der Prüfung verändert. Kein Signal gesendet.')
    if(!report.processes.some(p=>p.pid===manager.pid))console.log(`Manager PID ${manager.pid} · Elternprozess ${manager.ppid} · UID ${manager.uid} · Arbeitsverzeichnis ${manager.cwd}\n  Kommando: ${JSON.stringify(manager.command)}\n  Prozessmanager/Cgroup: ${manager.cgroup}`)
    if(!plan.targets.some(t=>t.pid===record.pid))plan.targets.unshift({...manager,role:'manager',signal:'SIGTERM',ports:[]})
  }
  for(const b of plan.blocked)console.log(`Port ${b.port}${b.pid?` · PID ${b.pid}`:''}: ${b.reason}. Dieser Prozess wird nicht direkt beendet.`)
  if(!plan.targets.length){
    if(report.listeners.length||report.limitations.some(s=>/Operation not permitted|EPERM|EACCES/.test(s))){
      console.error('Kein Projektprozess sicher zugeordnet. Fremde Dienste bzw. Hostprozesse außerhalb der sichtbaren Umgebung wurden nicht beendet. Diesen Befehl im Hostterminal ausführen; pnpm local:status liefert die Diagnose.')
      process.exitCode=1
    }else console.log('Keine laufenden Projektprozesse auf den geprüften Ports und kein laufender Projektmanager gefunden.')
    return
  }
  for(const t of plan.targets)console.log(`Zugeordnet: ${t.role} · PID ${t.pid} · Ports ${t.ports.join(', ')||'Projektmanager'} · reguläres Signal ${t.signal}`)
  const stopped=await stopLegacyTargets(plan.targets,{onSignal:t=>console.log(`${t.signal} an verifizierten Projektprozess ${t.pid} gesendet.`)})
  console.log(`Regulär beendet bzw. bereits beendet: ${stopped.map(s=>s.pid).join(', ')}.`)
  const remaining=await inspectLocal()
  if(remaining.listeners.length){
    console.error(`Weiterhin belegt: ${[...new Set(remaining.listeners.map(s=>s.port))].join(', ')}. Verbleibende Dienste nicht automatisch beendet; pnpm local:status prüfen.`)
    process.exitCode=1
  }else if(remaining.limitations.some(s=>/Operation not permitted|EPERM|EACCES/.test(s))){
    console.error('Die genannten Prozesse sind beendet; freie Hostports können wegen eingeschränkter Sicht nicht bestätigt werden.')
    process.exitCode=1
  }else console.log('Die geprüften Projektports sind frei. Start: pnpm preview:local')
}
try{await stopLocal()}catch(e){console.error(e.message);process.exitCode=1}

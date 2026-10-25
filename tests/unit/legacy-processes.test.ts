import {describe,it,expect} from 'vitest'
// @ts-expect-error local Node orchestration module
import {root} from '../../scripts/local-runtime.mjs'
// @ts-expect-error local Node orchestration module
import {classifyProjectProcess,planLegacyStops,stopLegacyTargets} from '../../scripts/legacy-processes.mjs'
const uid=1000
const proc=(pid:number,command:string[],cwd=root,ppid=1)=>({pid,ppid,command,cwd,uid,startTime:`start-${pid}`,cgroup:'0::/user.slice/user-1000.slice/session-1.scope'})
const api=()=>proc(101,['/usr/bin/python3','scripts/serve-real.py'])
const web=()=>proc(102,['/usr/bin/node','--max-http-header-size=65536','apps/web/.output/server/index.mjs'])
const nginx=()=>proc(104,['nginx: master process nginx -c /tmp/ortsnamenatlas-nginx/nginx.conf -g daemon off;'])
const report=(processes:any[],listeners:any[])=>({processes,listeners})
const plan=(r:any)=>planLegacyStops(r,{uid})

describe('regular shutdown of older project launches',()=>{
  it('recognizes known old API, built web and nginx launches without PID records',()=>{
    expect(classifyProjectProcess(api())).toEqual({role:'api',signal:'SIGTERM'})
    expect(classifyProjectProcess(web())).toEqual({role:'web',signal:'SIGTERM'})
    expect(classifyProjectProcess(nginx())).toEqual({role:'nginx',signal:'SIGQUIT'})
    const result=plan(report([api(),web(),nginx()],[{port:8000,pid:101},{port:3001,pid:102},{port:8080,pid:104}]))
    expect(result.targets.map((t:any)=>[t.pid,t.signal])).toEqual([[101,'SIGTERM'],[102,'SIGTERM'],[104,'SIGQUIT']])
    expect(result.blocked).toEqual([])
  })
  it('stops a single enclosing preview manager for API, web and nginx workers',()=>{
    const manager=proc(100,['/usr/bin/node','scripts/preview.mjs'])
    const wrapper=proc(103,['/usr/bin/node','scripts/serve-nginx.mjs'],root,100)
    const master={...nginx(),ppid:103},worker=proc(105,['nginx: worker process'],root,104)
    const result=plan(report([manager,{...api(),ppid:100},{...web(),ppid:100},wrapper,master,worker],[{port:8000,pid:101},{port:3001,pid:102},{port:8080,pids:[104,105]}]))
    expect(result.targets).toHaveLength(1)
    expect(result.targets[0]).toMatchObject({pid:100,role:'manager',signal:'SIGTERM',ports:[8000,3001,8080]})
  })
  it('goes through Nuxt dev and nginx wrapper parents for forked listeners',()=>{
    const nuxt=proc(200,['/usr/bin/node',`${root}/node_modules/.pnpm/cli/node_modules/@nuxt/cli/bin/nuxi.mjs`,'dev','--host','127.0.0.1'],`${root}/apps/web`)
    const worker=proc(201,['/usr/bin/node','worker.mjs'],`${root}/apps/web`,200)
    const wrapper=proc(103,['/usr/bin/node','scripts/serve-nginx.mjs'])
    const result=plan(report([nuxt,worker,wrapper,{...nginx(),ppid:103}],[{port:3000,pid:201},{port:8080,pid:104}]))
    expect(result.targets.map((t:any)=>[t.pid,t.role])).toEqual([[200,'web-dev'],[103,'nginx-wrapper']])
  })
  it('recognizes only the atlas uvicorn application in the project directory',()=>{
    expect(classifyProjectProcess(proc(101,['/usr/bin/python3','-m','uvicorn','atlas.main:app']))?.role).toBe('api')
    expect(classifyProjectProcess(proc(101,['/usr/bin/python3','-m','uvicorn','other.main:app']))).toBeNull()
    expect(classifyProjectProcess(proc(101,['/usr/bin/python3','-m','http.server','8000']))).toBeNull()
  })
  it('refuses unrelated scripts, another cwd, argv decoys and a different nginx config',()=>{
    for(const p of [proc(1,['/usr/bin/python3','other.py']),proc(1,['/usr/bin/node','scripts/preview.mjs'],'/other/project'),proc(1,['/usr/bin/node','-e','something','scripts/preview.mjs']),proc(1,['/usr/bin/node','other.mjs','scripts/preview.mjs']),proc(1,['nginx: master process nginx -c /etc/nginx/nginx.conf'])])expect(classifyProjectProcess(p)).toBeNull()
    expect(plan(report([proc(1,['/usr/bin/node','other.mjs'])],[{port:8000,pid:1}])).targets).toEqual([])
  })
  it('refuses unknown socket owners, unreadable start times and other users',()=>{
    for(const r of [report([],[{port:8000}]),report([{...api(),startTime:null}],[{port:8000,pid:101}]),report([{...api(),uid:0}],[{port:8000,pid:101}])]){
      const p=plan(r);expect(p.targets).toEqual([]);expect(p.blocked).toHaveLength(1)
    }
  })
  it('does not signal children managed by PM2 or a named systemd service',()=>{
    const pm2=proc(100,['PM2 v6: God Daemon'])
    const managed={...api(),ppid:100}
    expect(plan(report([managed,pm2],[{port:8000,pid:101}])).blocked[0].reason).toContain('PM2')
    const systemd={...api(),cgroup:'0::/user.slice/user-1000.slice/user@1000.service/app.slice/atlas-api.service'}
    expect(plan(report([systemd],[{port:8000,pid:101}])).blocked[0].reason).toContain('atlas-api.service')
  })
  it('does not mistake the SSH daemon ancestor for the application supervisor',()=>{
    const shell=proc(100,['zsh']),sshd={...proc(99,['/usr/sbin/sshd']),uid:0,cgroup:'0::/system.slice/ssh.service'}
    shell.ppid=99
    expect(plan(report([{...api(),ppid:100},shell,sshd],[{port:8000,pid:101}])).targets[0].pid).toBe(101)
  })
  it('rechecks PID start time, command, uid and parent immediately before signaling',async()=>{
    const target={...api(),signal:'SIGTERM'}
    for(const change of [{startTime:'reused'},{command:['foreign']},{cwd:'/other'},{uid:0},{ppid:999}]){
      const signals:any[]=[]
      await expect(stopLegacyTargets([target],{lookup:()=>({...target,...change}),signal:(...args:any[])=>signals.push(args)})).rejects.toThrow('verändert')
      expect(signals).toEqual([])
    }
  })
  it('uses only positive verified PIDs and the regular component signals',async()=>{
    const targets=plan(report([api(),nginx()],[{port:8000,pid:101},{port:8080,pid:104}])).targets
    const live=new Map(targets.map((t:any)=>[t.pid,t])),signals:any[]=[]
    const stopped=await stopLegacyTargets(targets,{lookup:(pid:number)=>live.get(pid),signal:(pid:number,name:string)=>{signals.push([pid,name]);live.delete(pid)},sleep:async()=>{}})
    expect(signals).toEqual([[101,'SIGTERM'],[104,'SIGQUIT']]);expect(stopped).toHaveLength(2)
  })
  it('does not force-kill unresponsive older launches or re-signal a reused PID',async()=>{
    const target={...api(),signal:'SIGTERM'},signals:any[]=[]
    await expect(stopLegacyTargets([target],{lookup:()=>target,signal:(...args:any[])=>signals.push(args),sleep:async()=>{},attempts:2})).rejects.toThrow('Kein SIGKILL')
    expect(signals).toEqual([[101,'SIGTERM']])
    let lookupCount=0
    const stopped=await stopLegacyTargets([target],{lookup:()=>++lookupCount===1?target:{...target,startTime:'another-process'},signal:()=>{},sleep:async()=>{}})
    expect(stopped).toHaveLength(1)
  })
})

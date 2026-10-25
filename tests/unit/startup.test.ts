import {describe,it,expect} from 'vitest'
import {EventEmitter} from 'node:events'
// These modules use Node's built-ins and do not start listeners on import.
// @ts-expect-error local Node orchestration module
import {config,services,identities,planServices,matches} from '../../scripts/local-runtime.mjs'
// @ts-expect-error local Node orchestration module
import {Children} from '../../scripts/local-stack.mjs'
describe('local startup ownership and ports',()=>{
  it('has distinct central ports and plans a fresh stack before spawning',async()=>{
    const expected=identities('preview'),visited:string[]=[]
    const plan=await planServices(expected,async(s:{name:string})=>{visited.push(s.name);return null})
    expect(new Set([config.apiPort,config.webPort,config.nginxPort]).size).toBe(3)
    expect(visited).toEqual(['api','web','nginx']);expect(plan.every((s:{reuse:boolean})=>!s.reuse)).toBe(true)
  })
  it('reuses the desired backend and rejects foreign, stale or wrong-mode services',async()=>{
    const expected=identities('preview')
    const plan=await planServices(expected,async(s:{name:string})=>s.name==='api'?expected.api:null)
    expect(plan[0].reuse).toBe(true)
    for(const actual of [{unidentified:true},{...expected.web,build:'stale'},{...expected.web,mode:'dev'}]){
      await expect(planServices(expected,async(s:{name:string})=>s.name==='web'?actual:null)).rejects.toThrow('Port 3000')
    }
    expect(matches({...expected.api,pid:123},expected.api)).toBe(true)
  })
  it('checks nginx upstreams, rather than accepting an arbitrary HTTP 200',async()=>{
    const expected=identities('preview')
    await expect(planServices(expected,async(s:{name:string})=>s.name==='nginx'?{...expected.nginx,web:'http://127.0.0.1:3001'}:null)).rejects.toThrow('Port 8080')
    const plan=await planServices(expected,async(s:{name:string})=>expected[s.name])
    expect(plan.every((s:{reuse:boolean})=>s.reuse)).toBe(true);expect(services).toHaveLength(3)
  })
  it('cleans up only spawned process groups and shuts down nginx gracefully',async()=>{
    let pid=10000
    const spawned:any[]=[],signals:any[]=[]
    const children=new Children((command:string)=>{const child=Object.assign(new EventEmitter(),{pid:++pid,spawnfile:command,exitCode:null,signalCode:null});spawned.push(child);return child},(target:number,signal:string)=>{signals.push([target,signal]);queueMicrotask(()=>{const child=spawned.find(c=>c.pid===-target);child.signalCode=signal;child.emit('exit',null,signal)})})
    children.start('python',[]);children.start('nginx',[])
    await children.stop();await children.stop()
    expect(signals).toEqual([[-10001,'SIGTERM'],[-10002,'SIGQUIT']])
    expect(()=>children.start('node',[])).toThrow('keine weiteren Dienste')
    expect(spawned).toHaveLength(2)
  })
  it('does not signal a child that already exited after a failed start',async()=>{
    const signals:any[]=[]
    const child=Object.assign(new EventEmitter(),{pid:10003,spawnfile:'node',exitCode:1,signalCode:null})
    const children=new Children(()=>child,(...args:any[])=>signals.push(args))
    children.start('node',[]);await children.stop();expect(signals).toEqual([])
  })
})

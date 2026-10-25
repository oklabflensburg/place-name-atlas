import {readFileSync,writeFileSync,mkdirSync} from 'node:fs'
import {spawn} from 'node:child_process'
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {root,runtime,config,identities} from './local-runtime.mjs'
export function writeNginxConfig(){
const directory=join(runtime,'nginx')
mkdirSync(directory,{recursive:true})
const identity=JSON.stringify(identities('preview').nginx)
const server=readFileSync(join(root,'infra/nginx.conf'),'utf8')
  .replace('listen 8080;',`listen ${config.host}:${config.nginxPort};`)
  .replaceAll('http://api:8000',`http://${config.host}:${config.apiPort}`)
  .replaceAll('http://web:3000',`http://${config.host}:${config.webPort}`)
  .replace('    location /api/v1/',`    location = /health/proxy { default_type application/json; add_header Cache-Control no-store; return 200 '${identity}'; }\n    location /api/v1/`)
const file=join(directory,'nginx.conf')
writeFileSync(file,`pid ${directory}/nginx.pid;\nerror_log ${directory}/error.log;\nevents {}\nhttp {\naccess_log off;\nclient_body_temp_path ${directory}/body;\nproxy_temp_path ${directory}/proxy;\n${server}\n}`)
return file
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
const child=spawn('nginx',['-c',writeNginxConfig(),'-g','daemon off;'],{stdio:'inherit'})
for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>child.kill('SIGQUIT'))
child.once('error',e=>{console.error(e.message);process.exitCode=1})
child.once('exit',(code,signal)=>{process.exitCode=signal?1:code||0})

}

import {defineConfig,devices} from '@playwright/test'
import {resolve} from 'node:path'
import local from './infra/test-local.json' with {type:'json'}
const production=process.env.TEST_PRODUCTION==='1'
const api=`http://${local.host}:${local.apiPort}`,web=`http://${local.host}:${local.webPort}`,entry=`http://${local.host}:${local.nginxPort}`
const env={ATLAS_LOCAL_CONFIG:resolve('infra/test-local.json'),NUXT_API_PROXY:api}
export default defineConfig({
  testDir:'tests/e2e',workers:1,timeout:45000,expect:{timeout:15000},
  use:{baseURL:production?entry:web,trace:'retain-on-failure',launchOptions:{args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']}},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome'],viewport:{width:1440,height:1100}}},{name:'mobile',use:{...devices['Pixel 7']}}],
  webServer:[
    {command:'PYTHONPATH=apps/api .venv/bin/python scripts/serve-test.py',url:api+'/health/ready',reuseExistingServer:false,timeout:60000,env},
    ...(production?[
      {command:`PORT=${local.webPort} HOST=${local.host} node --max-http-header-size=65536 apps/web/.output/server/index.mjs`,url:web,reuseExistingServer:false,timeout:30000,env},
      {command:'node scripts/serve-nginx.mjs',url:entry,reuseExistingServer:false,timeout:30000,env}
    ]:[{command:'pnpm --filter @atlas/web dev',url:web,reuseExistingServer:false,timeout:120000,env}])
  ]
})

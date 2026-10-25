import {defineConfig,devices} from '@playwright/test'
import local from './infra/local.json' with {type:'json'}
const entry=`http://${local.host}:${local.nginxPort}`
export default defineConfig({
  testDir:'tests/real-e2e',workers:1,timeout:180000,expect:{timeout:30000},
  reporter:[['list'],['json',{outputFile:'artifacts/maps-playwright-results.json'}]],
  use:{baseURL:entry,trace:'retain-on-failure',screenshot:'only-on-failure',launchOptions:{args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']}},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome'],viewport:{width:1440,height:1100}}},{name:'mobile',use:{...devices['Pixel 7']}}],
  // The supervisor checks identities, upstreams and the published database. The
  // tests also verify identities if Playwright reuses an already running stack.
  webServer:{command:'node scripts/preview.mjs',url:entry+'/health/proxy',reuseExistingServer:true,timeout:150000,
    // The manager must receive SIGTERM to close its own detached children.
    // Playwright's default SIGKILL bypasses cleanup and can leave stdio open.
    gracefulShutdown:{signal:'SIGTERM',timeout:15000}}
})

import defaults from '../../infra/local.json'
import {readFileSync} from 'node:fs'
const local=process.env.ATLAS_LOCAL_CONFIG?JSON.parse(readFileSync(process.env.ATLAS_LOCAL_CONFIG,'utf8')):defaults
export default defineNuxtConfig({
  compatibilityDate: '2026-10-01',
  modules: ['@nuxt/ui'],
  css: ['~/assets/main.css', 'maplibre-gl/dist/maplibre-gl.css'],
  typescript: { strict: true, typeCheck: false },
  ui: { fonts: false },
  icon: { customCollections:[{prefix:'atlas',dir:'./app/assets/icons'}], clientBundle:{icons:['atlas:plus','atlas:sliders','atlas:reset','atlas:share','atlas:close','atlas:check','atlas:chevron-down','atlas:pencil','atlas:info','atlas:more']} },
  devtools: { enabled: false },
  // Listhen accepts GetPortOptions at runtime. Disable all fallback ports, also
  // if another process binds between the manager's check and Nuxt's listener.
  devServer: { host:local.host, port:{port:local.webPort,alternativePortRange:[],random:false} as unknown as number },
  runtimeConfig: { public: { basemapUrl: '', basemapAttribution: '' } },
  nitro: { devProxy: {
    '/api/v1/': { target: (process.env.NUXT_API_PROXY || `http://${local.host}:${local.apiPort}`)+'/api/v1/', changeOrigin: false },
    ...Object.fromEntries(['live','ready','instance'].map(name=>[`/health/${name}`, { target: (process.env.NUXT_API_PROXY || `http://${local.host}:${local.apiPort}`)+`/health/${name}`,changeOrigin:false }]))
  } },
  app: { head: { htmlAttrs: { lang: 'de' }, title: 'Ortsnamenatlas · Namen entdecken',
    meta: [{ name: 'description', content: 'Ortsnamen und ihre geografische Verteilung erkunden. Ein offener Atlas von OK Lab Flensburg.' }] } }
})

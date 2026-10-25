export default defineEventHandler(event=>{
  setHeader(event,'Cache-Control','no-store')
  return {service:'web',project:process.env.ATLAS_LOCAL_ID||'',
    build:process.env.ATLAS_LOCAL_BUILD||'',mode:process.env.ATLAS_LOCAL_MODE||'',pid:process.pid}
})

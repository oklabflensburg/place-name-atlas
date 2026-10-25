declare module 'd3-interpolate' {
  export function interpolateRgb(a:string,b:string):(t:number)=>string
}
declare module 'd3-format' {
  export function formatLocale(definition:{decimal:string;thousands:string;grouping:number[];currency:[string,string];percent?:string}):{format:(specifier:string)=>(value:number)=>string}
}

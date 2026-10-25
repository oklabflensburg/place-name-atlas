import {startStack} from './local-stack.mjs'
try{await startStack('preview')}catch(e){console.error(e.message);process.exitCode=1}

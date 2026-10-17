// Use a normal npm install first; also support the bundled desktop test runtime.
if(process.env.PLAYWRIGHT_MODULE){
  module.exports=require(process.env.PLAYWRIGHT_MODULE);
}else{
  try{module.exports=require('playwright');}
  catch(error){
    if(error.code!=='MODULE_NOT_FOUND')throw error;
    const path=require('node:path'),os=require('node:os');
    module.exports=require(path.join(os.homedir(),'.cache','codex-runtimes','codex-primary-runtime','dependencies','node','node_modules','playwright'));
  }
}

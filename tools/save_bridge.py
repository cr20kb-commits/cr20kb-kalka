def patch_save_bridge(data):
    js = data.decode('utf-8')
    changes = [
        ("function download(blob,name){const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}",
         "const savePending=new Map();window.chrome.webview.addEventListener('message',event=>{const v=String(event.data).split('\\t');if(v[0]!=='save-result'||v.length<3)return;const p=savePending.get(v[1]);if(!p)return;savePending.delete(v[1]);if(v[2]==='OK')p.resolve();else p.reject(Error(v.slice(3).join('\\t')||({ru:'Сохранение отменено.',en:'Save canceled.',zh:'保存已取消。'}[language])));});function saveJob(job,name){return new Promise((resolve,reject)=>{savePending.set(job,{resolve,reject});window.chrome.webview.postMessage('save\\t'+job+'\\t'+name);});}"),
        ("async function finishJob(initial){const {job}=await initial.json();for(;;){await new Promise(resolve=>setTimeout(resolve,300));const result=await (await json('/api/job',{job})).json();if(result.status==='error')throw Error(result.error);if(result.status==='ready')return json('/api/result',{job});}}",
         "async function finishJob(initial,nativeName){const {job}=await initial.json();for(;;){await new Promise(resolve=>setTimeout(resolve,300));const result=await (await json('/api/job',{job})).json();if(result.status==='error')throw Error(result.error);if(result.status==='ready')return nativeName?saveJob(job,nativeName):json('/api/result',{job});}}"),
        ("const res=await finishJob(await json('/api/save',{entries:entries.map(e=>({id:e.id,layer:e.layer})),language,comparison:comparisonState()}));download(await res.blob(),'project.kalka');",
         "await finishJob(await json('/api/save',{entries:entries.map(e=>({id:e.id,layer:e.layer})),language,comparison:comparisonState()}),'project.kalka');"),
        ("const res=await finishJob(await json('/api/export',{entries:items.map(e=>({id:e.id,layer:e.layer})),layer_only:layerOnly,pair_compare:pairCompare,show_marks:pairCompare&&$('showMarks').checked}));download(await res.blob(),name);",
         "await finishJob(await json('/api/export',{entries:items.map(e=>({id:e.id,layer:e.layer})),layer_only:layerOnly,pair_compare:pairCompare,show_marks:pairCompare&&$('showMarks').checked}),name);")]
    for old, new in changes:
        if js.count(old) != 1:
            raise ValueError('Unexpected web UI: cannot apply save bridge')
        js = js.replace(old, new)
    return js.encode('utf-8')

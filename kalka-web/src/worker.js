import {ink,regions} from './geometry.js';
import {registerTranslation,acceptFractional} from './registration.js';
self.onmessage=e=>{try{const {id,type}=e.data;if(type==='color'){const p=new Uint8ClampedArray(e.data.pixels),color=e.data.color;for(let i=0;i<p.length;i+=4){const a=ink(p[i],p[i+1],p[i+2],p[i+3]);p[i]=color[0];p[i+1]=color[1];p[i+2]=color[2];p[i+3]=a}postMessage({id,pixels:p.buffer},[p.buffer]);}else if(type==='compare'){
 const a=new Uint8Array(e.data.a),b=new Uint8Array(e.data.b),w=e.data.width,h=e.data.height;let selected=b,integer,phase=[0,0];
 if(e.data.forcedCorrection){integer=e.data.forcedCorrection;phase=e.data.forcedPhase||phase}
 else if(e.data.candidate){const candidate=new Uint8Array(e.data.candidate),offset=registerTranslation(a,candidate,w,h,p=>postMessage({id,progress:p/2}));if(acceptFractional(a,b,candidate,w,h,...offset)){selected=candidate;integer=offset;phase=e.data.fraction}else integer=registerTranslation(a,b,w,h,p=>postMessage({id,progress:.5+p/2}))}
 else integer=registerTranslation(a,b,w,h,p=>postMessage({id,progress:p}));
 const correction=integer.map((v,i)=>v+phase[i]);
 let shifted=selected;if(integer[0]||integer[1]){shifted=new Uint8Array(b.length);for(let y=0;y<h;y++){let sy=y-integer[1];if(sy<0||sy>=h)continue;for(let x=Math.max(0,integer[0]);x<Math.min(w,w+integer[0]);x++)shifted[y*w+x]=selected[sy*w+x-integer[0]]}}
 const found=regions(a,shifted,w,h);let pixels=new Uint8ClampedArray(a.length*4);
 for(let i=0;i<a.length;i++){let av=a[i],bv=shifted[i],common=Math.min(av,bv),onlyA=av-common,onlyB=bv-common,total=Math.max(av,bv),j=i*4;if(total){pixels[j]=(21*onlyA+211*onlyB+106*common)/total;pixels[j+1]=(101*onlyA+47*onlyB+27*common)/total;pixels[j+2]=(192*onlyA+47*onlyB+154*common)/total}pixels[j+3]=total}
 postMessage({id,regions:found,correction,pixels:pixels.buffer},[pixels.buffer]);
 }}catch(error){postMessage({id:e.data.id,error:String(error.message||error)})}};

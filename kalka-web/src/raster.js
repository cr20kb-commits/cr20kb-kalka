import * as pdfjs from './vendor/pdfjs/pdf.min.mjs';
import {ink} from './geometry.js';
import {dimensions} from './budget.js';
pdfjs.GlobalWorkerOptions.workerSrc=new URL('./vendor/pdfjs/pdf.worker.min.mjs',import.meta.url).href;
export const TILE=1024;
function check(signal){if(signal.aborted)throw new DOMException('Cancelled','AbortError')}
function pdfOptions(data){return {data,cMapUrl:new URL('./vendor/pdfjs/cmaps/',import.meta.url).href,cMapPacked:true,standardFontDataUrl:new URL('./vendor/pdfjs/standard_fonts/',import.meta.url).href,wasmUrl:new URL('./vendor/pdfjs/wasm/',import.meta.url).href,iccUrl:new URL('./vendor/pdfjs/iccs/',import.meta.url).href,enableXfa:false}}
export async function eachTile(entry,box,factor,signal,callback,progress){
 const {w,h}=dimensions(box,factor),blob=await (await fetch(entry.data)).blob();check(signal);
 let pdf=null,page=null,bitmap=null,task=null;
 try{
  if(blob.type==='application/pdf'){task=pdfjs.getDocument(pdfOptions(new Uint8Array(await blob.arrayBuffer())));const abort=()=>task.destroy();signal.addEventListener('abort',abort,{once:true});try{pdf=await task.promise}finally{signal.removeEventListener('abort',abort)}check(signal);page=await pdf.getPage(entry.layer.page)}
  else{bitmap=await createImageBitmap(blob);check(signal)}
  const l=entry.layer,angle=l.angle*Math.PI/180,c=Math.cos(angle)*l.scale,s=Math.sin(angle)*l.scale;
  let v=null,yratio=1;if(page){let natural=page.getViewport({scale:1});v=page.getViewport({scale:factor*entry.width/natural.width});yratio=entry.height*factor/v.height}
  const total=Math.ceil(w/TILE)*Math.ceil(h/TILE);let done=0;
  for(let y=0;y<h;y+=TILE)for(let x=0;x<w;x+=TILE){
   check(signal);let tw=Math.min(TILE,w-x),th=Math.min(TILE,h-y),tile=document.createElement('canvas');tile.width=tw;tile.height=th;let ctx=tile.getContext('2d',{willReadFrequently:true});if(!ctx)throw Error('MEMORY');
   let tx=(l.x-box.left)*factor-x,ty=(l.y-box.top)*factor-y;
   if(page){let render=page.render({canvasContext:ctx,viewport:v,transform:[c,s,-s*yratio,c*yratio,tx,ty],background:'rgba(0,0,0,0)'});const abort=()=>render.cancel();signal.addEventListener('abort',abort,{once:true});try{await render.promise}finally{signal.removeEventListener('abort',abort)}}
   else{ctx.setTransform(c,s,-s,c,tx,ty);ctx.drawImage(bitmap,0,0,entry.width*factor,entry.height*factor)}
   check(signal);let image=ctx.getImageData(0,0,tw,th);await callback(image,x,y,tw,th,w);tile.width=tile.height=0;progress(++done,total);await new Promise(resolve=>setTimeout(resolve,0));
  }
 }finally{bitmap?.close();page?.cleanup();if(pdf)await pdf.destroy();else if(task)await task.destroy()}
}
export async function renderMask(entry,box,factor,signal,progress){let {w,h}=dimensions(box,factor),mask;try{mask=new Uint8Array(w*h)}catch{throw Error('MEMORY')};await eachTile(entry,box,factor,signal,(image,x,y,tw,th)=>{let p=image.data;for(let row=0;row<th;row++)for(let col=0;col<tw;col++){let i=(row*tw+col)*4;mask[(y+row)*w+x+col]=ink(p[i],p[i+1],p[i+2],p[i+3])}},progress);return mask}
export async function renderOverlay(items,box,factor,signal,white,progress){let {w,h}=dimensions(box,factor),output=document.createElement('canvas');output.width=w;output.height=h;let target=output.getContext('2d');if(!target)throw Error('MEMORY');if(white){target.fillStyle='white';target.fillRect(0,0,w,h)}for(let n=0;n<items.length;n++){let e=items[n],color=[1,3,5].map(i=>parseInt(e.layer.color.slice(i,i+2),16));await eachTile(e,box,factor,signal,(image,x,y,tw,th)=>{let p=image.data;for(let i=0;i<p.length;i+=4){let a=ink(p[i],p[i+1],p[i+2],p[i+3]);p[i]=color[0];p[i+1]=color[1];p[i+2]=color[2];p[i+3]=a}let tile=document.createElement('canvas');tile.width=tw;tile.height=th;tile.getContext('2d').putImageData(image,0,0);target.save();target.globalAlpha=e.layer.opacity/100;target.drawImage(tile,x,y);target.restore();tile.width=tile.height=0},(done,total)=>progress(n,items.length,done,total))}return output}

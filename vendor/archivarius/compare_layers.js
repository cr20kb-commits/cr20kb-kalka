/* Full-resolution derived layers. No image resampling except explicit manual scale. */
(() => {
  'use strict';
  function ink(r,g,b) {return 255-Math.round(.299*r+.587*g+.114*b);}
  // Directional difference for already aligned drawing masks. Original compose
  // and its callers stay unchanged. A and B are effective ink-alpha values.
  function directionalPixel(a,b,threshold=20) {
    if (![a,b,threshold].every(Number.isFinite) || Math.min(a,b,threshold)<0 || Math.max(a,b,threshold)>255) throw Error('Invalid difference mask.');
    const delta=b-a;
    if(Math.abs(delta)<=threshold)return [0,0,0,0];
    return delta<0?[225,35,60,Math.round(-delta)]:[0,155,200,Math.round(delta)];
  }
  function alphaLayer(image, color=[0,0,0]) {
    const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);
    const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);
    for(let i=0;i<pixels.data.length;i+=4){const a=ink(pixels.data[i],pixels.data[i+1],pixels.data[i+2]);pixels.data[i]=color[0];pixels.data[i+1]=color[1];pixels.data[i+2]=color[2];pixels.data[i+3]=Math.round(a*pixels.data[i+3]/255);}
    ctx.putImageData(pixels,0,0);return canvas;
  }
  function compose(a,b,o={}) {
    const scale=o.scale??1,angle=(o.angle??0)*Math.PI/180,x=o.x??0,y=o.y??0;
    if(![scale,angle,x,y].every(Number.isFinite)||scale<.01||scale>10)throw Error('Некорректное ручное совмещение.');
    const points=[[0,0],[b.width,0],[0,b.height],[b.width,b.height]].map(([u,v])=>[x+scale*(u*Math.cos(angle)-v*Math.sin(angle)),y+scale*(u*Math.sin(angle)+v*Math.cos(angle))]);
    const left=Math.floor(Math.min(0,...points.map(p=>p[0]))),top=Math.floor(Math.min(0,...points.map(p=>p[1])));
    const width=Math.ceil(Math.max(a.width,...points.map(p=>p[0])))-left,height=Math.ceil(Math.max(a.height,...points.map(p=>p[1])))-top;
    if(width*height>8_000_000||width>20000||height>20000)throw Error('Поле сравнения больше 8 Мп. Листы можно просмотреть отдельно; автоматическое уменьшение не применялось.');
    const make=()=>{const c=document.createElement('canvas');c.width=width;c.height=height;return c;};
    const ca=make(),cb=make(),mode=o.mode||'side',drawing=o.drawing===true;
    if(mode==='redcyan'&&!drawing)throw Error('Для красного/голубого включите режим чертежа. Для цветных моделей используйте наложение, шторку или различия.');
    const ax=ca.getContext('2d'),bx=cb.getContext('2d');
    ax.drawImage(drawing?alphaLayer(a,mode==='redcyan'?[225,35,60]:[0,0,0]):a,-left,-top);
    bx.translate(x-left,y-top);bx.rotate(angle);bx.scale(scale,scale);
    bx.drawImage(drawing?alphaLayer(b,mode==='redcyan'?[0,155,200]:[0,0,0]):b,0,0);
    const result=document.createElement('canvas');result.width=mode==='side'?width*2+20:width;result.height=height;
    const ctx=result.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,result.width,result.height);
    if(mode==='side'){ctx.drawImage(ca,0,0);ctx.fillStyle='#8da0ae';ctx.fillRect(width,0,20,height);ctx.drawImage(cb,width+20,0);}
    else if(mode==='blink'){ctx.drawImage(o.showNew?cb:ca,0,0);}
    else if(mode==='wipe'){ctx.drawImage(ca,0,0);ctx.save();ctx.beginPath();ctx.rect(width*(o.opacity??.5),0,width,height);ctx.clip();ctx.fillStyle='white';ctx.fillRect(0,0,width,height);ctx.drawImage(cb,0,0);ctx.restore();}
    else if(mode==='overlay'||mode==='redcyan'){ctx.drawImage(ca,0,0);ctx.globalAlpha=o.opacity??.5;ctx.drawImage(cb,0,0);}
    else if(mode==='diff'){
      // Flatten to white before comparison. Alpha transparency is display-only.
      for(const c of [ca,cb]){const cx=c.getContext('2d');cx.globalCompositeOperation='destination-over';cx.fillStyle='white';cx.fillRect(0,0,width,height);}
      const p=ax.getImageData(0,0,width,height),q=bx.getImageData(0,0,width,height),out=ctx.createImageData(width,height);
      for(let i=0;i<p.data.length;i+=4){const changed=Math.max(...[0,1,2].map(k=>Math.abs(p.data[i+k]-q.data[i+k])))>(o.threshold??20);out.data[i]=changed?230:230;out.data[i+1]=changed?35:230;out.data[i+2]=changed?65:230;out.data[i+3]=255;}ctx.putImageData(out,0,0);
    }
    return result;
  }
  globalThis.ArchivariusLayers={ink,alphaLayer,compose,directionalPixel};
  if(typeof module!=='undefined')module.exports={ink,directionalPixel};
})();

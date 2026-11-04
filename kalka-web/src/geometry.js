export function corners(l,w,h){const a=l.angle*Math.PI/180,clean=n=>Math.abs(n)<1e-12?0:n,c=clean(Math.cos(a))*l.scale,s=clean(Math.sin(a))*l.scale;return [[0,0],[w,0],[0,h],[w,h]].map(([x,y])=>[l.x+c*x-s*y,l.y+s*x+c*y]);}
export function bounds(entries){const p=entries.flatMap(e=>corners(e.layer,e.width,e.height));if(!p.length)return null;return {left:Math.floor(Math.min(...p.map(q=>q[0]))),top:Math.floor(Math.min(...p.map(q=>q[1]))),right:Math.ceil(Math.max(...p.map(q=>q[0]))),bottom:Math.ceil(Math.max(...p.map(q=>q[1])))};}
export function ink(r,g,b,a){const v=255-Math.min(r,g,b);return v>=32?Math.round(v*a/255):0;}
export function regions(a,b,w,h,threshold=56){
 const parent=[], boxes=[]; let previous=[];
 function root(i){while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i]}return i}
 for(let y=0;y<h;y++){let x=0,runs=[];while(x<w){while(x<w&&Math.abs(a[y*w+x]-b[y*w+x])<threshold)x++;if(x===w)break;const start=x;while(x<w&&Math.abs(a[y*w+x]-b[y*w+x])>=threshold)x++;let id=parent.length;parent.push(id);boxes.push([start,y,x,y+1]);runs.push([start,x,id]);if(id>500000)throw Error('Too many difference fragments');}
 let j=0;for(const [x0,x1,id] of runs){while(j<previous.length&&previous[j][1]<x0-1)j++;for(let k=j;k<previous.length&&previous[k][0]<=x1+1;k++){const p=root(id),q=root(previous[k][2]);if(p!==q)parent[q]=p;}}previous=runs;}
 const grouped=new Map();boxes.forEach((box,i)=>{const r=root(i),v=grouped.get(r);if(!v)grouped.set(r,box.slice());else{v[0]=Math.min(v[0],box[0]);v[1]=Math.min(v[1],box[1]);v[2]=Math.max(v[2],box[2]);v[3]=Math.max(v[3],box[3]);}});
 let found=[...grouped.values()];if(found.length>4000)throw Error('Too many difference regions');let changed=true;while(changed){changed=false;const out=[];for(const b of found.sort((a,b)=>a[1]-b[1]||a[0]-b[0])){let target=out.find(a=>Math.max(a[2]-a[0],a[3]-a[1],b[2]-b[0],b[3]-b[1])<=180&&b[0]<=a[2]+8&&b[2]>=a[0]-8&&b[1]<=a[3]+8&&b[3]>=a[1]-8);if(target){target[0]=Math.min(target[0],b[0]);target[1]=Math.min(target[1],b[1]);target[2]=Math.max(target[2],b[2]);target[3]=Math.max(target[3],b[3]);changed=true}else out.push(b.slice())}found=out;}return found.sort((a,b)=>a[1]-b[1]||a[0]-b[0]);
}

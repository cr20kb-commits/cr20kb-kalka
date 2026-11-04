// Port of kalka_compare._register_translation: only well-supported global shifts.
export function registerTranslation(a,b,w,h,onProgress=()=>{}) {
 let countA=0,countB=0,zero=0;
 for(let i=0;i<a.length;i++){let x=a[i]>=64,y=b[i]>=64;countA+=x;countB+=y;zero+=x!==y}
 if(Math.min(countA,countB)<1000||zero===0)return [0,0];
 const scores=[];
 for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){
  let score=0;
  for(let y=0;y<h;y++){let sy=y-dy;for(let x=0;x<w;x++){let sx=x-dx;let av=a[y*w+x]>=64,bv=sy>=0&&sy<h&&sx>=0&&sx<w&&b[sy*w+sx]>=64;score+=av!==bv}}
  scores.push([score,dx,dy]);onProgress(scores.length/25);
 }
 scores.sort((u,v)=>u[0]-v[0]||u[1]-v[1]||u[2]-v[2]);const [best,dx,dy]=scores[0];
 if((dx===0&&dy===0)||best*5>=zero||scores[1][0]-best<Math.max(100,Math.floor(zero/20)))return [0,0];
 let old=[0,0,0,0],fresh=[0,0,0,0];
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){let i=y*w+x,q=(y>=Math.floor(h/2)?2:0)+(x>=Math.floor(w/2)?1:0),sy=y-dy,sx=x-dx,av=a[i]>=64,bv=b[i]>=64,shift=sy>=0&&sy<h&&sx>=0&&sx<w&&b[sy*w+sx]>=64;old[q]+=av!==bv;fresh[q]+=av!==shift}
 if(old.filter((v,i)=>v>=100&&fresh[i]*2<v).length<3)return [0,0];
 return [dx,dy];
}
// As in _register_fractional, accept the alternate sampling phase only when
// improvement is large and distributed across at least three sheet quadrants.
export function acceptFractional(a,b,candidate,w,h,dx,dy){
 let countA=0,countB=0,old=0,fresh=0,oldQ=[0,0,0,0],newQ=[0,0,0,0];
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){let i=y*w+x,sy=y-dy,sx=x-dx,q=(y>=Math.floor(h/2)?2:0)+(x>=Math.floor(w/2)?1:0),av=a[i]>=64,bv=b[i]>=64,cv=sy>=0&&sy<h&&sx>=0&&sx<w&&candidate[sy*w+sx]>=64;countA+=av;countB+=bv;if(av!==bv){old++;oldQ[q]++}if(av!==cv){fresh++;newQ[q]++}}
 return Math.min(countA,countB)>=1000&&old>=500&&fresh*5<old&&oldQ.filter((v,i)=>v>=100&&newQ[i]*2<v).length>=3;
}

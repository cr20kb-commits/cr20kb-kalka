export const MAX_OUTPUT_PIXELS=25000000;
export function dimensions(box,factor){const w=Math.ceil((box.right-box.left)*factor),h=Math.ceil((box.bottom-box.top)*factor);if(!Number.isFinite(factor)||factor<=0||w<1||h<1||w>10000||h>10000||w*h>MAX_OUTPUT_PIXELS)throw Error('LIMIT_OUTPUT_25MP');return {w,h}}

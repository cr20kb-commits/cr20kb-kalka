import { cp, mkdir, readdir, rm, writeFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
const src = new URL('./src/', import.meta.url), dist = new URL('./dist/', import.meta.url);
await rm(dist, { recursive: true, force: true });
await cp(src, dist, { recursive: true });
async function files(dir) { const out=[]; for(const e of await readdir(dir,{withFileTypes:true})){const p=join(dir,e.name); if(e.isDirectory())out.push(...await files(p)); else out.push('./'+relative(fileURLToPath(dist),p).replaceAll('\\','/'));}return out; }
const list = await files(fileURLToPath(dist));
await writeFile(new URL('precache.js',dist), 'self.KALKA_ASSETS='+JSON.stringify(list)+';\n');
console.log(`Built ${list.length} offline resources`);

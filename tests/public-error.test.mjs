import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
test('a failed directory fetch shows safe recovery copy without raw diagnostics',async()=>{
 const nodes=new Map();
 const element=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',style:{},dataset:{},classList:{toggle(){},add(){},remove(){}},setAttribute(){},addEventListener(){},querySelectorAll(){return[]}});return nodes.get(id)};
 const document={getElementById:element,querySelector:element,querySelectorAll:()=>[],documentElement:element('html'),body:element('body')};
 const window={scrollY:0,addEventListener(){},matchMedia:()=>({matches:false})};
 const diagnostic='PRIVATE_DIAGNOSTIC provider-host.example/internal?token=fixture-only';
 vm.runInNewContext(readFileSync(new URL('../app.js',import.meta.url),'utf8'),{window,document,fetch:()=>Promise.reject(new Error(diagnostic)),localStorage:{getItem:()=>null,setItem(){}},URL,URLSearchParams,location:{href:'https://example.test/'},console});
 await new Promise(resolve=>setImmediate(resolve));
 const output=[...nodes.values()].map(n=>n.innerHTML+n.textContent).join(' ');
 assert.match(output,/Could not load|Refresh to retry/i);
 assert.doesNotMatch(output,/PRIVATE_DIAGNOSTIC|provider-host|fixture-only/);
 assert.match(output,/refresh|retry/i);
});

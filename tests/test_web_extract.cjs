const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const parent = {};
const anchor = (x,y) => ({style:{position:'absolute',left:x+'px',top:y+'px'},parentElement:parent});
const leaf = text => ({textContent:text, children:[]});
const column = (a,children) => ({style:{flexDirection:'column'},parentElement:a,children,
  getBoundingClientRect:()=>({width:60,height:100,left:20,top:20,right:80,bottom:120})});
const head = (a,name) => column(a,[leaf(name),leaf('92y 700^')]);
const table = a => column(a,[['76','102'],['-','12.5'],['3.7','6.5']].map(row=>({children:row.map(leaf)})));
const ctx={innerWidth:1000,innerHeight:800}; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web_extract.js'),'utf8'),ctx);
const a=anchor(20,50), b=anchor(20,50);
const run = elements => JSON.parse(JSON.stringify(ctx.extractSisetong({querySelectorAll:()=>elements})));
const good=run([head(a,'한마루럭키'),table(b)]);
assert.equal(good.length,1); assert.equal(good[0].rows[0][1],'12.5');
assert.equal(run([head(a,'A'),head(a,'B'),table(b)]).length,0);
assert.equal(run([head(a,'A'),table(b),table(b)]).length,0);
assert.equal(run([head(a,'A'),table(anchor(21,50))]).length,0);
const wrongParent=anchor(20,50);wrongParent.parentElement={};
assert.equal(run([head(a,'A'),table(wrongParent)]).length,0);
const malformed=table(b);malformed.children[1].children.pop();
assert.equal(run([head(a,'A'),malformed]).length,0);
const offscreen=head(a,'A');offscreen.getBoundingClientRect=()=>({width:50,height:50,left:-100,top:0,right:-50,bottom:50});
assert.equal(run([offscreen,table(b)]).length,0);

const nodes=[];
function element(tag){const node={tag,style:{},children:[],append(...children){this.children.push(...children);},remove(){},select(){}};nodes.push(node);return node;}
ctx.location={hostname:'sisetong.kr'};
ctx.document={querySelectorAll:()=>[head(a,'한마루럭키'),table(b)],getElementById:()=>null,createElement:element,body:element('body')};
let copied=''; ctx.navigator={clipboard:{writeText:async text=>{copied=text;}}};
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web_picker.js'),'utf8'),ctx);
(async()=>{
 await nodes.find(n=>n.textContent==='이 단지 복사').onclick();
 assert.ok(copied.startsWith('SISEPICKER_WEB_V1\n'));
 assert.equal(JSON.parse(copied.split('\n')[1]).rows[0][1],'12.5');
 console.log('Web extraction: pairing, ambiguity, visibility, columns and copy tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

const assert=require('node:assert/strict');
const {naverPrice,naverArea,summarizeNaverTypes,naverExpectedCount,naverWaitFor}=require('../naver_extract.js');
assert.equal(naverPrice('12억 5,000'),125000);
assert.equal(naverArea('83A-2㎡').key,'83A-2');
assert.equal(naverArea('84A-1m²').key,'84A-1');
assert.equal(naverArea('25A-2평').number,25);
for(const label of ['76D1㎡','76D2m²','76.5D12㎡']) {
  assert.equal(naverArea(label).number,parseFloat(label));
}
assert.equal(naverArea('23D1평').number,23);
const numbered=summarizeNaverTypes([{key:'76D1',pyeong:23,exclusive:'59.1'},{key:'76D2',pyeong:23,exclusive:'59.2'}],
 [{trade:'매매',price:'6억',spec:'76D1/59m²'}, {trade:'전세',price:'4억',spec:'76D2/59m²'}],true);
assert.equal(numbered.errors,0);assert.equal(numbered.types[0].sale,'6.0');assert.equal(numbered.types[1].lease,'4.0');

assert.throws(()=>naverArea('83A-/59㎡'));
const hyphen=summarizeNaverTypes([{key:'83A-2',pyeong:25,exclusive:'59.92'},{key:'84A-1',pyeong:25,exclusive:'59.99'}],
 [{trade:'전세',price:'8억 9,000',spec:'83A-2/59m², 중/34층'}, {trade:'매매',price:'19억 5,000',spec:'84A-1/59m², 24/35층'}],true);
assert.equal(hyphen.errors,0);assert.equal(hyphen.types[0].lease,'8.9');assert.equal(hyphen.types[1].sale,'19.5');
assert.equal(naverPrice('8,500'),8500);
assert.equal(naverPrice('9억'),90000);
for(const x of ['8억/160','가격협의','12억~13억','', '0'])assert.throws(()=>naverPrice(x));
const types=[{key:'117MB',pyeong:35,exclusive:'84.23'},{key:'118SB',pyeong:35,exclusive:'84.27'},{key:'138A',pyeong:42,exclusive:'101.04'}];
// Public DOM sample read from complex 140148, 2026-10-11. Partial first page.
const listings=[{trade:'전세',price:'8억 5,000',spec:'117MB/84m², 저/25층, 동향'},
 {trade:'전세',price:'9억',spec:'117MB/84m², 중/25층, 남향'},
 {trade:'매매',price:'17억 5,000',spec:'118SB/84m², 저/26층, 남향'},
 {trade:'전세',price:'12억',spec:'138A/101m², 중/26층, 남향'},
 {trade:'월세',price:'1억/100',spec:'118SB/84m²'}];
let result=summarizeNaverTypes(types,listings,false);
assert.equal(result.types[0].lease,'8.5');assert.equal(result.types[1].sale,'17.5');
assert.equal(result.types[0].sale,'?');assert.equal(result.types[2].lease,'12.0');assert.equal(result.errors,0);
assert.equal(summarizeNaverTypes(types,listings,true).types[0].sale,'-');
const invalid=summarizeNaverTypes(types,[{trade:'매매',price:'1억',spec:'117MB/59m²'}],true);
assert.equal(invalid.errors,1);assert.equal(invalid.types[0].sale,'?');
assert.equal(summarizeNaverTypes(types,[{trade:'매매',price:'1억',spec:'999A/59m²'}],true).errors,1);
const fs=require('node:fs');
new Function(fs.readFileSync(require('node:path').join(__dirname,'../naver_picker.js'),'utf8'));
console.log('Naver price, type matching, missing data and sample tests passed.');
const vm=require('node:vm');
async function runPicker(expected, switchComplex=false, retry=false, noLease=false, batchDelay=null, filterDelay=0){
  const nodes=[], inputs=['ALL','A1','B1','B2','B3'].map((value,i)=>({value,id:'trade'+i,checked:i===0}));
  let py=false,sort=false,foreign=false,scrolls=0,clip='',elapsed=0,requestedAt=null;
  const pendingFilters=[];const buttons={};
  const button=label=>buttons[label]||=({pressed:false,getAttribute(){return String(this.pressed)},click(){this.pressed=!this.pressed;}});
  const scroller={scrollHeight:1000,clientHeight:100,scrollTop:0,dispatchEvent(){scrolls++;if(requestedAt===null)requestedAt=elapsed;}};
  const marker={getAttribute:()=> 'true',querySelectorAll:()=>(noLease?['매매']:['매매','전세']).map((x,i)=>({querySelector:s=>({textContent:s==='.type'?x:String(i?0:expected)})}))};
  const doc={body:{append(){}},createElement(tag){const e={tag,style:{},setAttribute(){},removeAttribute(){},children:[],append(...n){this.children.push(...n)},remove(){},select(){}};nodes.push(e);return e;},
    getElementById:id=>['140148COMPLEX','2COMPLEX'].includes(id)?marker:inputs.find(e=>e.id===id),
    querySelector(s){
      if(s==='#complex_pyeong_tab_list')return {};
      if(s.startsWith('.filter_popup--dealtype input[value='))return inputs.find(e=>s.includes('"'+e.value+'"'));
      if(s.includes('aria-label="면적 선택"')||s.includes('aria-label="동 선택"')||s.includes('aria-label="거래방식"'))return button(s);
      if(s.includes('제곱미터로 평형전환'))return {getAttribute:()=>String(!py),click(){py=false}};
      if(s.includes('평으로 평형전환'))return {getAttribute:()=>String(py),click(){py=true}};
      if(s.includes('value="-1"')||s==='#housesize0'||s==='#number0')return {checked:true};
      if(s.endsWith('.btn_close_panel'))return {click(){}};
      if(s==='#address_group2')return {checked:false};
      if(s==='[data-nclk="TAA.price"]')return {getAttribute:()=>String(sort),get textContent(){return sort?'낮은가격순':'가격순'},click(){sort=true}};
      if(s.startsWith('label[for="trade')){let e=inputs.find(e=>s.includes(e.id));return {htmlFor:e.id,click(){pendingFilters.push({at:elapsed+filterDelay,e,wanted:!e.checked});}};}
      if(s==='#articleListArea')return scroller;
      throw Error('Unhandled selector '+s);
    },querySelectorAll(s){
      if(s==='#summaryInfo dt')return noLease?[{textContent:'전세가',nextElementSibling:{textContent:'-'}}]:[];
      if(s==='.filter_popup--dealtype input')return inputs;
      if(s==='#complex_pyeong_tab_list [role="tab"]')return [{textContent:'116A㎡',title:'전용면적 84.15㎡'}];
      return [];
    }};
  const ctx={document:doc,location:{hostname:'new.land.naver.com',get pathname(){return foreign?'/complexes/2':'/complexes/140148'}},alert:m=>{throw Error(m)},
    navigator:{clipboard:{writeText:async t=>{clip=t}}},getComputedStyle:()=>({overflowY:'auto'}),Event:class{},
    Date:class extends Date {static now(){return elapsed;}},
    setTimeout:(fn,ms)=>{elapsed+=ms;for(const task of pendingFilters){if(task.at<=elapsed){task.e.checked=task.wanted;inputs[0].checked=false;task.at=Infinity;}}if(switchComplex)foreign=true;fn()},
    naverSummary:()=>({name:'단지',households:'780',approvalDate:'2024-01-30'}),
    naverArea:require('../naver_extract.js').naverArea,
    naverOptions:()=>[{id:'housesize1',value:'1',label:py?'35A평':'116A㎡'}],
    naverListings:()=>[{trade:'매매',price:'12억 5,000',spec:'116A/84m²',name:'단지 101동'},
      ...(batchDelay!==null&&requestedAt!==null&&elapsed-requestedAt>=batchDelay ? [{trade:'전세',price:'6억',spec:'116A/84m²',name:'단지 102동'}] : [])],summarizeNaverTypes,naverExpectedCount,naverWaitFor};
  vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../naver_picker.js'),'utf8'),ctx);
  const start=nodes.find(e=>e.textContent==='매매·전세 수집 시작');
  // Browser dispatch continues bubbling after an async handler first yields.
  // Naver's outside-click listener then closes any filter already opened.
  const dispatchStart=()=>{
    let stopped=false;
    const pending=start.onclick({stopPropagation(){stopped=true;}});
    if(!stopped)for(const b of Object.values(buttons))b.pressed=false;
    return pending;
  };
  const pending=dispatchStart();
  assert.equal(start.textContent,'수집 중…');assert.equal(start.disabled,true);
  assert.ok(nodes.some(e=>e.tag==='p'&&e.textContent.includes('수집 중')));
  await pending;
  if(retry){
    foreign=true;
    const copyButton=nodes.find(e=>e.textContent==='결과 복사');await copyButton.onclick();
    assert.equal(clip,'');assert.equal(copyButton.disabled,true);
    await dispatchStart();
  }
  assert.equal(start.disabled,false);
  const copy=nodes.find(e=>e.textContent==='결과 복사');if(!copy.disabled)await copy.onclick();
  return {clip,scrolls,elapsed,status:nodes.filter(e=>e.tag==='p').map(e=>e.textContent).join('\n')};
}
(async()=>{
 const complete=await runPicker(1);assert.ok(complete.clip.startsWith('SISEPICKER_NAVER_V1\n'));
 assert.equal(JSON.parse(complete.clip.split('\n')[1]).types[0].sale,'12.5');
 assert.equal(JSON.parse(complete.clip.split('\n')[1]).complete,true);
 const noLease=await runPicker(1,false,false,true);
 assert.equal(JSON.parse(noLease.clip.split('\n')[1]).complete,true);
 assert.equal(JSON.parse(noLease.clip.split('\n')[1]).types[0].lease,'-');
 const partial=await runPicker(2);assert.equal(JSON.parse(partial.clip.split('\n')[1]).complete,false);
 assert.equal(JSON.parse(partial.clip.split('\n')[1]).types[0].lease,'?');
 const changed=await runPicker(1,true);assert.equal(changed.clip,'');assert.match(changed.status,/단지가 바뀌었습니다/);
 const retried=await runPicker(1,false,true);assert.equal(JSON.parse(retried.clip.split('\n')[1]).complexId,'2');
 const delayedFilter=await runPicker(1,false,false,false,null,4000);assert.ok(delayedFilter.clip,'4-second filter response should finish');
 const stuckFilter=await runPicker(1,false,false,false,null,Infinity);assert.equal(stuckFilter.clip,'');assert.match(stuckFilter.status,/매매 필터.*8초/);
 const fast=await runPicker(2,false,false,false,100);
 const slow=await runPicker(2,false,false,false,1800);
 for(const run of [fast,slow]) {
   const data=JSON.parse(run.clip.split('\n')[1]);assert.equal(data.complete,true);assert.equal(data.types[0].lease,'6.0');
 }
 assert.ok(fast.elapsed<slow.elapsed);assert.ok(fast.elapsed-complete.elapsed<1100);
 assert.ok(partial.elapsed-complete.elapsed>=5500,'No-progress timeout must not be shortened');
 let clock=0;
 const timing={now:()=>clock,sleep:async ms=>{clock+=ms;},timeoutMs:1000,settleMs:200};
 assert.equal(await naverWaitFor(()=>clock>=100&&!(clock>=200&&clock<350),timing),true);
 assert.equal(clock,550,'Transient readiness must restart the settling period');
 clock=0;assert.equal(await naverWaitFor(()=>false,timing),false);assert.equal(clock,1000);
 clock=0;await assert.rejects(naverWaitFor(()=>false,{...timing,guard:()=>{if(clock>=150)throw Error('cancelled');}}),/cancelled/);
 assert.equal(clock,150,'Cancellation must interrupt polling');
 console.log(`Simulated two-listing collection: fast ${fast.elapsed}ms, slow ${slow.elapsed}ms; partial ${partial.elapsed}ms.`);
 console.log('Bookmarklet flow: filters, copy, partial loading and cancellation passed.');
})().catch(e=>{console.error(e);process.exitCode=1});

function countDoc(entries, prices={}, active=true) {
  return {getElementById:()=>active===null?null:{getAttribute:()=>String(active),querySelectorAll:()=>entries.map(([trade,count])=>({querySelector:s=>({textContent:s==='.type'?trade:count})}))},
    querySelectorAll:()=>Object.entries(prices).map(([textContent,price])=>({textContent,nextElementSibling:{textContent:price}}))};
}
assert.equal(naverExpectedCount(countDoc([['매매','1']],{'전세가':'-'}),'8798'),1);
assert.equal(naverExpectedCount(countDoc([['전세','2']],{'매매가':'-'}),'1'),2);
assert.equal(naverExpectedCount(countDoc([],{'매매가':'-','전세가':'-'}),'1'),0);
for(const prices of [{},{'전세가':''},{'전세가':'8억'}])assert.equal(naverExpectedCount(countDoc([['매매','1']],prices),'1'),null);
assert.equal(naverExpectedCount(countDoc([['매매','']],{'전세가':'-'}),'1'),null);
assert.equal(naverExpectedCount(countDoc([['매매','1'],['매매','1']],{'전세가':'-'}),'1'),null);
assert.equal(naverExpectedCount(countDoc([['매매','1']],{'전세가':'-'},false),'1'),null);
assert.equal(naverExpectedCount(countDoc([],{},null),'1'),null);
console.log('Zero-listing confirmation and unknown count tests passed.');

const assert=require('node:assert/strict');
const {naverPrice,naverArea,summarizeNaverTypes}=require('../naver_extract.js');
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
async function runPicker(expected, switchComplex=false, retry=false){
  const nodes=[], inputs=['ALL','A1','B1','B2','B3'].map((value,i)=>({value,id:'trade'+i,checked:i===0}));
  let py=false,sort=false,foreign=false,scrolls=0,clip='';
  const buttons={};
  const button=label=>buttons[label]||=( {getAttribute:()=> 'true',click(){}} );
  const scroller={scrollHeight:1000,clientHeight:100,scrollTop:0,dispatchEvent(){scrolls++}};
  const marker={querySelectorAll:()=>['매매','전세'].map((x,i)=>({querySelector:s=>({textContent:s==='.type'?x:String(i?0:expected)})}))};
  const doc={body:{append(){}},createElement(tag){const e={tag,style:{},setAttribute(){},removeAttribute(){},children:[],append(...n){this.children.push(...n)},remove(){},select(){}};nodes.push(e);return e;},
    getElementById:id=>['140148COMPLEX','2COMPLEX'].includes(id)?marker:null,
    querySelector(s){
      if(s==='#complex_pyeong_tab_list')return {};
      if(s.includes('aria-label="면적 선택"')||s.includes('aria-label="동 선택"')||s.includes('aria-label="거래방식"'))return button(s);
      if(s.includes('제곱미터로 평형전환'))return {getAttribute:()=>String(!py),click(){py=false}};
      if(s.includes('평으로 평형전환'))return {getAttribute:()=>String(py),click(){py=true}};
      if(s.includes('value="-1"')||s==='#housesize0'||s==='#number0')return {checked:true};
      if(s.endsWith('.btn_close_panel'))return {click(){}};
      if(s==='#address_group2')return {checked:false};
      if(s==='[data-nclk="TAA.price"]')return {getAttribute:()=>String(sort),get textContent(){return sort?'낮은가격순':'가격순'},click(){sort=true}};
      if(s.startsWith('label[for="trade')){let e=inputs.find(e=>s.includes(e.id));return {click(){e.checked=!e.checked;inputs[0].checked=false}};}
      if(s==='#articleListArea')return scroller;
      throw Error('Unhandled selector '+s);
    },querySelectorAll(s){
      if(s==='.filter_popup--dealtype input')return inputs;
      if(s==='#complex_pyeong_tab_list [role="tab"]')return [{textContent:'116A㎡',title:'전용면적 84.15㎡'}];
      return [];
    }};
  const ctx={document:doc,location:{hostname:'new.land.naver.com',get pathname(){return foreign?'/complexes/2':'/complexes/140148'}},alert:m=>{throw Error(m)},
    navigator:{clipboard:{writeText:async t=>{clip=t}}},getComputedStyle:()=>({overflowY:'auto'}),Event:class{},
    setTimeout:fn=>{if(switchComplex)foreign=true;fn()},
    naverSummary:()=>({name:'단지',households:'780',approvalDate:'2024-01-30'}),
    naverArea:require('../naver_extract.js').naverArea,
    naverOptions:()=>[{id:'housesize1',value:'1',label:py?'35A평':'116A㎡'}],
    naverListings:()=>[{trade:'매매',price:'12억 5,000',spec:'116A/84m²',name:'단지 101동'}],summarizeNaverTypes};
  vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../naver_picker.js'),'utf8'),ctx);
  const start=nodes.find(e=>e.textContent==='매매·전세 수집 시작');
  const pending=start.onclick();
  assert.equal(start.textContent,'수집 중…');assert.equal(start.disabled,true);
  assert.ok(nodes.some(e=>e.tag==='p'&&e.textContent.includes('수집 중')));
  await pending;
  if(retry){
    foreign=true;
    const copyButton=nodes.find(e=>e.textContent==='결과 복사');await copyButton.onclick();
    assert.equal(clip,'');assert.equal(copyButton.disabled,true);
    await start.onclick();
  }
  assert.equal(start.disabled,false);
  const copy=nodes.find(e=>e.textContent==='결과 복사');if(!copy.disabled)await copy.onclick();
  return {clip,scrolls,status:nodes.filter(e=>e.tag==='p').map(e=>e.textContent).join('\n')};
}
(async()=>{
 const complete=await runPicker(1);assert.ok(complete.clip.startsWith('SISEPICKER_NAVER_V1\n'));
 assert.equal(JSON.parse(complete.clip.split('\n')[1]).types[0].sale,'12.5');
 assert.equal(JSON.parse(complete.clip.split('\n')[1]).complete,true);
 const partial=await runPicker(2);assert.equal(JSON.parse(partial.clip.split('\n')[1]).complete,false);
 assert.equal(JSON.parse(partial.clip.split('\n')[1]).types[0].lease,'?');
 const changed=await runPicker(1,true);assert.equal(changed.clip,'');assert.match(changed.status,/단지가 바뀌었습니다/);
 const retried=await runPicker(1,false,true);assert.equal(JSON.parse(retried.clip.split('\n')[1]).complexId,'2');
 console.log('Bookmarklet flow: filters, copy, partial loading and cancellation passed.');
})().catch(e=>{console.error(e);process.exitCode=1});

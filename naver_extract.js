/* Read only DOM adapter. No private API, cookies, or page application state. */
function naverPrice(text) {
  const s = String(text).replace(/[\s,]/g, '').replace(/만원$/, '');
  const m = /^(?:(\d+(?:\.\d+)?)억)?(\d+)?$/.exec(s);
  if (!m || (!m[1] && !m[2])) throw new Error('해석할 수 없는 가격: ' + text);
  const won = Math.round(Number(m[1] || 0) * 10000) + Number(m[2] || 0);
  if (!(won > 0)) throw new Error('가격이 0입니다.');
  return won;
}
function naverArea(text) {
  const m = /^(\d+(?:\.\d+)?)((?:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)?)\s*(㎡|m²|평)?$/i.exec(text.trim());
  if (!m) throw new Error('면적 형식 확인 필요: ' + text);
  return {number: Number(m[1]), suffix: m[2], unit: m[3] || '', key: m[1] + m[2]};
}
function naverSummary(doc) {
  const name = doc.querySelector('#complexTitle')?.textContent.trim();
  const values = {};
  for (const dt of doc.querySelectorAll('#summaryInfo .complex_feature dt'))
    values[dt.textContent.trim()] = dt.nextElementSibling?.textContent.trim() || '';
  const households = values['세대수']?.replace(/,/g, '').match(/(\d+)\s*세대/)?.[1];
  const date = values['사용승인일']?.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (!name || !households || !date) throw new Error('단지를 선택하고 단지정보를 열어 주세요. 세대수/사용승인일을 읽지 못했습니다.');
  return {name, households, approvalDate: `${date[1]}-${date[2].padStart(2,'0')}-${date[3].padStart(2,'0')}`};
}
function naverOptions(doc) {
  return [...doc.querySelectorAll('.filter_popup--type-list input[name="housesize"]')]
    .filter(e=>e.value !== '-1').map(e=>({id:e.id,value:e.value,label:doc.querySelector(`label[for="${e.id}"]`).textContent.trim()}));
}
function naverListings(doc) {
  return [...doc.querySelectorAll('#articleListArea .item_link')].map(el=>({
    trade:el.querySelector('.price_line .type')?.textContent.trim(),
    price:el.querySelector('.price_line .price')?.textContent.trim(),
    spec:el.querySelector('.info_area .spec')?.textContent.trim(),
    name:el.querySelector('.item_title .text')?.textContent.trim()
  }));
}
function summarizeNaver(types, listings, complete=false) {
  const groups = new Map(), byType = new Map();
  for (const t of types) {
    if (!(t.pyeong > 0 && t.pyeong < 40)) continue;
    if (byType.has(t.key)) throw new Error('중복 면적 유형: ' + t.key);
    byType.set(t.key, t);
    if (!groups.has(t.pyeong)) groups.set(t.pyeong,{pyeong:String(t.pyeong),types:[],exclusiveAreas:[],sale:null,lease:null});
    const g=groups.get(t.pyeong);g.types.push(t.key);
    if (t.exclusive && !g.exclusiveAreas.includes(t.exclusive)) g.exclusiveAreas.push(t.exclusive);
  }
  let errors=0;
  for (const item of listings) {
    if (!['매매','전세'].includes(item.trade)) continue;
    try {
      const match = /^(\d+(?:\.\d+)?(?:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)?)\s*\/\s*(\d+(?:\.\d+)?)\s*(m²|㎡)/i.exec(item.spec || '');
      if (!match) throw new Error('면적 읽기 실패');
      const type=byType.get(match[1]);
      if (!type) {
        if (!types.some(t=>t.key===match[1])) throw new Error('알 수 없는 면적');
        continue;
      }
      const g=groups.get(type.pyeong), price=naverPrice(item.price), field=item.trade==='매매'?'sale':'lease';
      g[field]=g[field]===null?price:Math.min(g[field],price);
      if (!g.exclusiveAreas.includes(match[2])) g.exclusiveAreas.push(match[2]);
    } catch(e) {errors++;}
  }
  const decimal = x => {const s=(x/10000).toFixed(4).replace(/0+$/,'').replace(/\.$/,'');return s.includes('.')?s:s+'.0';};
  return {groups:[...groups.values()].sort((a,b)=>Number(a.pyeong)-Number(b.pyeong)).map(g=>({...g,
    sale:g.sale===null?(complete&&!errors?'-':'?'):decimal(g.sale),
    lease:g.lease===null?(complete&&!errors?'-':'?'):decimal(g.lease)})),errors};
}
if (typeof module !== 'undefined') module.exports={naverPrice,naverArea,naverSummary,naverOptions,naverListings,summarizeNaver};
function summarizeNaverTypes(types, listings, complete=false) {
  const map=new Map(types.map(t=>[t.key,{key:t.key,supplyPyeong:String(t.pyeong),exclusiveArea:t.exclusive||'',sale:null,lease:null}]));
  if(map.size!==types.length)throw new Error('면적 유형이 중복됩니다.');
  let errors=0;
  for(const item of listings){
    if(!['매매','전세'].includes(item.trade))continue;
    try{
      const match=/^(\d+(?:\.\d+)?(?:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)?)\s*\/\s*(\d+(?:\.\d+)?)\s*(m²|㎡)/i.exec(item.spec||'');
      const t=match&&map.get(match[1]);if(!t)throw new Error('면적 연결 실패');
      if(!t.exclusiveArea)t.exclusiveArea=match[2];
      if(Math.floor(Number(t.exclusiveArea))!==Math.floor(Number(match[2])))throw new Error('전용면적 충돌');
      const field=item.trade==='매매'?'sale':'lease',price=naverPrice(item.price);
      t[field]=t[field]===null?price:Math.min(price,t[field]);
    }catch(e){errors++;}
  }
  const price=x=>{if(x===null)return complete&&!errors?'-':'?';const s=(x/10000).toFixed(4).replace(/0+$/,'').replace(/\.$/,'');return s.includes('.')?s:s+'.0';};
  return {types:[...map.values()].map(t=>({...t,sale:price(t.sale),lease:price(t.lease)})),errors};
}
if(typeof module!=='undefined')module.exports.summarizeNaverTypes=summarizeNaverTypes;

// A missing trade button is not automatically zero: require explicit no-price
// text in the selected complex summary as independent DOM evidence.
function naverExpectedCount(doc, complexId) {
  const marker=doc.getElementById(complexId+'COMPLEX');
  if(!marker || marker.getAttribute('aria-pressed')!=='true')return null;
  const counts=new Map();
  for(const link of marker.querySelectorAll('.article_link')) {
    const trade=link.querySelector('.type')?.textContent.trim();
    if(!['매매','전세'].includes(trade))continue;
    const raw=link.querySelector('.count')?.textContent.trim().replace(/,/g,'');
    if(!raw || !/^\d+$/.test(raw) || counts.has(trade))return null;
    const count=Number(raw);if(!Number.isSafeInteger(count))return null;
    counts.set(trade,count);
  }
  const prices=new Map();
  for(const dt of doc.querySelectorAll('#summaryInfo dt')) {
    const label=dt.textContent.trim();
    if(['매매가','전세가'].includes(label))prices.set(label,dt.nextElementSibling?.textContent.trim());
  }
  for(const trade of ['매매','전세']) {
    if(!counts.has(trade)) {
      if(prices.get(trade+'가')!=='-')return null;
      counts.set(trade,0);
    }
  }
  return counts.get('매매')+counts.get('전세');
}
if(typeof module!=='undefined')module.exports.naverExpectedCount=naverExpectedCount;

// Yield to the browser between checks. Readiness must remain true for settleMs;
// a timeout is never proof that all listings have been collected.
async function naverWaitFor(ready, {guard=()=>{}, timeoutMs=1500, settleMs=0,
  intervalMs=50, sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)), now=()=>Date.now()}={}) {
  const started=now();let since=null;
  while(true) {
    guard();const time=now();
    if(ready()) {
      if(since===null)since=time;
      if(time-since>=settleMs)return true;
    } else since=null;
    if(time-started>=timeoutMs)return false;
    await sleep(Math.min(intervalMs,timeoutMs-(time-started)));
  }
}
if(typeof module!=='undefined')module.exports.naverWaitFor=naverWaitFor;

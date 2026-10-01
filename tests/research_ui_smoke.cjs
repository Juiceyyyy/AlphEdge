const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
class Element {
  constructor(){this.children=[];this.value='0';this.checked=true;this.textContent='';this.innerHTML='';this.handlers={};this.classList={toggle(){}}}
  append(...items){this.children.push(...items)}
  appendChild(item){this.children.push(item);this.firstChild=this.children[0]}
  removeChild(){this.children.shift();this.firstChild=this.children[0]}
  replaceChildren(){this.children=[];this.firstChild=null}
  addEventListener(type,fn){this.handlers[type]=fn}
  setAttribute(){}
  get childElementCount(){return this.children.length}
}
const els=new Map();const get=id=>els.get(id)||(els.set(id,new Element()),els.get(id));
Object.assign(get('lump'),{value:'100000'});Object.assign(get('sip'),{value:'10000'});
Object.assign(get('start-month'),{value:'2023-01'});Object.assign(get('end-month'),{value:'2025-12'});
Object.assign(get('holdings'),{value:'10'});
const overview={backtest:{kpis:{cagr_pct:40.69,max_drawdown_pct:-20.91,sharpe:1.93,benchmark_cagr_pct:10.11},yearly:Array.from({length:14},(_,i)=>({year:2012+i,return_pct:12,bench_return_pct:8}))},windows:[{label:'W1',cagr_pct:20,bench_cagr_pct:10,max_dd_pct:-12}]};
const basket={date:'2026-09-25',computed_at:'2026-09-29T12:00:00Z',risk_on:true,positions:[{ticker:'TEST.NS',weight:.6},{ticker:'EXAMPLE.NS',weight:.4}]};
const scenario={kpis:{cagr_pct:22,max_drawdown_pct:-18},months:Array.from({length:36},(_,i)=>({date:`2023-${String(i%12+1).padStart(2,'0')}-28`,strategy_return:.01,benchmark_return:.005}))};
overview.scenarios={computed_at:'2026-09-29T12:00:00Z',variants:{'1/1/10':scenario,'0/1/10':scenario}};
overview.rolling_windows=[{start:'2020-01-01',end:'2022-12-31',cagr_pct:20,bench_cagr_pct:10,max_dd_pct:-12}];
overview.snapshot={price_date:'2026-09-25',forward:[{date:'2026-09-25',model_index:100,benchmark_index:100}],basket};
const fetch=async url=>({ok:true,json:async()=>url.endsWith('/scenario')?scenario:url.endsWith('/candidates')?basket:overview});
const document={getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element(),createTextNode:t=>t};
vm.runInNewContext(fs.readFileSync('dashboard/explorer.js','utf8'),{document,fetch,Intl,Number,Math,Array,Error,AbortController,setTimeout,clearTimeout,setInterval:()=>{},Date});
setTimeout(async()=>{
  assert.equal(get('kpi-cagr').textContent,'22.00%');
  assert.equal(get('annual-results').children.length,14);
  assert.equal(get('window-results').children.length,1);
  assert.equal(get('rolling-results').children.length,1);
  assert.equal(get('candidate-positions').children.length,2);
  assert.equal(get('forward-model').textContent,'100.00');
  assert.equal(get('candidate-positions').children[0].children[1].textContent,'60.0%');
  get('trend').checked=false;get('trend').handlers.input();
  assert.match(get('candidate-status').textContent,/Refresh holdings/);
  assert.match(get('chart-mode').textContent,/Saved scenario/);
  get('sip').value='20000';get('sip').handlers.input();
  assert.match(get('contributed-total').textContent,/₹/);
  console.log('Research UI interactions passed');
},30);

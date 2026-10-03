const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
class Element{
 constructor(){this.children=[];this.value='';this.checked=true;this.textContent='';this.handlers={};this.attrs={};this.classes=new Set();this.classList={toggle(){},remove(){},add:name=>this.classes.add(name)};this.dataset={};this.style={};}
 append(...items){this.children.push(...items);this.firstChild=this.children[0]}
 replaceChildren(){this.children=[];this.firstChild=null}
 addEventListener(type,fn){this.handlers[type]=fn}
 setAttribute(name,value){this.attrs[name]=String(value)}
 get childElementCount(){return this.children.length}
}
const els=new Map(),get=id=>els.get(id)||(els.set(id,new Element()),els.get(id));
Object.assign(get('lump'),{value:'100000'});Object.assign(get('sip'),{value:'10000'});
Object.assign(get('holdings'),{value:'10'});Object.assign(get('model-holdings'),{value:'10'});Object.assign(get('risk-profile'),{value:'moderate'});Object.assign(get('model-risk-profile'),{value:'moderate'});
Object.assign(get('growth-chart'),{clientWidth:320,clientHeight:220});
const months=Array.from({length:36},(_,i)=>({date:`2023-${String(i%12+1).padStart(2,'0')}-28`,strategy_return:.01,benchmark_return:.005}));
const scenario={kpis:{cagr_pct:22,max_drawdown_pct:-18,sharpe:1.2,benchmark_cagr_pct:8,start:'2011',end:'2026'},months};
const basket={date:'2026-09-25',risk_on:true,positions:[{ticker:'TEST.NS',weight:.6},{ticker:'EXAMPLE.NS',weight:.4}]};
const benchmarkData={strategy_id:'hold-five-v1',data_through:'2026-09-25',initial:{midcap150:100,smallcap250:100},monthly:months.map((m,i)=>({date:m.date,midcap150:100*Math.pow(1.001,i),smallcap250:100*Math.pow(1.0005,i)}))};
const manifest={benchmarks:benchmarkData,backtest:{yearly:[]},research:{strategy_id:'hold-five-v1',variants:{'1/1/10/5':{annual:[{year:2025,return_pct:12,bench_return_pct:8},{year:2024,return_pct:-4,bench_return_pct:2}],windows:[{start:'2023',end:'2025',label:'2023–2025',cagr_pct:6,bench_cagr_pct:9,max_dd_pct:-12}],active_window:null}}},holdings:{strategy_id:'hold-five-v1',baskets:{'1/1/10/5':basket,'1/1/6/5':basket,'1/1/15/5':basket,'1/1/15/0':{date:'2026-09-25',risk_on:false,positions:[]}}},snapshot:{strategy_id:'hold-five-v1',forward:[],basket}};
const paths={strategy_id:'hold-five-v1',data_through:'2026-09-25',variants:{'1/1/10/5':scenario,'1/1/15/5':scenario,'0/1/10/0':scenario,'0/1/6/0':scenario}};
let requests=0;
const fetch=async url=>{requests++;return{ok:true,json:async()=>url.endsWith('/scenarios')?paths:manifest}};
const buttons=['12','36','60','120','all'].map(p=>Object.assign(new Element(),{dataset:{period:p}}));
const riskControls=['risk-profile','model-risk-profile'].map(id=>{
 const choices=['low','moderate','aggressive'].map(risk=>Object.assign(new Element(),{dataset:{risk}}));
 return Object.assign(new Element(),{dataset:{riskControl:id},querySelectorAll:()=>choices,style:{setProperty(name,value){this[name]=value}}});
});
const document={getElementById:get,querySelectorAll:selector=>selector==='[data-risk-control]'?riskControls:buttons,createElement:()=>new Element(),createElementNS:()=>new Element()};
vm.runInNewContext(fs.readFileSync('dashboard/explorer.js','utf8'),{document,window:{ALPHEDGE_STATIC:false},fetch,Intl,Number,Math,Array,Error,setInterval:()=>{},Date});
setTimeout(()=>{
 assert.equal(get('kpi-cagr').textContent,'22.00%');
 assert.equal(get('annual-results').children.length,2);
 assert.ok(get('annual-results').children[0].children[1].classes.has('return-winner'));
 assert.ok(get('annual-results').children[1].children[2].classes.has('return-winner'));
 assert.ok(get('window-results').children[0].children[2].classes.has('return-winner'));
 assert.ok(get('rolling-results').children[0].children[2].classes.has('return-winner'));
 assert.equal(get('candidate-positions').children.length,2);
 assert.match(get('contributed-total').textContent,/₹/);
 assert.match(get('midcap-total').textContent,/₹/);
 assert.equal(get('growth-chart').children.filter(c=>c.attrs.stroke==='#ddac68').length,1);
 const before=requests;
 riskControls[0].querySelectorAll()[2].handlers.click();
 assert.equal(get('risk-profile').value,'aggressive');
 assert.equal(riskControls[0].dataset.active,'aggressive');
 riskControls[0].querySelectorAll()[1].handlers.click();
 get('holdings').value='15';get('holdings').handlers.input();
 basket.risk_on=false;
 get('model-holdings').value='15';get('model-holdings').handlers.input();
 assert.equal(get('holdings-value').textContent,'15 stocks');
 assert.equal(get('model-holdings-value').textContent,'15 stocks');
 assert.match(get('basket-note').textContent,/earlier holdings/);
 riskControls[1].querySelectorAll()[0].handlers.click();
 assert.match(get('candidate-status').textContent,/100% cash/);
 get('model-holdings').value='6';get('model-holdings').handlers.input();
 assert.equal(requests,before,'controls replay cached paths without network calls');
 assert.match(get('chart-mode').textContent,/Saved path/);
 assert.equal(get('growth-chart').attrs.viewBox,'0 0 320 220','chart uses available phone width');
 console.log('Cached research UI interactions passed');
},30);

const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
class Element{
 constructor(){this.children=[];this.value='';this.checked=true;this.textContent='';this.handlers={};this.classList={toggle(){},remove(){}};this.dataset={};this.style={};}
 append(...items){this.children.push(...items);this.firstChild=this.children[0]}
 replaceChildren(){this.children=[];this.firstChild=null}
 addEventListener(type,fn){this.handlers[type]=fn}
 setAttribute(){}
 get childElementCount(){return this.children.length}
}
const els=new Map(),get=id=>els.get(id)||(els.set(id,new Element()),els.get(id));
Object.assign(get('lump'),{value:'100000'});Object.assign(get('sip'),{value:'10000'});
Object.assign(get('holdings'),{value:'10'});Object.assign(get('model-holdings'),{value:'10'});
const months=Array.from({length:36},(_,i)=>({date:`2023-${String(i%12+1).padStart(2,'0')}-28`,strategy_return:.01,benchmark_return:.005}));
const scenario={kpis:{cagr_pct:22,max_drawdown_pct:-18,sharpe:1.2,benchmark_cagr_pct:8,start:'2011',end:'2026'},months};
const basket={date:'2026-09-25',risk_on:true,positions:[{ticker:'TEST.NS',weight:.6},{ticker:'EXAMPLE.NS',weight:.4}]};
const manifest={backtest:{yearly:[]},research:{variants:{'1/1/10':{annual:[{year:2025,return_pct:12,bench_return_pct:8}],windows:[],active_window:null}}},holdings:{baskets:{'1/1/10':basket}},snapshot:{forward:[],basket}};
const paths={data_through:'2026-09-25',variants:{'1/1/10':scenario,'0/1/10':scenario,'0/1/6':scenario}};
let requests=0;
const fetch=async url=>{requests++;return{ok:true,json:async()=>url.endsWith('/scenarios')?paths:manifest}};
const buttons=['12','36','60','120','all'].map(p=>Object.assign(new Element(),{dataset:{period:p}}));
const document={getElementById:get,querySelectorAll:()=>buttons,createElement:()=>new Element(),createElementNS:()=>new Element()};
vm.runInNewContext(fs.readFileSync('dashboard/explorer.js','utf8'),{document,fetch,Intl,Number,Math,Array,Error,setInterval:()=>{},Date});
setTimeout(()=>{
 assert.equal(get('kpi-cagr').textContent,'22.00%');
 assert.equal(get('annual-results').children.length,1);
 assert.equal(get('candidate-positions').children.length,2);
 assert.match(get('contributed-total').textContent,/₹/);
 const before=requests;
 get('trend').checked=false;get('trend').handlers.input();
 get('model-holdings').value='6';get('model-holdings').handlers.input();
 assert.equal(requests,before,'controls replay cached paths without network calls');
 assert.match(get('chart-mode').textContent,/Saved path/);
 console.log('Cached research UI interactions passed');
},30);

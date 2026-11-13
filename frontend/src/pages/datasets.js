import {datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';

const canWrite=()=>session.user.role!=='viewer';

function countCard(label,value,tone=''){
 return '<div class="count-card '+tone+'"><span>'+esc(label)+'</span><strong>'+esc(value??0)+'</strong></div>';
}

function reasonTable(rows,emptyText){
 if(!rows?.length)return '<div class="empty">'+esc(emptyText)+'</div>';
 const cols=[{key:'row_index',label:'原始行号'},{key:'batch_id',label:'批次号'},{key:'reason',label:'原因'}];
 return table(cols,rows);
}

function reviewPanel(d){
 if(!d)return '<div class="empty">尚无批次。请先接入业务数据。</div>';
 const c=d.counts||{};
 const q=d.quality||{};
 const banner=c.isolated>0
   ? '<p class="warning">该批次含 '+esc(c.isolated)+' 条隔离工况，分群不会使用；请在下方修正隔离记录后生成新数据批次。</p>'
   : (c.duplicate>0?'<p class="hint">重复工况已自动去重，分群仅使用 '+esc(c.valid)+' 条有效批次。</p>':'<p class="hint">全部记录均为唯一有效批次，可直接用于分群。</p>');
 const validCols=[{key:'batch_id',label:'批次号'},...workspace.meta.columns.filter(x=>x.key!=='batch_id')];
 return '<div class="section-title"><h2 id="preview-name">'+esc(d.name)+'</h2><span>'+(d.origin_id?'修正批次 · 源自 #'+esc(d.origin_id):'原始接入批次')+'</span></div>'
  +'<div class="count-grid">'
  +countCard('原始记录',c.raw)+countCard('有效批次',c.valid,'ok')
  +countCard('重复去重',c.duplicate,'dup')+countCard('隔离记录',c.isolated,'bad')+'</div>'
  +'<p class="hint">核对恒等式：原始 '+esc(c.raw)+' = 有效 '+esc(c.valid)+' + 重复 '+esc(c.duplicate)+' + 隔离 '+esc(c.isolated)+'。</p>'
  +banner
  +'<section class="panel compact"><div class="section-title"><h2>有效批次（用于分群）</h2><span>前 30 条 · 共 '+esc(c.valid)+' 条</span></div><div id="data-preview">'+table(validCols,(d.records||[]).slice(0,30))+'</div></section>'
  +'<section class="panel compact"><div class="section-title"><h2>重复工况明细</h2><span>'+esc(c.duplicate)+' 条已丢弃</span></div>'+reasonTable(q.duplicates,'无重复工况。相同批次号且工况一致时仅保留首条。')+'</section>'
  +'<section class="panel compact"><div class="section-title"><h2>隔离记录明细与原因</h2><span>'+esc(c.isolated)+' 条已隔离</span></div>'+reasonTable(q.isolated,'无隔离记录。')+'</section>';
}

export async function dataPage(){
 workspace.datasets=await datasets.list();
 const first=workspace.datasets[0];
 const selected=first?await datasets.get(first.id):null;
 const m=workspace.meta;
 const listHtml=workspace.datasets.map(d=>{
   const c=d.counts||{};
   const flag=c.isolated>0?'<small class="flag-bad">隔离 '+esc(c.isolated)+'</small>':(c.duplicate>0?'<small class="flag-dup">去重 '+esc(c.duplicate)+'</small>':'<small class="flag-ok">全部有效</small>');
   return '<button class="batch-item" data-dataset="'+d.id+'"><strong>'+esc(d.name)+'</strong><span>原始 '+esc(d.raw_rows??d.rows)+' 条 · 有效 '+esc(d.rows)+' 条 · '+esc(d.source)+'</span><small>SHA256 '+esc(d.checksum.slice(0,18))+'…</small>'+flag+'</button>';
 }).join('');
 return heading('02 / DATA INTAKE','数据接入与批次核对','按批次号核对：相同工况只留一条；工况冲突整组及无效工况隔离并注明原因；分群仅使用有效批次。')
 +'<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>业务批次</h2><span>'+workspace.datasets.length+' 批</span></div><div class="batch-list">'+(listHtml||'<div class="empty">尚无批次</div>')+'</div>'
 +'<div class="section-title"><h2>接入新数据</h2></div><form id="dataset-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：11 月复测批次"></label><label>上传 CSV 或 JSON<input type="file" id="file-input" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="6" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">字段：'+m.columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。5–5,000 条记录。无效与冲突记录会被隔离而非拒绝整批。</p><button type="submit" class="primary" '+(canWrite()?'':'disabled')+'>核对并接入批次</button></form></section>'
 +'<section class="panel" id="review-panel">'+reviewPanel(selected)+(selected&&selected.counts?.isolated>0?correctionForm(selected):'')+'</section></div>';
}

function correctionForm(d){
 const payload=JSON.stringify(d.raw_records||[],null,2);
 return '<section class="panel compact correction"><div class="section-title"><h2>修正隔离记录并生成新数据批次</h2><span>原批次保持不变</span></div>'
 +'<p class="hint">下方已预填该批次的原始记录。按隔离明细修正冲突与无效工况后提交：系统重新核对并生成新批次，原批次及已有分析不变；同一次修正重复提交不会新增批次。</p>'
 +'<form id="correction-form" data-origin="'+d.id+'"><label>新批次名称<input name="name" required minlength="2" value="'+esc(d.name)+' · 修正版"></label><label>修正后完整记录 JSON<textarea name="records" rows="10" required>'+esc(payload)+'</textarea></label><button type="submit" class="primary" '+(canWrite()?'':'disabled')+'>重新核对并生成批次</button></form></section>';
}

export function bindData(refresh){
 let source='manual.json';
 document.querySelector('#file-input')?.addEventListener('change',async e=>{
  try{const file=e.target.files[0];if(!file)return;source=file.name;const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('[name=records]').value=JSON.stringify(records,null,2);}
  catch(error){notify(error.message,true);}
 });
 document.querySelectorAll('[data-dataset]').forEach(button=>button.onclick=async()=>{
  try{const d=await datasets.get(button.dataset.dataset);const panel=document.querySelector('#review-panel');panel.innerHTML=reviewPanel(d)+(d.counts?.isolated>0?correctionForm(d):'');bindCorrection(refresh);}
  catch(error){notify(error.message,true);}
 });
 submit(document.querySelector('#dataset-form'),async f=>{
  await datasets.create({name:f.get('name'),source,records:JSON.parse(f.get('records'))});
  notify('数据已核对接入，可前往工作台执行分析');await refresh();
 });
 bindCorrection(refresh);
}

function bindCorrection(refresh){
 const form=document.querySelector('#correction-form');
 if(!form)return;
 submit(form,async f=>{
  const originId=Number(form.dataset.origin);
  const r=await datasets.correct(originId,{name:f.get('name'),source:'correction.json',origin_id:originId,records:JSON.parse(f.get('records'))});
  notify(r.idempotent?'该修正已提交过，返回既有批次，未新增':'修正批次已生成，原批次保持不变');
  await refresh();
 });
}

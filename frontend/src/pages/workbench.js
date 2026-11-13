import {datasets,jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
export async function workbench(){
 workspace.datasets=await datasets.list();const m=workspace.meta;
 return heading('03 / ANALYSIS LAB',m.workbench_title,'选择业务批次和分析口径。参数、输入指纹与计算结论随任务保存，便于复核和复现。')+'<div class="workbench-grid"><section class="panel"><form id="job-form"><label>分析任务名称<input name="name" required minlength="2" value="'+esc(m.name)+' · 复核试算"></label><label>数据批次<select name="dataset_id" required>'+workspace.datasets.map(d=>'<option value="'+d.id+'">'+esc(d.name)+' · 有效 '+d.rows+' 条'+(d.counts?.isolated?(' · 隔离 '+d.counts.isolated):'')+'</option>').join('')+'</select></label><p class="hint" id="dataset-quality-hint">分群仅消费各批次核对后的有效记录；重复工况已去重，冲突与无效工况已隔离。</p><div class="parameter-grid">'+m.parameters.map(p=>'<label>'+esc(p.label)+(p.type==='select'?'<select name="param-'+esc(p.key)+'">'+p.options.map(o=>'<option value="'+esc(o.value)+'" '+(o.value==p.default?'selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select>':'<input type="number" step="any" name="param-'+esc(p.key)+'" value="'+esc(p.default)+'" min="'+esc(p.min??'')+'" max="'+esc(p.max??'')+'" required>')+'</label>').join('')+'</div><button type="submit" class="primary" '+(session.user.role==='viewer'||!workspace.datasets.length?'disabled':'')+'>'+esc(m.action_label||'执行分析')+' ↗</button><p class="hint">提交后由后台任务计算。观察员可查看参数和结果，无法提交。</p></form></section><section class="method-sheet"><p class="eyebrow">METHOD / BUSINESS RULE</p><h2>'+esc(m.method)+'</h2><p>'+esc(m.tagline)+'</p><h3>业务判读边界</h3><ul>'+m.limitations.map(v=>'<li>'+esc(v)+'</li>').join('')+'</ul><div class="method-trace"><span>输入</span><strong>'+esc(m.dataset_name)+'</strong><span>输出</span><strong>可复核结果 / 参数版本 / 分发归档</strong></div></section></div>';
}
export function bindWorkbench(){
 const select=document.querySelector('[name=dataset_id]');
 const hint=document.querySelector('#dataset-quality-hint');
 const syncHint=()=>{const d=workspace.datasets.find(x=>String(x.id)===select?.value);if(!d)return;const c=d.counts||{};hint.textContent=c.isolated>0?('该批次原始 '+c.raw+' 条：有效 '+c.valid+'、重复 '+c.duplicate+'、隔离 '+c.isolated+'；分群仅使用有效批次，隔离记录请到数据接入页修正。'):('该批次原始 '+(c.raw??d.rows)+' 条：有效 '+(c.valid??d.rows)+' 条'+(c.duplicate?('，重复去重 '+c.duplicate+' 条'):'，无隔离记录。'));};
 select?.addEventListener('change',syncHint);syncHint();
 submit(document.querySelector('#job-form'),async f=>{const params={};for(const p of workspace.meta.parameters){const value=f.get('param-'+p.key);params[p.key]=p.type==='number'?Number(value):value;}const j=await jobs.create({name:f.get('name'),dataset_id:Number(f.get('dataset_id')),params});workspace.selectedJob=j.id;notify('分析任务已提交');location.hash='#/results/'+j.id;});}

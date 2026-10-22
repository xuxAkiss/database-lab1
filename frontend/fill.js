'use strict';
const $=s=>document.querySelector(s),token=decodeURIComponent(location.pathname.split('/').pop()),base='/api/fill/'+encodeURIComponent(token);
const intentKey='work1_submit:'+token;
const white=/[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u;
let csrf,context,structure,draft,versionNumber,localValue,generation=0,savedGeneration=0,timer,saving=null,blocked=false,busy=false;
const own=(obj,key)=>Object.hasOwn(obj,key)?obj[key]:undefined;
function message(t,error=false){$('#message').textContent=t;$('#message').classList.toggle('error',error);}
async function api(path,body){const r=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});const d=await r.json();if(!r.ok){const e=Error(d.message||'请求失败');e.data=d;e.status=r.status;throw e;}return d;}
function el(tag,text,parent){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(parent)parent.append(n);return n;}
function button(parent,text,fn){const n=el('button',text,parent);n.type='button';n.onclick=()=>run(fn);return n;}
function qcurrent(){return structure.questions.find(q=>q.id===draft?.current);}
function clientError(q,v){if(!q)return '';const len=q.type==='text'?Array.from(v||'').filter(c=>!white.test(c)).length:(v||[]).length;if(!len)return q.required?'此题必答。':'';
 if(q.type==='multiple'){if(q.exact_choices!==null&&q.exact_choices!==undefined&&len!==q.exact_choices)return `必须恰好选择 ${q.exact_choices} 项。`;if(q.min_choices!=null&&len<q.min_choices)return `至少选择 ${q.min_choices} 项。`;if(q.max_choices!=null&&len>q.max_choices)return `最多选择 ${q.max_choices} 项。`;}
 if(q.type==='text'){if(q.min_length!=null&&len<q.min_length)return `去除空白后至少 ${q.min_length} 字。`;if(q.max_length!=null&&len>q.max_length)return `去除空白后最多 ${q.max_length} 字。`;}
 if(q.type==='number'){if(!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(v)||!Number.isFinite(Number(v)))return '请输入完整、有限的数字。';const n=Number(v);if(q.integer_only&&!Number.isInteger(n))return '必须为整数。';if(q.minimum!=null&&n<q.minimum)return `不得小于 ${q.minimum}。`;if(q.maximum!=null&&n>q.maximum)return `不得大于 ${q.maximum}。`;}
 return '';}
function changed(value){localValue=value;generation++;$('#save-status').textContent='待自动保存…';$('#validation').textContent=clientError(qcurrent(),localValue);clearTimeout(timer);timer=setTimeout(()=>saveNow().catch(showSaveError),700);}
function showSaveError(e){blocked=true;$('#save-status').textContent='保存失败 / 结果未确认，已停止自动重试。';message(e.message,true);$('#unsaved').hidden=false;$('#unsaved-value').value=JSON.stringify({question_id:draft?.current,value:localValue},null,2);}
async function saveNow(){clearTimeout(timer);if(saving){await saving;return saveNow();}if(generation===savedGeneration)return;if(blocked)throw Error('请先复制未保存内容，再重新读取并核对；不会覆盖其他窗口。');
 const gen=generation, value=structuredClone(localValue), qid=draft.current;$('#save-status').textContent='保存中…';
 saving=(async()=>{draft=await api(`${base}/drafts/${draft.version_id}/action`,{attempt_id:draft.attempt_id,revision:draft.revision,action:'save',question_id:qid,value});savedGeneration=gen;refreshProgress();$('#save-status').textContent=generation===gen?`已保存 · 修订 ${draft.revision}`:'仍有新输入待保存…';})();
 try{await saving;}catch(e){showSaveError(e);throw e;}finally{saving=null;}
 if(generation!==savedGeneration)return saveNow();
}
async function run(fn){if(busy)return;busy=true;$('#body').inert=true;try{await fn();}catch(e){message(e.message,true);}finally{busy=false;$('#body').inert=false;}}
function pendingIntent(){try{return JSON.parse(sessionStorage.getItem(intentKey));}catch{return null;}}
function refreshProgress(){if(!draft)return;$('#version').textContent=`V${versionNumber} · 草稿修订 ${draft.revision}`;$('#progress').textContent=`已访问 ${draft.visited.length}/${structure.questions.length} 题；待答顺序：${draft.pending.map(id=>structure.questions.findIndex(q=>q.id===id)+1).join(' → ')||'无'}`;
 const nav=$('#navigation');nav.replaceChildren();const free=!structure.questions.some(q=>q.rules.length);for(const item of structure.questions){const issue=draft.errors.find(e=>e.question_id===item.id);if(free||draft.visited.includes(item.id)||(draft.ended&&item.required&&issue)){button(nav,`${structure.questions.indexOf(item)+1}. ${item.title}${issue?'（待修正）':''}`,()=>navigate('goto',item.id));}}
}
function render(){const q=qcurrent();$('#body').hidden=false;$('#title').textContent=structure.title;$('#description').textContent=structure.description;
 $('#version').textContent=`V${versionNumber} · ${draft?`草稿修订 ${draft.revision}`:'尚未开始'}`;
 $('#policy').textContent=`${structure.anonymous?'匿名填写：创建者不能通过本入口获得你的身份，后台保留账号关联。':'非匿名填写。'} ${structure.allow_repeat?'本版允许重复，每次成功提交独立保存。':'本版每账号只能成功提交一次。'}`;
 const currentView=!draft||draft.version_id===context.version_id;
 $('#start').hidden=!!draft||context.read_only||!currentView;
 $('#restart').hidden=!draft||draft.status!=='submitted'||!structure.allow_repeat||context.read_only||!currentView;
 $('#retry-submit').hidden=!pendingIntent();
 $('#form').hidden=!draft||draft.read_only;$('#readonly').hidden=!draft||!draft.read_only;
 if(draft?.read_only){const box=$('#readonly');box.replaceChildren();el('h3',draft.reason||'只读记录',box);for(const item of structure.questions){el('h4',item.title,box);const v=own(draft.answers,item.id);const display=item.options?.length?(Array.isArray(v)?v:[v]).map(id=>item.options.find(o=>o.id===id)?.label||'').join('、'):v;el('p',display||'（未填写）',box);}}
 if(draft&&!draft.read_only){$('#progress').textContent=`已访问 ${draft.visited.length}/${structure.questions.length} 题；待答顺序：${draft.pending.map(id=>structure.questions.findIndex(q=>q.id===id)+1).join(' → ')||'无'}`;
 const box=$('#question');box.replaceChildren();$('#validation').textContent='';
 $('#save').hidden=!q;$('#next').hidden=!q;$('#finish').hidden=draft.ended;$('#submit').hidden=!draft.ended;
 if(q){el('h3',`${structure.questions.indexOf(q)+1}. ${q.title}${q.required?'（必答）':''}`,box);localValue=own(draft.answers,q.id)??(q.type==='multiple'?[]:'');
 if(q.type==='single'||q.type==='multiple'){for(const option of q.options){const label=el('label',undefined,box),input=el('input',undefined,label);input.type=q.type==='single'?'radio':'checkbox';input.name='answer';input.checked=q.type==='single'?localValue===option.id:localValue.includes(option.id);label.append(document.createTextNode(option.label));input.onchange=()=>changed(q.type==='single'?option.id:input.checked?[...localValue,option.id]:localValue.filter(id=>id!==option.id));}if(!q.required)button(box,'清空选择',async()=>{changed(q.type==='multiple'?[]:'');await saveNow();render();});}
 else{const label=el('label',q.type==='number'?'数字输入':'文本输入',box),input=el(q.type==='text'?'textarea':'input',undefined,label);input.value=localValue;input.maxLength=q.type==='text'?20000:128;if(q.type==='number')input.inputMode='decimal';input.oninput=()=>changed(input.value);}
 $('#validation').textContent=clientError(q,localValue);
 }else{el('h3','结束检查',box);el('p','提交前后端会检查全卷必答与所有已填答案。',box);for(const e of draft.errors)el('p',`第 ${e.number} 题：${e.message}`,box);}
 refreshProgress();
 }
 const old=$('#old-drafts');old.replaceChildren();if(context.old_drafts.length){el('h3','旧版草稿（仅自己的只读记录）',old);for(const d of context.old_drafts)button(old,`查看旧版 ${d.version_id}`,async()=>{await saveNow();const data=await api(`${base}/drafts/${d.version_id}`);structure=data.structure;versionNumber=data.version_number;draft=data.draft;generation=savedGeneration=0;render();message('旧版记录只读，不会搬入新版。');});}
}
async function load(){clearTimeout(timer);csrf=(await api('/api/auth/csrf')).csrf_token;context=await api(base);structure=context.structure;versionNumber=context.version_number;draft=context.draft;generation=savedGeneration=0;blocked=false;$('#unsaved').hidden=true;render();message(context.reason|| (draft?.status==='submitted'?'本轮已成功提交，历史记录已保留。':'已读取当前版本及此账号的草稿。'));$('#save-status').textContent=draft?(draft.status==='submitted'?'此轮已提交，历史已保存。':'服务器草稿已恢复。'):'';}
async function navigate(action,target){await saveNow();const body={attempt_id:draft.attempt_id,revision:draft.revision,action};if(target)body.target=target;draft=await api(`${base}/drafts/${draft.version_id}/action`,body);generation=savedGeneration=0;render();$('#save-status').textContent=`进度已保存 · 修订 ${draft.revision}`;message('填写进度已保存。');}
async function sendSubmission(intent){const result=await api(`${base}/drafts/${intent.version_id}/submit`,{attempt_id:intent.attempt_id,revision:intent.revision,request_key:intent.request_key});sessionStorage.removeItem(intentKey);await load();message(`提交成功：本版第 ${result.sequence} 次，记录 ${result.submission_id}。`);}
$('#save').onclick=()=>run(async()=>{await saveNow();message('当前输入已保存；是否完整将在下一题或提交时检查。');});
$('#next').onclick=()=>run(()=>navigate('next'));$('#finish').onclick=()=>run(()=>navigate('finish'));
$('#start').onclick=()=>run(async()=>{draft=await api(base+'/start',{version_id:context.version_id});generation=savedGeneration=0;render();$('#save-status').textContent='空白草稿已创建。';message('已开始本版填写。');});
$('#restart').onclick=()=>run(async()=>{draft=await api(base+'/start',{version_id:context.version_id,new_attempt:true,previous_attempt_id:draft.attempt_id});generation=savedGeneration=0;render();$('#save-status').textContent='新一轮空白草稿已创建。';message('新一轮为空白；旧的成功提交继续保留。');});
$('#submit').onclick=()=>run(async()=>{await saveNow();let intent=pendingIntent();if(!intent||intent.attempt_id!==draft.attempt_id||intent.revision!==draft.revision){intent={version_id:draft.version_id,attempt_id:draft.attempt_id,revision:draft.revision,request_key:crypto.randomUUID()};sessionStorage.setItem(intentKey,JSON.stringify(intent));}$('#retry-submit').hidden=false;try{await sendSubmission(intent);}catch(e){if(e.status===422){sessionStorage.removeItem(intentKey);$('#retry-submit').hidden=true;}throw e;}});
$('#retry-submit').onclick=()=>run(async()=>{const intent=pendingIntent();if(intent)await sendSubmission(intent);});
$('#reload').onclick=()=>run(async()=>{if(generation!==savedGeneration&&!confirm('当前有未确认保存的输入，请先复制。确认重新读取服务器记录？'))return;if(saving)await saving.catch(()=>{});await load();});
window.addEventListener('beforeunload',e=>{if(generation!==savedGeneration){e.preventDefault();e.returnValue='';}});
run(load);

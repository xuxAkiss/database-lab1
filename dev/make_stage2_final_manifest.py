"""Build a separate full stage-two delivery inventory; never rewrite old manifests."""
import hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
allowed={'.py','.ps1','.js','.html','.css','.md','.txt','.json','.cfg','.png'}
files=[]
for folder in ('backend','frontend','tests','dev','docs'):
 for p in (ROOT/folder).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix in allowed and p.name!='stage2-final-manifest.json':files.append(p)
for n in ['README.md','requirements.in','requirements.txt','requirements-test.txt','.env.example','.gitignore','.gitattributes','stage2_baseline.py']:files.append(ROOT/n)
start=json.loads((ROOT/'docs/stage2-final-start.json').read_text(encoding='utf-8'))
changed=[];added=[]
for p in files:
 rel=p.relative_to(ROOT).as_posix();h=hashlib.sha256(p.read_bytes()).hexdigest()
 if rel in start['files']:
  if start['files'][rel]!=h:changed.append(rel)
 else:added.append(rel)
protected=[n for n in start['files'] if n.startswith('docs/') and (n.startswith('docs/stage1-') or n.endswith('-results.txt') or n.endswith('integration-final.txt') or n.endswith('integration-schema.txt') or n in ['docs/baseline-manifest.json','docs/stage2-manifest.json'])]
for n in protected:assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==start['files'][n],f'Preserved evidence changed: {n}'
summary='''# 本轮改动摘要与交付检查

基于本轮开始时含022未提交成果的实际工作区，而非假设HEAD就是022。HEAD仍为e0b3391。保留全部原数据；没有提交或推送。

## 主要变化
- 新增只读跨卷统计后端与页面；固定题版本、本人问卷、历史发布替换、同卷实例选择、最新整份提交、频数与分页。
- 在原main.py注册入口，原surveys.py增加submissions索引，题库与原问卷前端加统计链接。
- 原认证/填写/单卷统计代码未改；022题身份、版本、共享、快照保存机制沿用。
- 完善报告、八项演进、完整需求覆盖、API/数据库/逻辑、测试和AI日志；022需更新文档先保存在022-preserved。
- 新增测试工具依赖仅在项目.venv，业务依赖与.env不变。未触碰日志.txt或用户Word。

## 检查结果
真实跨卷C01–C11、022 S01–S09、原认证/发布/填写/统计、27项单元及浏览器复测通过。阶段一525条、本轮前762条业务记录哈希不变。浏览器修复提示遮挡和表格间距后复测；pip check通过，git diff空白检查通过（保留CRLF）。

旧阶段一/022测试输出和清单的哈希与本轮起始文件快照比较通过，共检查 %d 个证据文件。最终清单排除自身，以避免自引用；交付清单内文件加清单本身。排除.venv/.local/真实.env/凭据/缓存/数据库目录。

## 相对起始文件快照发生变化的文件
%s

## 当前新增文件
%s

列表只表示文件变化，不表示用户手写贡献。README未包含在起始files映射中，但已作为022-preserved/README.md保留；应将它理解为更新文件。新增列表包含本轮保存的022副本。
'''%(len(protected),'\n'.join('- '+x for x in sorted(changed)), '\n'.join('- '+x for x in sorted(added)))
p=ROOT/'docs/stage2-final-changes.md';p.write_text(summary,encoding='utf-8')
if p not in files:files.append(p)
rows=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
result={'stage':'stage2-complete-local-delivery','base_head':start['head'],'generated_at':datetime.now(timezone.utc).isoformat(),'preserves':['docs/baseline-manifest.json','docs/stage2-manifest.json','docs/022-preserved'],'excludes':['.venv','.local','.env','credentials','__pycache__','database files'],'note':'Includes all source/config/docs/test evidence. Add this manifest itself; not a database backup or Git commit.','files':rows}
(ROOT/'docs/stage2-final-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows:assert hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256']
print('PASS preserved evidence files',len(protected),'delivery files',len(rows),'all manifest hashes checked')

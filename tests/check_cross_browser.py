"""Real UI-only flow against local app; no API seeding or browser-evaluate shortcuts."""
import json,secrets,sys
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]; E=ROOT/'docs/evidence';BASE='http://127.0.0.1:8000'
RUN='qa_cross_ui_'+uuid4().hex[:8];PASSWORD=secrets.token_urlsafe(24)
errors=[];warnings=[]
with sync_playwright() as pw:
 browser=pw.chromium.launch(channel='msedge',headless=True)
 context=browser.new_context(viewport={'width':1280,'height':900});p=context.new_page();p.set_default_timeout(15000)
 p.on('pageerror',lambda e:errors.append(str(e)))
 p.on('console',lambda e:warnings.append(e.text) if e.type in ('warning','error') else None)
 try:
  p.goto(BASE);p.locator('#show-register').click();p.locator('#register-username').fill(RUN);p.locator('#register-password').fill(PASSWORD);p.get_by_role('button',name='创建账号',exact=True).click();expect(p.locator('#message')).to_have_text('注册成功，请登录。');p.locator('#login-password').fill(PASSWORD);p.get_by_role('button',name='登录账号',exact=True).click();expect(p.locator('#signed-in')).to_be_visible()
  p.get_by_role('link',name='管理我的问卷').click();p.get_by_role('link',name='题目与题库').click();expect(p.locator('#workspace')).to_be_visible()
  p.locator('#type').select_option('number');p.locator('#title').fill(RUN+' 年龄');p.locator('#minimum').fill('0');p.locator('#maximum').fill('120');p.locator('#save').click();expect(p.locator('#message')).to_contain_text('保存成功 V1')
  stats_link=p.locator('#cross-statistics').get_attribute('href');qid=stats_link.split('/')[2].split('?')[0];qv1=stats_link.split('version=')[1]
  print('PASS UI create independent numeric question',flush=True)
  def make(label):
   p.goto(BASE+'/manage');expect(p.locator('#workspace')).to_be_visible();p.locator('#create input').fill(RUN+' '+label);p.get_by_role('button',name='创建问卷',exact=True).click();expect(p.locator('#editor')).to_be_visible();p.locator('#load-library').click();expect(p.locator('#library-question option')).to_have_count(1);p.locator('#import-question').click();p.locator('#save').click();expect(p.locator('#message')).to_contain_text('已保存修订');p.locator('#publish').click();expect(p.locator('#message')).to_contain_text('发布 V1 成功');return {'label':RUN+' '+label,'share':p.locator('#share').get_attribute('href')}
  def fill(s,value):
   p.goto(BASE+s['share']);p.locator('#start').click();p.get_by_label('数字输入').fill(value);p.locator('#next').click();expect(p.locator('#submit')).to_be_visible();p.locator('#submit').click();expect(p.locator('#message')).to_contain_text('提交成功')
  A=make('A');fill(A,'0');B=make('B');fill(B,'8')
  p.goto(BASE+stats_link);expect(p.locator('#message')).to_contain_text('查询成功');expect(p.locator('#summary')).to_contain_text('纳入问卷数：2');expect(p.locator('#summary')).to_contain_text('有效回答数：2');expect(p.locator('#results')).to_contain_text('平均值：4');p.screenshot(path=str(E/'stage2-final-browser-current.png'),full_page=True)
  print('PASS UI reuse two surveys/publish/fill/current stats [0,8] average4',flush=True)
  p.goto(BASE+'/manage');p.get_by_role('button',name=A['label']+' · V1',exact=True).click();expect(p.locator('#editor')).to_be_visible();p.locator('#description').fill('QA second publication');p.locator('#save').click();expect(p.locator('#message')).to_contain_text('已保存修订');p.locator('#publish').click();expect(p.locator('#message')).to_contain_text('发布 V2 成功');fill(A,'10')
  p.goto(BASE+stats_link);expect(p.locator('#message')).to_contain_text('查询成功');expect(p.locator('#results')).to_contain_text('平均值：9')
  acard=p.locator('#scope article').filter(has=p.get_by_role('heading',name=A['label'],exact=True));acard.get_by_label('问卷发布版本').select_option(label='问卷 V1 · '+A['label']);p.locator('#query').click();expect(p.locator('#message')).to_contain_text('查询成功');expect(p.locator('#results')).to_contain_text('平均值：4');expect(p.locator('#included')).to_contain_text('问卷 V1');p.screenshot(path=str(E/'stage2-final-browser-history.png'),full_page=True)
  print('PASS UI history replaces A V2, current avg9 -> historical avg4',flush=True)
  p.goto(BASE+'/library');p.get_by_role('button',name=RUN+' 年龄 · V1 · 我的',exact=True).click();expect(p.locator('#heading')).to_have_text('编辑自己的题目');p.locator('#title').fill(RUN+' 年龄新版');p.locator('#save').click();expect(p.locator('#message')).to_contain_text('保存成功 V2');qv2=p.locator('#cross-statistics').get_attribute('href').split('version=')[1]
  p.goto(BASE+'/manage');p.get_by_role('button',name=A['label']+' · V2',exact=True).click();expect(p.locator('#editor')).to_be_visible();p.locator('#load-library').click();expect(p.locator('#library-version option')).to_have_count(2);p.locator('#library-version').select_option(qv2);p.get_by_role('button',name='换为选中的题库版本').click();p.locator('#save').click();expect(p.locator('#message')).to_contain_text('已保存修订');p.locator('#publish').click();expect(p.locator('#message')).to_contain_text('发布 V3 成功');fill(A,'20')
  p.goto(BASE+'/question-statistics/'+qid);expect(p.locator('#message')).to_contain_text('查询成功');p.locator('#question-version').select_option(qv2);p.locator('#query').click();expect(p.locator('#message')).to_contain_text('查询成功');expect(p.locator('#results')).to_contain_text('平均值：20');expect(p.locator('#summary')).to_contain_text('纳入问卷数：1');expect(p.locator('#summary')).to_contain_text('题目 V2')
  p.screenshot(path=str(E/'stage2-final-browser-question-v2.png'),full_page=True)
  print('PASS UI question-version switch isolates V2 average20',flush=True)
  assert p.title()=='跨问卷题目统计' and p.locator('h1').inner_text()=='跨问卷题目统计'
  assert not errors,errors
  # Auth landing intentionally receives 401 /auth/me before logging in; no other console errors allowed.
  relevant=[w for w in warnings if '401' not in w]
  assert not relevant,relevant
  p.set_viewport_size({'width':390,'height':844});p.screenshot(path=str(E/'stage2-final-browser-mobile.png'),full_page=True)
  assert p.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'horizontal overflow'
  print('PASS UI page identity/nonblank/no runtime error/mobile no horizontal overflow',flush=True)
  (ROOT/'docs/stage2-final-browser-results.json').write_text(json.dumps({'run':RUN,'browser':'Microsoft Edge via Playwright 1.64.1','reason':'Browser plugin not available','viewports':[[1280,900],[390,844]],'page_errors':errors,'console_messages':warnings,'question_id':qid,'question_versions':[qv1,qv2],'surveys':[A,B],'result':'PASS'},ensure_ascii=False,indent=2),encoding='utf-8')
 except Exception:
  p.screenshot(path=str(E/'stage2-final-browser-failure.png'),full_page=True)
  print('FAIL UI',p.url, 'message:',p.locator('#message').inner_text() if p.locator('#message').count() else '',flush=True)
  raise
 finally:browser.close()

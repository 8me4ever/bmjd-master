"""Exercise the standalone HTML in Chromium, with a temporary local server and database.

Requires Playwright and an installed Chromium; does not change BMJD catalogs.
The loopback origin avoids managed Chromium's file-URL policy. After loading,
offline mode verifies that normal editing and export have no network dependency.
"""
import argparse
import hashlib
import json
import shutil
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
JD = '分析岗位业务需求并明确工作目标。\n制定具体实施计划并协调相关资源。\n跟踪执行进度并处理职责范围内问题。\n整理工作成果并提出后续改进建议。'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, default=ROOT/'BMJD持续补全工具_20261029/BMJD岗位持续补全.html')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    checks = {}

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks[name] = True
        print('PASS '+name, flush=True)

    class Quiet(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(args.html.resolve().parent), **kw)
        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
    Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'+quote(args.html.name)
    original = json.loads((ROOT/'岗位JD匹配审查_20261029/岗位JD主库.json').read_text())
    errors, remote = [], []
    try:
        with tempfile.TemporaryDirectory(prefix='bmjd-browser-') as temp, sync_playwright() as p:
            temp = Path(temp)
            executable = shutil.which('chromium') or shutil.which('chromium-browser')
            browser = p.chromium.launch(**({'executable_path': executable} if executable else {}), args=['--no-sandbox'])
            context = browser.new_context(viewport={'width': 1440, 'height': 1100}, accept_downloads=True)

            def open_page(ctx=context):
                page = ctx.new_page()
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('request', lambda r: remote.append(r.url) if r.url.startswith(('http:', 'https:')) and not r.url.startswith(f'http://127.0.0.1:{server.server_port}/') else None)
                page.goto(url)
                page.wait_for_function('window.BMJDTool?.ready === true', timeout=60000)
                return page

            def state(page):
                return page.evaluate('window.BMJDTool.getState()')

            def wait_records(page, count):
                page.wait_for_function('(n)=>Number(document.getElementById("record-total").textContent)===n', arg=count)

            def fill(page, suffix):
                page.locator('#function-input').fill('人力资源')
                page.locator('#series-select').select_option('__new__')
                page.locator('#series-name').fill('持续补全验证方向'+suffix)
                page.locator('#job-name').fill('持续补全验证专员'+suffix)
                page.locator('#industry-options input[value="高科技"]').check(force=True)
                page.locator('#job-jd').fill(JD)

            def download(page, kind):
                with page.expect_download() as info:
                    page.locator('#export-'+kind).click()
                path = temp/info.value.suggested_filename
                info.value.save_as(path)
                return path

            def upload(page, path):
                revision = state(page)['revision']
                page.locator('#import-file').set_input_files(str(path))
                page.wait_for_function('(v)=>document.getElementById("load-message").hidden && (document.getElementById("form-error").hidden===false || window.BMJDTool.getState().then(s=>s.revision>v))', arg=revision)
                page.wait_for_function('document.getElementById("load-message").hidden')

            page = open_page()
            check('完整主库及263职能成功载入', page.locator('#base-count').inner_text() == '9,111' and len(state(page)['functions']) == 263)
            fill(page, 'A')
            candidate = page.locator('#suggested-code').get_attribute('data-code')
            check('推荐代码避让13164个已知代码', candidate not in state(page)['knownCodes'] and len(state(page)['knownCodes']) == 13164)
            page.locator('#save-job').click()
            wait_records(page, 1)
            first = state(page)['records'][0]
            check('保存规范JD及人工来源标记', first['job']['code'] == candidate and len(first['job']['jd_clauses']) == 4 and first['job']['source_ids'] == [])
            page.reload();page.wait_for_function('window.BMJDTool?.ready === true', timeout=60000)
            check('刷新后新增记录完整恢复', state(page)['records'][0] == first)
            page.locator('[data-edit]').click()
            page.locator('#job-name').fill('持续补全验证修订专员A')
            page.locator('#save-job').click()
            page.wait_for_function('document.querySelector(".job-label")?.textContent.includes("修订")')
            check('编辑名称JD保持原代码', state(page)['records'][0]['job']['code'] == candidate)
            page.locator('[data-status="withdrawn"]').click()
            page.wait_for_function('document.querySelector(".record-status")?.textContent==="已撤回"')
            check('撤回仍保留编码', candidate in state(page)['knownCodes'])
            page.locator('[data-status="active"]').click()
            page.wait_for_function('document.querySelector(".record-status")?.textContent==="活动新增"')
            check('恢复仍使用原代码', state(page)['records'][0]['job']['code'] == candidate)

            second = open_page()
            fill(page, 'B');fill(second, 'C')
            check('双窗口共享同一保存前建议码', page.locator('#suggested-code').get_attribute('data-code') == second.locator('#suggested-code').get_attribute('data-code'))
            page.evaluate('document.getElementById("job-form").requestSubmit()')
            second.evaluate('document.getElementById("job-form").requestSubmit()')
            wait_records(page, 3);wait_records(second, 3)
            codes = [r['job']['code'] for r in state(page)['records']]
            check('双窗口事务分配不同代码且无记录丢失', len(codes) == len(set(codes)) == 3)
            second.close()

            fill(page, '重复')
            page.locator('#job-name').fill(original['jobs'][0]['name'])
            page.locator('#save-job').click()
            page.wait_for_function('!document.getElementById("form-error").hidden')
            check('重复名称阻止保存', len(state(page)['records']) == 3 and '重复' in page.locator('#form-error').inner_text())
            page.locator('#reset-form').click()
            fill(page, '文本')
            text = '<img src=x onerror="window.__injected=1">验证专员'
            page.locator('#job-name').fill(text)
            page.locator('#save-job').click();wait_records(page, 4)
            check('名称按纯文本呈现', page.locator('.job-label').first.inner_text() == text and not page.locator('#records-body img').count() and not page.evaluate('Boolean(window.__injected)'))
            page.locator('[data-detail]').filter(visible=True).first.click()
            check('原岗位JD可只读查看', page.locator('#job-dialog').is_visible() and page.locator('#detail-clauses li').count() > 0)
            page.locator('#job-dialog .close-dialog').click()
            if args.screenshots:
                args.screenshots.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(args.screenshots/'桌面预览.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            check('手机页面无横向溢出', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
            if args.screenshots:
                page.screenshot(path=str(args.screenshots/'手机预览.png'), full_page=True)
            page.set_viewport_size({'width': 1440, 'height': 1100})
            context.set_offline(True)
            fill(page, '离线');page.locator('#save-job').click();wait_records(page, 5)
            full = download(page, 'full');delta = download(page, 'delta');csv = download(page, 'csv')
            out = json.loads(full.read_text())
            check('断网后可新增并导出三种文件', len(out['jobs']) == 9116 and csv.read_bytes().startswith(b'\xef\xbb\xbf'))
            check('完整导出全部9111个旧岗位逐值不变', out['jobs'][:9111] == original['jobs'])
            check('全部导出代码及ID唯一', len({j['code'] for j in out['jobs']}) == len({j['id'] for j in out['jobs']}) == 9116)
            context.set_offline(False)

            fresh = browser.new_context(accept_downloads=True)
            fresh_page = open_page(fresh)
            upload(fresh_page, delta);wait_records(fresh_page, 5)
            upload(fresh_page, delta)
            check('增量导入可重复且无重复岗位', len(state(fresh_page)['records']) == 5)
            conflict = json.loads(delta.read_text());conflict['records'][0]['job']['name'] = '冲突岗位新版本'
            bad = temp/'conflict.json';bad.write_text(json.dumps(conflict, ensure_ascii=False))
            before = state(fresh_page)
            upload(fresh_page, bad)
            check('冲突增量整批回滚', state(fresh_page) == before and not fresh_page.locator('#form-error').is_hidden())
            upload(fresh_page, full)
            check('完整主库回导后新增转为已并入', len(state(fresh_page)['baseJobs']) == 9116 and all(r['status']=='integrated' for r in state(fresh_page)['records']))
            again = json.loads(download(fresh_page, 'full').read_text())
            check('完整回导再导出无岗位重复', len(again['jobs']) == 9116 and again['jobs'][:9111] == original['jobs'])
            fresh.close()

            fallback = browser.new_context(accept_downloads=True)
            fallback.add_init_script('Object.defineProperty(window,"indexedDB",{get(){throw new Error("storage disabled by test")}})')
            fp = open_page(fallback)
            check('存储不可用时明确提示仅会话模式', fp.locator('#storage-warning').is_visible() and fp.locator('#storage-status').inner_text() == '仅本次会话')
            fill(fp, '内存');fp.locator('#save-job').click();wait_records(fp, 1)
            check('会话模式仍可导出备份', len(json.loads(download(fp, 'delta').read_text())['records']) == 1)
            fallback.close()
            check('无外部资源请求', not remote)
            check('浏览器无未处理脚本异常', not errors)
            browser.close()
    finally:
        server.shutdown();server.server_close()
    report = {'all_passed': all(checks.values()), 'passed': len(checks), 'checks': checks,
              'html_sha256': hashlib.sha256(args.html.read_bytes()).hexdigest(),
              'scope': 'Chromium; loopback HTTP loaded once, offline edits and exports; file URL blocked by environment policy and not bypassed', 'errors': errors, 'external_requests': remote}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

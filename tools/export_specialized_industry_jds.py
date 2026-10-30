"""Export industry-only JD revisions, preserving the delivered parent workbooks."""
import argparse
import collections
import shutil
from pathlib import Path

from export_industry_masters import new_workbook,write_sheet,validate_workbook
from specialize_industry_jds import DIRECTORY,INDUSTRIES,read,table_rows


CHANGE_HEADER=['行业','岗位ID','岗位代码','岗位名称','改写原因','主库JD（未修改）','本行业子库新JD','专业框架','本行业来源ID']


def change_rows(records):
    return [CHANGE_HEADER]+[[r['industry'],r['job_id'],r['code'],r['name'],r['reason'],r['old_jd'],r['new_jd'],r['selected_profile'],
                            '、'.join(s['source_id'] for s in r['local_source_context'])] for r in records if r['changed']]


def notes(overview,industry=None):
    s=overview['summary']
    return [['项目','说明'],['版本',overview['version']],['当前范围',industry or '全部11个行业子库'],
            ['本轮原则','仅在新版本行业子库改写专业性不足的JD；主库及上版子库文件不修改。'],
            ['数量',f"审查{s['reviewed_industry_jobs']}条行业岗位记录，改写{s['modified_industry_jobs']}条，保留{s['retained_industry_jobs']}条。"],
            ['通用职能','人力、行政、一般财务等通用职能保持原稿，不按行业标签机械改写。'],
            ['改写条件','明确专业岗位、本行业真实来源、主库通用补写框架和关键专业职责缺口同时成立。'],
            ['岗位身份','岗位ID、代码、名称、职能、系列、层级、行业范围及来源保持原样；跨行业仍共享同一码。'],
            ['JD格式','改写稿沿用1、2、3、编号，每份4或5条，按原岗位管理、专业或辅助边界编写。'],
            ['查看对照','“改写前后对照”仅列本轮修改的岗位。主库原稿保留，行业新稿不回写主库。'],
            ['依据标注','新条款为行业专业补写，未伪造原文引用；本行业方向来源及原始定位保存于JSON台账。'],
            ['数据字段','JSON中的jd_review_*及jd_profile继承主库基础审查记录；industry_jd_revision表示本轮行业修订。'],
            ['源级约束','原23条暂缓来源不恢复；身份推定标记不因行业JD改写而清除。']]


def export(download=None):
    overview=read(DIRECTORY/'子库优化总览.json');records=read(DIRECTORY/'逐岗行业JD审查台账.json')
    grouped=collections.defaultdict(list)
    for r in records:grouped[r['industry']].append(r)
    combined=new_workbook('BMJD 11行业专业JD优化')
    overview_rows=[['行业','岗位数','行业JD改写','保留原稿','通用职能保留','唯一代码数','父库版本','本轮版本','说明']]
    for r in overview['industries']:
        overview_rows.append([r['industry'],r['jobs'],r['modified'],r['retained'],r['decision_counts'].get('保留-通用职能',0),r['jobs'],
                              overview['global_master_version'],overview['version'],'仅修改本行业子库JD'])
    combined_sheets={'行业优化总览':overview_rows};write_sheet(combined,'行业优化总览',overview_rows)
    for industry in INDUSTRIES:
        child=read(DIRECTORY/industry/'岗位主库.json');local=grouped[industry]
        rows=table_rows(child,local);changes=change_rows(local)
        counts=collections.defaultdict(collections.Counter)
        for r in local:counts[r['function_name']]['改写' if r['changed'] else '保留']+=1
        stats=[['职能','岗位数','本轮改写','本轮保留']]+[[f,sum(c.values()),c['改写'],c['保留']] for f,c in sorted(counts.items())]
        sheets={'岗位主库':rows,'改写前后对照':changes,'职能统计':stats,'使用说明':notes(overview,industry)}
        path=DIRECTORY/industry/'岗位主库.xlsx'
        if path.exists():validate_workbook(path,sheets)
        else:
            workbook=new_workbook('BMJD '+industry+'专业JD优化')
            for title,data in sheets.items():
                sheet=write_sheet(workbook,title,data,title=='岗位主库')
                if title=='改写前后对照':
                    for col,width in zip('ABCDEFGHI',[16,28,14,43,65,110,110,28,55]):sheet.column_dimensions[col].width=width
                    for n in range(2,sheet.max_row+1):sheet.row_dimensions[n].height=145
                if title=='使用说明':sheet.column_dimensions['B'].width=115
            workbook.save(path);validate_workbook(path,sheets)
        combined_sheets[industry]=rows;write_sheet(combined,industry,rows,True)
    combined_sheets['改写前后对照']=change_rows(records)
    sheet=write_sheet(combined,'改写前后对照',combined_sheets['改写前后对照'])
    for col,width in zip('ABCDEFGHI',[16,28,14,43,65,110,110,28,55]):sheet.column_dimensions[col].width=width
    for n in range(2,sheet.max_row+1):sheet.row_dimensions[n].height=145
    combined_sheets['使用说明']=notes(overview);sheet=write_sheet(combined,'使用说明',combined_sheets['使用说明']);sheet.column_dimensions['B'].width=115
    path=DIRECTORY/'BMJD_11行业专业JD优化.xlsx'
    if path.exists():validate_workbook(path,combined_sheets)
    else:combined.save(path);validate_workbook(path,combined_sheets)
    if download:
        target=Path(download);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.read_bytes()!=path.read_bytes():raise ValueError('下载副本已存在不同内容，不覆盖。')
        if not target.exists():shutil.copyfile(path,target)
    print('11份行业Excel及总工作簿已导出，包含全部改写前后对照。')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--download',type=Path);args=p.parse_args();export(args.download)

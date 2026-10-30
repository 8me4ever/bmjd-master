from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
p=ROOT/'BMJD主库浏览器/app.js';s=p.read_text(encoding='utf-8')
s=s.replace('aria-label="已收录来源 7692 条，占 40.0%；待匹配来源 11557 条，占 60.0%"','aria-label="已收录来源 ${s.admitted_source_records} 条，占 ${(s.admitted_source_records/s.source_records*100).toFixed(1)}%；待匹配来源 ${s.pending_source_records} 条，占 ${(s.pending_source_records/s.source_records*100).toFixed(1)}%"')
s=s.replace('>40.0%</span>','>${(s.admitted_source_records/s.source_records*100).toFixed(1)}%</span>')
s=s.replace('>60.0%</span>','>${(s.pending_source_records/s.source_records*100).toFixed(1)}%</span>')
old="...(sourceByPrefix.get(p[0])||[]).map(i=>{const s=D.source_index[i];"
assert old in s
s=s.replace(old,"...(sourceByPrefix.get(p[0])||[]).filter(i=>D.source_index[i][7]==='待匹配').map(i=>{const s=D.source_index[i];",1)
p.write_text(s,encoding='utf-8')
p=ROOT/'BMJD主库浏览器/使用说明.md';s=p.read_text(encoding='utf-8').replace('3,165 个已收录岗位','3,166 个已收录岗位').replace('489 个多版本 JD 岗位','490 个多版本 JD 岗位')
s+='\n## GM001 收录修正\n\nGM001 已作为“总经理（集团）”收录，保留“总经理”“总经理/行长”为完整别名。11 个行业核心职责已核对一致。GM00 的其他岗位及字典标签仍需规范，不会连带把 GM001 放回待匹配。JD 来源版式保留供后续统一。\n'
p.write_text(s,encoding='utf-8')
p=ROOT/'BMJD主库浏览器/交付核查.md';s=p.read_text(encoding='utf-8')
s=s.replace('3,165 个唯一代码岗位','3,166 个唯一代码岗位').replace('7,692 条，待匹配来源 11,557 条','7,703 条，待匹配来源 11,546 条').replace('489 个多版本 JD 岗位','490 个多版本 JD 岗位')
s+='\n## GM001 修正验证\n\nGM001 新增11条已收录来源；原有3,165个主库岗位逐字段未变，其他来源记录未变。去除行首编号、标点及空白后，GM001的11行业职责文本完全一致。待匹配检索只索引待匹配来源，已收录的GM001不再触发GM00的待匹配结果。候选排查清单列出556个仅标签门槛阻挡的代码，其中410个核心JD文本一致；它们是后续复核候选，本次未批量自动确认。\n'
p.write_text(s,encoding='utf-8')
p=ROOT/'字典与主库_20261028/建设说明与当前进度.md';s=p.read_text(encoding='utf-8')
s=s.replace('# BMJD职能字典与主库建设说明','# BMJD职能字典与主库建设说明\n\n> 2026-10-28 GM001修正：当前HTML及JSON为3,166岗、7,703条已收录来源、11,546条待匹配来源；GM001已收录。下述首版及既有Excel保留作为历史快照。详情见《GM001与收录门槛复核说明.md》。',1)
p.write_text(s,encoding='utf-8')

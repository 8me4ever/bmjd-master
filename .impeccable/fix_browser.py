from pathlib import Path
p=Path('BMJD主库浏览器/app.js')
s=p.read_text(encoding='utf-8')
def rep(old,new):
 global s
 assert old in s,old[:100]
 s=s.replace(old,new,1)
rep("function go(view,opts={}){closeDrawer();", "function go(view,opts={}){clearTimeout(filterTimer);closeDrawer();if(view==='overview'||view==='notes')state.domain='';")
rep("function render(){ $('#navItems')", "function render(){ clearTimeout(filterTimer);$('#navItems')")
rep("function renderResults(){let items", "function renderResults(){if(!$('#results'))return;let items")
rep("if(meaningful)notes[key]={key,title,status,proposedCode:proposed,note:text,updatedAt:new Date().toISOString(),dataVersion:D.version};else delete notes[key];persistNotes();", "const previous=notes[key];if(meaningful){if(!previous||previous.status!==status||previous.proposedCode!==proposed||previous.note!==text)notes[key]={key,title,status,proposedCode:proposed,note:text,updatedAt:new Date().toISOString(),dataVersion:D.version};}else delete notes[key];persistNotes();")
rep("${meta}</header><div class=\"drawer-body\">${body}</div>", "${meta}${body.includes('id=\"reviewForm\"')?'<button class=\"btn text\" data-action=\"review-jump\" style=\"margin-left:8px\">记录意见</button>':''}</header><div class=\"drawer-body\">${body}</div>")
rep("document.body.style.overflow='hidden';$('.drawer .close').focus();", "document.body.style.overflow='hidden';$('.workspace').inert=true;$('.drawer .close').focus();")
rep("document.body.style.overflow='';drawerEntity=null;", "document.body.style.overflow='';$('.workspace').inert=false;drawerEntity=null;")
rep("case'help':help();break;", "case'review-jump':$('#reviewForm').scrollIntoView({block:'start'});$('#reviewText').focus({preventScroll:true});break;case'help':help();break;")
rep("function ladder(prefix,current){", "function ladder(prefix,current,showPending=false){")
rep("const byLevel=new Map((masterByPrefix.get(prefix)||[]).map(m=>[m[7],m]));return", "const byLevel=new Map((masterByPrefix.get(prefix)||[]).map(m=>[m[7],m]));const pendingLevels=new Map();if(showPending)(sourceByPrefix.get(prefix)||[]).forEach(i=>{const r=D.source_index[i];if(r[7]==='待匹配'){const level=Number(r[3].slice(-1));if(!pendingLevels.has(level))pendingLevels.set(level,[]);pendingLevels.get(level).push(r);}});return")
rep("`:<div class=", "`:<div class=") if False else None
rep("`<div class=\"level-slot\"><b>${l} 级</b><span>未收录</span></div>`;", "pendingLevels.has(l)?`<div class=\"level-slot pending-level\" title=\"${esc([...new Set(pendingLevels.get(l).map(r=>r[4]))].join('；'))}\"><b>${l} 级</b><span>待匹配</span><span>${pendingLevels.get(l).length} 条来源</span></div>`:`<div class=\"level-slot\"><b>${l} 级</b><span>未收录</span></div>`;")
rep("仅显示已收录岗位。空位不代表需要补设岗位，高层级是否适用由职责决定。", "${showPending?'蓝色为已收录岗位；琥珀色为此层级的待匹配来源，尚未合并为标准岗。':'仅显示已收录岗位。'}空位不代表需要补设岗位，高层级是否适用由职责决定。")
rep("h+=ladder(prefix,'')+reviewForm", "h+=ladder(prefix,'',true)+reviewForm")
p.write_text(s,encoding='utf-8')
css=Path('BMJD主库浏览器/style.css')
css.write_text(css.read_text(encoding='utf-8')+'\n.level-slot.pending-level{background:var(--amber-soft);color:var(--amber);border-color:#ead4ac}\n',encoding='utf-8')

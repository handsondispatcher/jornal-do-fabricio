import csv, datetime as dt, html, io, json, re, shutil
from pathlib import Path
import engine
BASE=Path(__file__).parent

def e(s): return html.escape(str(s or ''),quote=True)

def main():
    data=engine.report(); arts=data['articles'][:500]; src=(BASE/'app_original.txt').read_text(encoding='utf-8')
    css=src.split('<style>',1)[1].split('</style>',1)[0].replace('{{','{').replace('}}','}')
    # Keep only original source typography and layout; no backend actions exposed.
    css+='''\n.story{min-height:145px}.story-thumb{display:block}.filters{grid-template-columns:1.4fr 1fr 1fr}.filters button{display:none}.live-note{font-size:11px;color:#65758a;margin-top:9px}.story[hidden]{display:none!important}.pagination button{background:#eef3f8;color:#214767;margin:0 3px}.pagination button:disabled{opacity:.35}.story-foot{clear:none}.story-top{margin-bottom:3px}@media(max-width:560px){.filters{grid-template-columns:1fr}.story-thumb{float:none;width:100%;height:175px;margin:0 0 12px}}'''
    thumbs=BASE/'thumbnails'; count=0
    cards=[]
    for i,a in enumerate(arts,1):
        image=a.get('image_url','') or ''
        if image.startswith('/thumb/'):
            fn=Path(image).name
            if (thumbs/fn).is_file():image='thumbnails/'+fn;count+=1
            else:image=''
        if image and not image.startswith('https://') and not image.startswith('thumbnails/'):image=''
        img=f'<img class="story-thumb" src="{e(image)}" loading="lazy" alt="Fotografia publicada pela fonte" onerror="this.remove()">' if image else ''
        tags=''.join('<span class="tag">'+e(x.title())+'</span>' for x in a['sectors'])
        summary=e(a['summary'][:330]) or 'Consulte a matéria na fonte original.'
        cards.append(f'<article class="story" data-sector="{e("|".join(a["sectors"]))}" data-day="{e(a["published"][:10])}" data-text="{e((a["title"]+" "+a["summary"]+" "+a["source"]).casefold())}">{img}<div class="story-top"><span class="story-index">{i:02d}</span><div class="tags">{tags}</div></div><h3><a href="{e(a["url"])}" target="_blank" rel="noopener noreferrer">{e(a["title"])}</a></h3><p class="abstract">{summary}</p><div class="story-foot"><span><b>{e(a["source"])}</b> · {e(a["published"][:16].replace("T"," "))} UTC</span><a href="{e(a["url"])}" target="_blank" rel="noopener noreferrer">Abrir fonte ↗</a></div></article>')
    sectors=''.join(f'<option value="{e(s)}">{e(s.title())}</option>' for s in sorted(engine.SECTORS))
    today=data['date']; yesterday=(dt.date.fromisoformat(today)-dt.timedelta(days=1)).isoformat()
    last=data['last_run']; status=f'{last["success"]} canais responderam · {last["fail"]} falharam' if last else 'Ainda não houve coleta bem-sucedida.'
    page=f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Jornal do Fabricio — informações do Brasil"><title>Jornal do Fabricio | Informações do Brasil</title><style>{css}</style></head><body><header class="top"><div class="topline"><div class="brand">JORNAL DO FABRICIO <span class="brand-sub">/ INFORMAÇÕES DO BRASIL</span></div><div class="micro">Edição Exclusiva · Brasil · {dt.date.fromisoformat(today):%d/%m/%Y}</div></div><div class="hero"><div class="gold"></div><h1>O essencial. Com profundidade.</h1></div></header><main class="shell"><div class="workspace"><section class="panel"><div class="filters"><input id="search" placeholder="Pesquisar manchetes ou fontes" aria-label="Pesquisar"><select id="sector" aria-label="Editoria"><option value="">Todas as editorias</option>{sectors}</select><select id="day" aria-label="Período"><option value="">Hoje e ontem</option><option value="{today}">Hoje</option><option value="{yesterday}">Ontem</option></select></div><div class="live-note">Edição atualizada automaticamente pelo servidor de publicação. Esta página verifica novas versões a cada minuto.</div></section><div id="stories">{''.join(cards) or '<div class="empty">Nenhuma notícia coletada ainda. Aguarde a primeira atualização automática.</div>'}</div><div class="pagination"><span id="counter"></span><div><button id="prev" type="button">← Anterior</button><button id="next" type="button">Próxima →</button></div></div></div><footer class="technical-footer"><div class="footer-inner"><div class="footer-brand"><span>JORNAL DO FABRICIO</span><small>INFORMAÇÕES DO BRASIL · EDIÇÃO EXCLUSIVA · {dt.date.fromisoformat(today):%d/%m/%Y}</small></div><div class="footer-links"><details><summary>Exportação e impressão</summary><p><a class="footer-tool" href="noticias.csv">Exportar CSV ↗</a> &nbsp; <button class="footer-print" onclick="window.print()">Imprimir / Salvar PDF</button></p></details><details><summary>Estado da atualização e avisos técnicos</summary><p>{e(status)} · Rascunho automatizado não certificado</p><p>Última geração: {e(dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes'))} UTC</p></details><details><summary>Critérios e limitações</summary><p>Feeds RSS e agregadores; títulos e datas dependem das fontes. Seleção exploratória, sem certificação editorial. As imagens só aparecem quando publicamente disponíveis. A execução agendada pode atrasar ou falhar. Links levam à publicação original.</p></details></div><div class="footer-bottom">© Jornal do Fabricio · Publicação pública · Informações sujeitas à verificação nas fontes originais.</div></div></footer></main><script>
const cards=[...document.querySelectorAll('.story')],search=document.querySelector('#search'),sector=document.querySelector('#sector'),day=document.querySelector('#day');let page=0,matching=[];
function render(reset=true){{if(reset)page=0;let term=search.value.trim().toLocaleLowerCase('pt-BR');matching=cards.filter(x=>(!term||x.dataset.text.includes(term))&&(!sector.value||x.dataset.sector.split('|').includes(sector.value))&&(!day.value||x.dataset.day===day.value));let total=Math.max(1,Math.ceil(matching.length/30));page=Math.max(0,Math.min(page,total-1));cards.forEach(x=>x.hidden=true);matching.slice(page*30,(page+1)*30).forEach(x=>x.hidden=false);document.querySelector('#counter').textContent=`Página ${{page+1}} de ${{total}} · ${{matching.length}} notícias`;document.querySelector('#prev').disabled=page===0;document.querySelector('#next').disabled=page>=total-1;}}
[search,sector,day].forEach(x=>x.addEventListener(x===search?'input':'change',()=>render()));document.querySelector('#prev').onclick=()=>{{page--;render(false);window.scrollTo(0,180)}};document.querySelector('#next').onclick=()=>{{page++;render(false);window.scrollTo(0,180)}};render();
let version='';async function check(){{try{{let r=await fetch('version.json?ts='+Date.now(),{{cache:'no-store'}});if(!r.ok)return;let v=(await r.json()).version;if(version&&v!==version)location.reload();version=v;}}catch(e){{}}}}check();setInterval(check,60000);
</script></body></html>'''
    (BASE/'index.html').write_text(page,encoding='utf-8')
    (BASE/'version.json').write_text(json.dumps({'version':dt.datetime.now(dt.timezone.utc).isoformat()}))
    with (BASE/'noticias.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['Título','Fonte','Data UTC','Editorias','Link']);w.writerows([a['title'],a['source'],a['published'],', '.join(a['sectors']),a['url']] for a in arts)
    print('Site gerado:',len(arts),'notícias,',count,'imagens locais,',len(page),'caracteres')
if __name__=='__main__':main()

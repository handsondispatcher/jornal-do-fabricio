"""Seleção editorial de fontes alternativas para o Jornal do Fabricio.

Não equivale a checagem factual. Prefere um artigo original, com metadados
acessíveis, a links de intermediários que não podem ser traduzidos.
Não contorna paywalls, não fabrica tradução e não declara que um proxy funcionou
sem testá-lo. Referências permanecem atribuídas à fonte escolhida.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import email.utils
import html
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import sqlite3
import time
import unicodedata
import urllib.parse as up
import urllib.request as ur
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE_FILE = BASE / 'traducoes.json'
CACHE_NAMESPACE = '__fontes_alternativas_v413__'
STOP = set('''a o os as um uma uns umas ao aos do da dos das de e em no na nos nas por para com sem sobre que se seu sua seus suas foi eram ser sendo tem teve ter vai pode sao esta este esta essa esse aqui assim ate apos entre pelo pela mas ou mais menos vida mundo noticias noticia noticiais jornal noticia hoje ontem ultimas novo nova atualizada atualizacao direto ao vivo
and the or of to for as with in on at about said says says that from after before into is are was were has have had its this those these amid over how why what who where than will can a an to by news latest breaking world report article updated live update told according editorial headlines report reports say claim claims amid latest now after year last new
'''.split())
SYNONYMS = {
    'yemen':'iemen','yemeni':'iemen','houthi':'houthi','houthis':'houthi',
    'riyadh':'riade','saudi':'saudita','saudis':'saudita',
    'airport':'aeroporto','airports':'aeroporto','struck':'atingiu','hit':'atingiu',
    'missile':'missil','missiles':'missil','misseis':'missil','misseis':'missil','balisticos':'balistico','ballistic':'balistico','atingido':'atingiu',
    'ukraine':'ucrania','russian':'russia','russia':'russia',
    'france':'franca','french':'franca','india':'india','indian':'india',
    'sudan':'sudao','sudanese':'sudao','war':'guerra','wars':'guerra',
    'school':'escola','schools':'escola','student':'estudante','students':'estudante',
    'protests':'protesto','protest':'protesto','budget':'orcamento',
    'nobel':'nobel','peace':'paz','prize':'premio','eight':'8','oito':'8',
    'usa':'eua','us':'eua','american':'eua',
    'trumps':'trump','trump':'trump','palestinian':'palestina',
}


def normalized(text):
    text=unicodedata.normalize('NFKD',str(text or '').casefold())
    return ''.join(c for c in text if not unicodedata.combining(c))


def tokens(text):
    text=normalized(re.sub(r'\s*\|\s*(noticias do mundo|world news|breaking news).*$', '', text or '',flags=re.I))
    arr=re.findall(r'[a-z0-9]+',text)
    return frozenset(SYNONYMS.get(t,t) for t in arr if (len(t)>2 or t.isdigit()) and t not in STOP)


def similar(left, right):
    a=tokens(left); b=tokens(right)
    if not a or not b:return False
    common=a&b
    if len(common)<3:return False
    # Números frequentemente distinguem acontecimentos concorrentes.
    na={x for x in a if x.isdigit()};nb={x for x in b if x.isdigit()}
    if na and nb and not (na&nb):return False
    coverage=len(common)/max(1,min(len(a),len(b)))
    jaccard=len(common)/max(1,len(a|b))
    return (len(common)>=4 and (coverage>=.65 or jaccard>=.49)) or (len(common)>=3 and coverage>=.82 and jaccard>=.38)


def is_google_news(url):
    host=(up.urlsplit(url or '').hostname or '').lower()
    return host in {'news.google.com','www.news.google.com'}


def candidate_direct(url):
    p=up.urlsplit(url or '')
    host=(p.hostname or '').lower()
    return p.scheme=='https' and bool(host) and not is_google_news(url) and not host.endswith(('.translate.goog','.google.com','.googleusercontent.com')) and not host.endswith(('.local','.internal')) and host not in ('localhost','127.0.0.1') and bool(p.path and p.path!='/') and not p.username and not p.password


def safe_external(url):
    p=up.urlsplit(url or '')
    if not candidate_direct(url) or p.port not in (None,443) or len(url)>2500:return False
    try:
        infos=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        return bool(infos) and all(ipaddress.ip_address(x[4][0]).is_global for x in infos)
    except (OSError,ValueError):return False


class SafeRedirect(ur.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_external(newurl):raise ValueError('Redirecionamento não permitido')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class Meta(HTMLParser):
    def __init__(self):
        super().__init__();self.title='';self.description='';self.canonical='';self.language='';self.in_title=False;self.image=''
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='html':self.language=d.get('lang','')
        if tag=='title':self.in_title=True
        if tag=='link' and 'canonical' in d.get('rel','').lower():self.canonical=d.get('href','')
        if tag=='meta':
            k=(d.get('property') or d.get('name') or '').lower();v=html.unescape(d.get('content','')).strip()
            if k in ('og:description','twitter:description','description') and len(v)>len(self.description):self.description=v[:700]
            if k in ('og:image','twitter:image') and not self.image:self.image=v
            if k=='og:locale' and not self.language:self.language=v
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title+=data


def probe_publisher(url, timeout=5):
    """Confirma acesso à página HTML pública, não confirma tradução por terceiros."""
    if not safe_external(url):return None
    try:
        handler=ur.build_opener(SafeRedirect)
        req=ur.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; JornalDoFabricio/4.13; editorial-link-check)','Accept':'text/html'})
        with handler.open(req,timeout=timeout) as resp:
            final=resp.geturl()
            if not safe_external(final) or 'html' not in resp.headers.get('Content-Type','').lower():return None
            raw=resp.read(150_000).decode('utf-8','replace')
        parser=Meta();parser.feed(raw)
        if re.search(r'404 not found|page not found|access denied|captcha required',parser.title,re.I):return None
        # Um HTML genérico sem metadados pode indicar bloqueio ou landing page.
        if not (parser.title.strip() or parser.description):return None
        real=up.urljoin(final,parser.canonical) if parser.canonical else final
        if not candidate_direct(real) or (up.urlsplit(real).hostname!=up.urlsplit(final).hostname):real=final
        return {'url':real,'description':parser.description,'image_url':up.urljoin(real,parser.image) if parser.image else '', 'language':parser.language, 'title':parser.title[:250]}
    except Exception:return None



def probe_translation(url, timeout=5):
    """Best-effort confirmation that a translated HTML page is obtainable.

    A 200 response alone is NOT sufficient; the proxy may show an empty shell.
    """
    if not safe_external(url):return False
    gateway='https://translate.google.com/translate?'+up.urlencode({'sl':'auto','tl':'pt-BR','u':url})
    class TranslateRedirect(ur.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            p=up.urlsplit(newurl);h=(p.hostname or '').lower()
            permitted=h=='translate.google.com' or h.endswith('.translate.goog')
            if p.scheme!='https' or not permitted or p.port not in (None,443):
                raise ValueError('Destino do tradutor inesperado')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    try:
        req=ur.Request(gateway,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
        with ur.build_opener(TranslateRedirect).open(req,timeout=timeout) as resp:
            if 'html' not in resp.headers.get('Content-Type','').lower():return False
            raw=resp.read(80_000).decode('utf-8','replace')
            final=(up.urlsplit(resp.geturl()).hostname or '').lower()
        if len(raw)<1800 or not final.endswith('.translate.goog'):return False
        # Uma página intermediária vazia não é tradução confirmada.
        lang=bool(re.search(r'<html[^>]+lang=["\']pt(?:-BR)?["\']',raw,re.I))
        translated_words=len(re.findall(r'\b(?:para|com|que|uma|das|dos|pelo|pela|não|está|sobre|após|também)\b',raw,re.I))
        return lang and translated_words>=5
    except Exception:return False

def reading_score(c, verified=False, translated=False):
    url=c.get('url') or ''
    score=0
    if candidate_direct(url): score+=80
    if verified:score+=35
    # Artigo já publicado em português recebe prioridade sobre proxy de tradução.
    url_lower=url.lower()
    if re.search(r'/portuguese/|/pt-br/|/brasil/',url_lower) or (up.urlsplit(url).hostname or '').endswith('.br'):score+=90
    if translated:score+=70
    if c.get('image_url'):score+=7
    if len(str(c.get('summary') or ''))>110:score+=9
    if len(str(c.get('summary') or ''))>220:score+=3
    if c.get('source') and 'tema:' not in c.get('source','').lower():score+=3
    if is_google_news(url):score-=85
    if re.search(r'(subscribe|paywall|premium)',url,re.I):score-=15
    if re.search(r'/rss/|/search[/?]',url,re.I):score-=15
    return score


def _as_utc(date):
    try:
        return dt.datetime.fromisoformat(date).astimezone(dt.timezone.utc)
    except (TypeError,ValueError):return None


def db_candidates(db_path):
    if not Path(db_path).is_file():return []
    try:
        db=sqlite3.connect(f'file:{up.quote(str(db_path))}?mode=ro',uri=True)
        try:rows=db.execute('SELECT title,url,source,published,summary,image_url FROM articles').fetchall()
        finally:db.close()
    except (sqlite3.Error,OSError):return []
    return [dict(zip(('title','url','source','published','summary','image_url'),r)) for r in rows]


def matching_db_entries(articles, rows, limit_per_story=10):
    """Busca coberturas equivalentes do mesmo acontecimento na coleta atual."""
    lookup=defaultdict(list)
    recent=[]
    for row in rows:
        tok=tokens(row['title'])
        if len(tok)<3:continue
        i=len(recent);recent.append((row,tok))
        for t in tok:lookup[t].append(i)
    result={}
    for article in articles:
        key=article['url'];tok=tokens(article['title'])
        if len(tok)<3:continue
        ids=Counter(i for t in tok for i in lookup.get(t,[]))
        possible=[];used=set()
        base_date=_as_utc(article.get('published'))
        for i,count in ids.most_common(150):
            if count<3:break
            r,other=recent[i]
            if r['url']==key or r['url'] in used:continue
            alternate_date=_as_utc(r.get('published'))
            if base_date and alternate_date and abs((base_date-alternate_date).total_seconds())>60*60*36:continue
            if not similar(article['title'],r['title']):continue
            used.add(r['url']);possible.append(r)
            if len(possible)>=limit_per_story:break
        if possible:result[key]=possible
    return result


def lookup_bing_rss(title, limit=10, timeout=7):
    """Descoberta complementar. Não considera agregador como fonte final."""
    q=' '.join(w for w in re.findall(r'[\wÀ-ÿ]+', title) if normalized(w) not in STOP)[:140]
    if not q:return []
    url='https://www.bing.com/news/search?'+up.urlencode({'q':q,'format':'rss','setlang':'pt-BR'})
    try:
        req=ur.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/rss+xml,text/xml,*/*'})
        with ur.urlopen(req,timeout=timeout) as resp:data=resp.read(400_000)
        root=ET.fromstring(data)
    except Exception:return []
    results=[]
    for item in root.findall('./channel/item')[:limit]:
        headline=re.sub('<[^>]+>',' ',html.unescape(item.findtext('title') or '')).strip()
        raw=(item.findtext('link') or '').strip()
        parsed=up.urlsplit(raw)
        if (parsed.hostname or '').endswith('bing.com'):
            params=up.parse_qs(parsed.query)
            direct=next((v[0] for k,v in params.items() if k in ('url','u','r') and v and v[0].startswith('https://')),None)
            raw=direct or ''
        if not candidate_direct(raw) or not similar(title,headline):continue
        source_el=item.find('source')
        source=(source_el.text or '').strip() if source_el is not None else up.urlsplit(raw).hostname
        results.append({'title':headline,'url':raw,'source':source,'summary':'','image_url':'','published':''})
    return results



def collapse_equivalent_stories(articles):
    """Uma cobertura principal por acontecimento, sem misturar eventos parecidos."""
    result=[]
    for story in articles:
        index=None
        for i,kept in enumerate(result):
            if not similar(story.get('title',''),kept.get('title','')):continue
            one=_as_utc(story.get('published'));two=_as_utc(kept.get('published'))
            if one and two and abs((one-two).total_seconds())>36*3600:continue
            index=i;break
        if index is None:
            result.append(story);continue
        previous=result[index]
        rank=lambda a:reading_score(a,bool(a.get('source_checked')),bool(a.get('translation_verified')))
        preferred,secondary=(story,previous) if rank(story)>rank(previous) else (previous,story)
        # Preserva links para as demais coberturas, com uma opção por veículo.
        collected=list(preferred.get('other_sources',[]))+list(secondary.get('other_sources',[]))
        if candidate_direct(secondary.get('url','')):
            collected.insert(0,{'name':secondary.get('source') or 'Outra fonte','url':secondary['url']})
        more=[];known_hosts={(up.urlsplit(preferred.get('url','')).hostname or '').lower().removeprefix('www.')}
        for entry in collected:
            url=entry.get('url','');host=(up.urlsplit(url).hostname or '').lower().removeprefix('www.')
            if not candidate_direct(url) or not host or host in known_hosts:continue
            known_hosts.add(host);more.append(entry)
            if len(more)>=4:break
        preferred['other_sources']=more
        preferred['source_options_count']=max(preferred.get('source_options_count',1),secondary.get('source_options_count',1))
        result[index]=preferred
    return result

def choose_sources(articles, db_path=None, discover_limit=14, probe_limit=45, now=None):
    """Encontra equivalentes, verifica URLs diretas e escolhe uma origem com leitura viável.

    Nunca altera a notícia se não há indício forte de que a alternativa é o mesmo evento.
    """
    db_path=db_path or BASE/'news.db'
    candidates=matching_db_entries(articles,db_candidates(db_path))
    try:root=json.loads(CACHE_FILE.read_text(encoding='utf-8'))
    except (OSError,ValueError):root={}
    if not isinstance(root,dict):root={}
    cache=root.get(CACHE_NAMESPACE,{})
    if not isinstance(cache,dict):cache={}
    current=int(now if now is not None else time.time())
    # Complementar buscas somente onde a coleta não trouxe uma fonte diretamente acessível.
    needs=[]
    for a in articles:
        if not any(s in a.get('sectors',[]) for s in ('internacional','guerra','americas','europa','asia','oriente_medio','oceania','africa','antartida')):continue
        options=[a]+candidates.get(a['url'],[])
        if sum(candidate_direct(o.get('url','')) for o in options)>=3:continue
        needs.append(a)
    needs=needs[:discover_limit]
    def discover(a):
        key=a['title']
        saved=cache.get(key)
        if saved and current-int(saved.get('checked_at',0))<6*3600:return key,saved.get('items',[])
        found=lookup_bing_rss(key)
        return key,found
    if needs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for key,results in pool.map(discover,needs):
                cache[key]={'checked_at':current,'items':results[:8]}
    # Faça preflight de links prioritários. Falha da rede não apaga opções locais.
    verify=[]
    for a in articles[:min(100,len(articles))]:
        opts=[a]+candidates.get(a['url'],[])+cache.get(a['title'],{}).get('items',[])
        for x in sorted(opts,key=reading_score,reverse=True)[:3]:
            url=x.get('url','')
            if candidate_direct(url) and url not in verify:verify.append(url)
            if len(verify)>=probe_limit:break
        if len(verify)>=probe_limit:break
    checks={}
    if verify:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            for url,meta in zip(verify,pool.map(probe_publisher,verify)):checks[url]=meta
    translate_targets=[u for u in verify if checks.get(u)][:24]
    can_translate={}
    if translate_targets:
        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
            for url,ok in zip(translate_targets,pool.map(probe_translation,translate_targets)):can_translate[url]=ok
    output=[];chosen_count=0;options_count=0
    for a in articles:
        a=dict(a)
        alternates=candidates.get(a['url'],[])+cache.get(a['title'],{}).get('items',[])
        # Dedup URL; uma única origem não conta como validação independente.
        unique=[];seen=set()
        for entry in [a]+alternates:
            url=entry.get('url','')
            if url and url not in seen and (entry is a or similar(a['title'],entry.get('title',''))):
                seen.add(url);unique.append(entry)
        options_count+=max(0,len(unique)-1)
        ordered=sorted(unique,key=lambda c:(reading_score(c, bool(checks.get(c.get('url',''))), can_translate.get(c.get('url',''),False)), bool(c.get('image_url'))),reverse=True)
        chosen=ordered[0] if ordered else a
        original_url=a.get('url','')
        url=chosen.get('url','')
        if url!=original_url and candidate_direct(url):
            chosen_count+=1
            a['url']=url
            a['title']=chosen.get('title') or a['title']
            a['summary']=chosen.get('summary') or ''
            a['image_url']=chosen.get('image_url') or ''
            if _as_utc(chosen.get('published')):a['published']=chosen['published']
            a['publisher_url']=checks.get(url,{}).get('url',url) if checks.get(url) else url
            a['source']=chosen.get('source') or a.get('source')
            if chosen.get('summary') and len(chosen.get('summary',''))>len(a.get('summary','')):a['summary']=chosen['summary']
            if chosen.get('image_url'):a['image_url']=chosen['image_url']
        elif candidate_direct(original_url):
            a['publisher_url']=checks.get(original_url,{}).get('url',original_url) if checks.get(original_url) else original_url
        meta=checks.get(url)
        if meta:
            if meta.get('description') and len(meta['description'])>len(a.get('summary','')):a['summary']=meta['description']
            if meta.get('image_url') and not a.get('image_url'):a['image_url']=meta['image_url']
            a['source_checked']=True
        a['translation_verified']=bool(can_translate.get(url))
        # Não atribua a uma fonte o conteúdo de outra se não for o mesmo evento.
        other=[];hosts={(up.urlsplit(a.get('url','')).hostname or '').lower()}
        for x in ordered:
            other_url=x.get('url','');host=(up.urlsplit(other_url).hostname or '').lower().removeprefix('www.')
            if not candidate_direct(other_url) or other_url==a.get('url') or host in hosts:continue
            other.append({'name':x.get('source') or host,'url':other_url});hosts.add(host)
            if len(other)>=4:break
        a['other_sources']=other
        a['source_options_count']=len(unique)
        output.append(a)
    # Traducao e descoberta partilham um arquivo JÁ incluído no workflow existente.
    # Preserve todas as traduções e não exija edição da pasta oculta .github.
    cache={k:v for k,v in cache.items() if current-int(v.get('checked_at',0))<12*3600}
    root[CACHE_NAMESPACE]=cache
    try:CACHE_FILE.write_text(json.dumps(root,ensure_ascii=False,indent=1),encoding='utf-8')
    except OSError:pass
    output=collapse_equivalent_stories(output)
    print(f'Seleção de fontes: {chosen_count} alternativas escolhidas; {options_count} opções examinadas; {len(verify)} links pré-verificados; {sum(can_translate.values())} traduções confirmadas; {len(needs)} buscas complementares')
    return output

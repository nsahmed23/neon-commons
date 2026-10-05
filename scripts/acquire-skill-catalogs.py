#!/usr/bin/env python3
"""Acquire inert, pinned catalog instructions. Never install or execute catalog code.
All results are acquisition/triage evidence, not completed semantic review.
"""
import argparse, concurrent.futures, datetime, hashlib, json, pathlib, re, urllib.request
from urllib.parse import quote
REPOS = ['cloudposse/atmos','microsoft/azure-skills','microsoft/skills','MicrosoftDocs/Agent-Skills','microsoft/mggraph-intune-samples','hashicorp/agent-skills','antonbabenko/terraform-skill','cloudflare/security-audit-skill','cloudflare/skills','vercel/vercel-plugin','vercel-labs/agent-skills','vercel-labs/skills','GoogleCloudPlatform/knowledge-catalog','microsoft/Ontology-Playground','Contrastive-LM/CLM','powerstacks-corp/intune-advanced-troubleshooting','TheLobbi/Claude-m','saurabhkumar8112/cyclomatic-complexity-skill','mukul975/Anthropic-Cybersecurity-Skills','DietrichGebert/ponytail','dmmulroy/anti-slop']
MAX_FILE=2*1024*1024

def repository_selector(value):
    # An acquisition selector is data, never a filesystem path or URL. Admit
    # the bounded ASCII owner/repository subset used by the pinned catalog.
    if (type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', value)
            or value.split('/')[1] in {'.', '..'}):
        raise ValueError('Repository selector must be a bounded owner/repository name.')
    return value

def get(url,limit=MAX_FILE):
    req=urllib.request.Request(url,headers={'User-Agent':'Intune-Catalog-Acquisition/1','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=45) as r:
        data=r.read(limit+1)
    if len(data)>limit: raise ValueError('response_limit')
    return data

def safe(path):
    p=pathlib.PurePosixPath(path)
    return not p.is_absolute() and all(x not in ('..','.') for x in p.parts) and '\\' not in path

def acquire(repo,out):
    repo=repository_selector(repo)
    result={'repository':repo,'status':'BLOCKED','skills':[], 'files':[], 'limitations':[]}
    base=out/repo.replace('/','__');base.mkdir(parents=True,exist_ok=True)
    try:
        commit=json.loads(get('https://api.github.com/repos/'+repo+'/commits/HEAD'))['sha']
        result['commit']=commit
        tree_raw=get('https://api.github.com/repos/'+repo+'/git/trees/'+commit+'?recursive=1',24*1024*1024)
        tree=json.loads(tree_raw);(base/'tree.json').write_bytes(tree_raw)
        result['tree_sha256']=hashlib.sha256(tree_raw).hexdigest()
        result['truncated']=tree.get('truncated',True)
        rows=[x for x in tree.get('tree',[]) if x.get('type')=='blob' and safe(x['path'])]
        skills=[x for x in rows if pathlib.PurePosixPath(x['path']).name.lower()=='skill.md']
        result['discovered_skills']=len(skills)
        licenses=[x for x in rows if '/' not in x['path'] and x['path'].lower().startswith(('license','copying'))]
        selected={x['path']:x for x in skills+licenses}
        # Relevant skills' complete immediate instruction bundles are retained for on-demand review.
        for skill in skills:
            name=skill['path'].lower()
            if repo in ('cloudposse/atmos','hashicorp/agent-skills','antonbabenko/terraform-skill','MicrosoftDocs/Agent-Skills','cloudflare/security-audit-skill') or any(t in name for t in ('azure','identity','security','terraform','powershell','storage','intune','mcp','vercel-sandbox','env-vars','deployments-cicd','verification')):
                parent=str(pathlib.PurePosixPath(skill['path']).parent)
                if parent != '.':
                    for row in rows:
                        if row['path'].startswith(parent+'/') and row.get('size',MAX_FILE+1)<=MAX_FILE: selected[row['path']]=row
        result['license_paths']=[x['path'] for x in licenses]
        def fetch(row):
            url='https://raw.githubusercontent.com/'+repo+'/'+commit+'/'+quote(row['path'],safe='/')
            record={'path':row['path'],'source_url':url,'git_blob_sha':row['sha']}
            try:
                data=get(url);target=base/'raw'/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                record.update(status='PASS',sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
            except Exception as e: record.update(status='BLOCKED',error=type(e).__name__+': '+str(e)[:200])
            return record
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            result['files']=list(pool.map(fetch,selected.values()))
        bypath={r['path']:r for r in result['files']}
        for row in skills:
            r=bypath[row['path']]
            result['skills'].append({'path':row['path'],'sha256':r.get('sha256'),'acquisition':r['status'],'disposition':'defer','rationale':'Acquired for task-stage review; compatibility, permissions and companion completeness require explicit semantic review before adoption.','license':'see repository license; nested exceptions not yet reviewed','supported_versions':'unverified','dependencies':'unverified','permissions':'unverified; no authority granted','side_effects':'unverified; not installed or executed','readiness_consequence':'Not an adopted runtime capability.'})
        result['status']='PASS' if not result['truncated'] and all(r['status']=='PASS' for r in result['files']) else 'INCONCLUSIVE'
        result['limitations'].append('Discovery covers SKILL.md named entries in this pinned tree; other instruction conventions not enumerated. Acquisition does not establish semantic review or license compatibility.')
    except Exception as e: result['error']=type(e).__name__+': '+str(e)[:200]
    (base/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--repos',nargs='*',type=repository_selector);a=p.parse_args()
    out=pathlib.Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for repo in a.repos or REPOS:
        result=acquire(repo,out);rows.append(result)
        print(json.dumps({'repository':repo,'status':result['status'],'commit':result.get('commit'),'skills':len(result['skills']),'error':result.get('error')}),flush=True)
        (out/'catalog-summary.json').write_text(json.dumps({'schema':'catalog-acquisition/1','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repositories':rows},indent=2)+'\n')
if __name__=='__main__':main()

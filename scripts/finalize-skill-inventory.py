#!/usr/bin/env python3
"""Build the declared-catalog disposition ledger from pinned acquisition receipts.

Classification is scope triage. It is not a semantic security audit, installer,
or automatic authorization to invoke a discovered skill.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acquisition',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args();source=Path(args.acquisition);out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    reviewed={
        ('cloudposse/atmos','agent-skills/skills/atmos-stacks/SKILL.md'):('adapt','Complete instructions and linked relevant references read; only literal subset measured on Atmos 1.199.0.'),
        ('cloudposse/atmos','agent-skills/skills/atmos-introspection/SKILL.md'):('adapt','Complete instructions and linked relevant references read; native describe comparison, no execution authority.'),
        ('hashicorp/agent-skills','plugins/terraform/skills/run-acceptance-tests/SKILL.md'):('reference','Complete instructions read; service tests require authorized disposable targets and TF_ACC; source tests are not live acceptance.'),
        ('hashicorp/agent-skills','plugins/terraform/skills/provider-test-patterns/SKILL.md'):('reference','Complete instructions and checks reference read; import/state/final-plan assertions considered against actual pinned dependencies.'),
        ('antonbabenko/terraform-skill','skills/terraform-skill/SKILL.md'):('reference','Instructions and state-management excerpts reviewed; full companion closure not established; runtime feature floors must be independently checked.'),
        ('MicrosoftDocs/Agent-Skills','skills/azure-rbac/SKILL.md'):('reference','Documentation routing index inspected; does not establish any role grant, effective authorization or SDK implementation.'),
        ('microsoft/skills','.github/plugins/azure-sdk-python/skills/azure-identity-py/SKILL.md'):('adapt','Complete instructions and capabilities/non-hero references read by identity owner; explicit credential boundary adapted, no SDK/default credential chain installed; see protected-source-ledger.json.'),
        ('microsoft/skills','.github/plugins/azure-sdk-python/skills/azure-storage-blob-py/SKILL.md'):('adapt','Complete instructions and capabilities/non-hero references read by identity owner; fixed conditional read observation only, no storage writes or lease acquisition; see protected-source-ledger.json.'),
    }
    security_path=out.parent/'security/skill-dispositions.csv'
    security={}
    if security_path.exists():
        for row in csv.DictReader(security_path.open()):security[(row['repository'],row.get('path',row.get('skill_path')))]=row
    rows=[];repositories=[];mirrors={}
    for receipt in sorted(source.glob('*/receipt.json')):
        info=json.loads(receipt.read_text());repo=info['repository'];commit=info['commit']
        license_labels=[]
        for path in info.get('license_paths',[]):
            raw=receipt.parent/'raw'/path
            if not raw.is_file():continue
            data=raw.read_text(errors='replace')
            label=next((name for token,name in [('Apache License','Apache-2.0'),('MIT License','MIT'),('Mozilla Public License','MPL-2.0'),('Creative Commons Attribution','CC-BY (inspect exact terms)')] if token in data),'custom/inspect source')
            license_labels.append(path+': '+label)
        repositories.append({k:info.get(k) for k in ('repository','commit','status','discovered_skills','truncated','limitations','license_paths')})
        for skill in info['skills']:
            path=skill['path'];key=(repo,path)
            disposition='defer';rationale='Potentially relevant catalog; individual dependency/permission/compatibility review incomplete.'
            instruction_review='metadata/scope triage only; not adopted'
            if repo in {'cloudflare/skills','TheLobbi/Claude-m','mukul975/Anthropic-Cybersecurity-Skills','DietrichGebert/ponytail','dmmulroy/anti-slop'}:
                disposition='exclude';rationale='No matching product boundary or necessary execution capability in this Intune wizard or read-only Wally evaluation; no installation.'
            if repo=='vercel-labs/agent-skills':
                disposition='defer';rationale='Potential Wally performance-method overlap; actual Wally source unavailable, no product migration or skill substitution justified.'
            if repo=='vercel-labs/skills':
                disposition='reference';rationale='Discovery/provenance reference only; catalog installer not needed or executed.'
            if repo=='cloudposse/atmos' and not path.startswith('agent-skills/'):
                disposition='exclude';rationale='Upstream development/release contributor workflow, outside supported operator execution profile.'
            if repo=='hashicorp/agent-skills' and not any(x in path for x in ('provider','terraform-search-import','terraform-test','terraform-style','refactor-module')):
                disposition='exclude';rationale='Different product/service or unsupported workflow; no platform added to use this skill.'
            if repo in {'MicrosoftDocs/Agent-Skills','microsoft/azure-skills','microsoft/skills'} and not any(x in path.lower() for x in ('identity','storage','rbac','entra','security','auth','governance','diagnos','monitor','microsoft-doc','mcp','agent')):
                disposition='exclude';rationale='Catalog path targets an unrelated service/language/workload; selected Python identity/storage implementations reviewed separately.'
            if key in reviewed:
                disposition,instruction_review=reviewed[key];rationale=instruction_review
            if key in security:
                item=security[key];disposition=item['disposition'];rationale=item.get('rationale',item.get('reason','See security-specific disposition ledger.'));instruction_review=item.get('instruction_review','See security-specific source review record.')
            sha=skill['sha256'];canonical=mirrors.setdefault(sha,repo+'@'+commit+':'+path)
            rows.append({'owner':repo.split('/')[0],'repository':repo,'commit':commit,'skill_path':path,'sha256':sha,
                'license':'; '.join(license_labels) or 'No root license acquired; reuse authorization unresolved',
                'license_scope':'Root license screened; nested exceptions require review before copying into product',
                'supported_versions':'Pinned catalog snapshot; exact installed runtime compatibility unverified unless evidence row states otherwise',
                'dependencies':skill.get('dependencies','unverified'),'required_permissions':'Not granted by reading; per-skill requirements unverified except selected review records',
                'execution_side_effects':'Not installed or executed; catalog may request network/subprocess/cloud mutations',
                'disposition':disposition,'rationale':rationale,'instruction_review':instruction_review,
                'readiness_consequence':'Excluded from declared product profile' if disposition=='exclude' else 'Not a product capability; implementation and exact-version qualification required',
                'canonical_byte_mirror':canonical,'acquisition':skill['acquisition'],
                'source_url':f'https://github.com/{repo}/blob/{commit}/{path}'})
    with (out/'skill-inventory.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary={'schema_version':'catalog-dispositions/1','status':'PASS' if all(r['acquisition']=='PASS' for r in rows) else 'INCONCLUSIVE',
        'repositories':repositories,'discovered_skill_entries':len(rows),'unique_skill_byte_hashes':len(mirrors),
        'dispositions':dict(collections.Counter(r['disposition'] for r in rows)),
        'boundary':'Every discovered SKILL.md in 21 declared pinned repository trees; installed environment inventory separate.',
        'not_established':['Full ecosystem enumeration','Full instruction/reference closure for deferred entries','Security of catalog code','All nested licenses','Compatibility with unqualified runtime versions'],
        'ledger_sha256':hashlib.sha256((out/'skill-inventory.csv').read_bytes()).hexdigest()}
    (out/'catalog-dispositions.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='repositories'},indent=2))


if __name__=='__main__':main()

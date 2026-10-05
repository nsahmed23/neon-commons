"""Explicit v2 field rules for the bounded local projection.

This producer helper is not imported by the independent preservation oracle.
"""
import hashlib

def opaque(pointer):
    return 'f_'+hashlib.sha256(pointer.encode('utf-8')).hexdigest()[:24]

def under(pointer,roots):
    return any(pointer==r or pointer.startswith(r+'/') for r in roots)

def records(bundle,policy_pointer,settings,assignments,retained,sensitive,source_digest):
    from .core import _walk
    out=[]
    for p,v in _walk(bundle):
        disp='service_owned';rule='capture.provenance.v2';dest=[]
        if p==policy_pointer or p.startswith(policy_pointer+'/'):
            rel=p[len(policy_pointer):];top=rel[1:].split('/')[0]
            mapping={'name':'name','description':'description','platforms':'platforms','technologies':'technologies/0','roleScopeTagIds':'role_scope_tag_ids'}
            rule='policy.metadata.v2';dest=['/observed/policy'+rel]
            if top in mapping:
                disp='desired';rule='policy.desired.v2';suffix=rel[len('/'+top):];dest=['/desired/'+mapping[top]+suffix]
            elif top=='id':
                disp='identity';rule='policy.identity.v2';dest=['/object_id','/key']
        for i,(_,sp) in enumerate(settings):
            di=sum(not under(prior,retained|sensitive) for _,prior in settings[:i])
            if p==sp or p.startswith(sp+'/'):
                rel=p[len(sp):];rule='setting.wrapper.v2';disp='service_owned';dest=[f'/observed/settings/{i}'+rel]
                if rel=='/id':disp='identity';rule='setting.identity.v2';dest=[f'/desired/settings/settings/{di}/id']
                elif rel=='/@odata.type':rule='setting.wrapper-type.v2'
                elif rel=='/settingInstance' or rel.startswith('/settingInstance/'):
                    disp='desired';rule='setting.instance.v2';dest=[f'/desired/settings/settings/{di}'+rel]
        for i,(a,ap) in enumerate(assignments):
            di=sum(not under(prior,retained|sensitive) for _,prior in assignments[:i])
            if p==ap or p.startswith(ap+'/'):
                rel=p[len(ap):];disp='service_owned';rule='assignment.metadata.v2';dest=[f'/observed/assignments/{i}'+rel]
                if rel=='/target' or rel.startswith('/target/'):
                    disp='relationship';rule='assignment.target.v2';dest=[f'/desired/assignments/{di}']
                    if rel!='/target':
                        field=rel.removeprefix('/target/')
                        mapped={'@odata.type':'type','groupId':'group_id','deviceAndAppManagementAssignmentFilterType':'filter_type','deviceAndAppManagementAssignmentFilterId':'filter_id'}.get(field)
                        dest=[f'/desired/assignments/{di}/'+mapped] if mapped else []
                        if mapped=='filter_id' and a.get('target',{}).get('deviceAndAppManagementAssignmentFilterType')=='none':dest=[]
        if p=='/references' or p.startswith('/references/'):
            disp='separately_managed';rule='reference.external.v2';dest=[p]
            parts=p.split('/')
            if len(parts)>2 and parts[2].isdigit():
                ri=int(parts[2]);di=sum(not under('/references/'+str(j),retained|sensitive) for j in range(ri))
                dest=['/references/'+str(di)+('/'+'/'.join(parts[3:]) if len(parts)>3 else '')]
        kind=('null' if v is None else 'boolean' if isinstance(v,bool) else 'object' if isinstance(v,dict) else 'array' if isinstance(v,list) else 'number' if isinstance(v,(int,float)) else 'string')
        retained_here=under(p,retained);sensitive_here=under(p,sensitive)
        row={'source_pointer':p,'kind':kind,'disposition':disp,'rule_id':rule,'rule_version':'2.0.0','destination_pointers':dest,'reason':rule,'loss_blocking':False}
        if retained_here or sensitive_here:
            finding=opaque(p);disp='sensitive_local_only' if sensitive_here else 'unsupported';rule='retention.sensitive.v2' if sensitive_here else 'retention.unsupported.v2'
            row.update(source_pointer='opaque:'+finding,disposition=disp,rule_id=rule,destination_pointers=[],reason='Restricted original only',loss_blocking=True,finding_id=finding,retention_locator='restricted-original-source',source_digest_ref=source_digest)
        out.append(row)
    return out

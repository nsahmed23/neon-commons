#!/usr/bin/env python3
"""Execute three pinned provider-free catalog exercises with original graders.

Authored solutions implement public contracts. Static HCP questionnaire answers
are historical exercise inputs, not revalidation of a live HCP service.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
PROFILES={
    'versions':('modules/version-modules',9),
    'permissions':('hcp-terraform/projects-teams',13),
    'policy':('hcp-terraform/policy-as-code',13),
}

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def solve_policy(work,run):
    p=work/'versions.tf';p.write_text(p.read_text().replace('>= 1.11.0','= 1.10.0'))
    p=work/'verdicts.tf';p.write_text(p.read_text().replace('nom => ???', 'nom => (!cas.policy_en_echec || cas.niveau == "advisory" ? "poursuit" : (cas.override_autorise_par_le_policy_set && cas.detient_manage_policy_overrides ? "bloque_surchargeable" : "bloque"))'))
    p=work/'evaluation.tf';p.write_text(p.read_text().replace('nom => ???', 'nom => [for r in plan.resource_changes : r.address if contains(r.change.actions, "create") && r.type == "local_file" && substr(r.change.after.file_permission, length(r.change.after.file_permission)-1, 1) != "0"]'))
    # These documentary values are labeled and scored separately in the receipt.
    p=work/'connaissances.tf';text=p.read_text()
    values=[{'sentinel':['advisory','soft-mandatory','hard-mandatory'],'opa':['advisory','mandatory'],'terraform':['advisory','mandatory overridable','mandatory']}, {'framework_unique':'sentinel','version_maximale':'0.40.x','voit_le_cout':True}, {'policy_sets':1,'policies_par_set':5,'connexion_vcs':False}]
    for key,value in zip(('niveaux_par_framework','policy_checks','free_tier'),values):
        text=text.replace(key+' = ???',key+' = jsondecode('+json.dumps(json.dumps(value))+')')
    p.write_text(text)

def solve_permissions(work,run):
    for p in work.rglob('versions.tf'):p.write_text(p.read_text().replace('>= 1.11.0','= 1.10.0'))
    p=work/'acces/acces.tf';text=p.read_text()
    rule='max(index(local.echelle, local.equivalences[e.organisation]), index(local.echelle, e.projet), index(local.echelle, e.workspace))'
    text=text.replace('value = ???','value = {for name, e in var.equipes : name => local.echelle['+rule+']}',1)
    text=text.replace('value = ???','value = sort([for name, e in var.equipes : name if '+rule+' >= index(local.echelle, "ecriture")])',1);p.write_text(text)
    values={'ce_qui_tranche_entre_deux_niveaux':'le_plus_permissif','qui_peut_declencher_un_plan_vcs':'quiconque_peut_fusionner_dans_la_branche','duree_de_vie_du_jeton_run_task':'dix_minutes','role_entre_lecture_et_ecriture':'plan','role_entre_ecriture_et_admin':'maintenance'}
    (work/'questionnaire/reponses.auto.tfvars').write_text('reponses = jsondecode('+json.dumps(json.dumps(values))+')\n')
    # Function calls are forbidden in tfvars, so emit the equivalent literal map.
    (work/'questionnaire/reponses.auto.tfvars').write_text('reponses = '+json.dumps(values)+'\n')

def solve_versions(work,run):
    repo=work/'modules-src';module=repo/'etiquette'
    def git(*args):return run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false',*args],repo)
    git('init','--template=');git('config','user.name','Synthetic Lab');git('config','user.email','lab@example.invalid')
    def commit(tag):
        git('add','.');git('commit','-m',tag);git('tag','-a',tag,'-m',tag)
        return git('rev-parse','HEAD')['stdout'].strip()
    first=commit('v1.0.0')
    variable=module/'variables.tf';variable.write_text(variable.read_text()+'\nvariable "suffixe" {\n type = string\n default = ""\n}\n')
    for p in module.glob('*.tf'):
        if p.name!='variables.tf':
            p.write_text(p.read_text().replace('etiquette = var.prefixe','etiquette = var.suffixe == "" ? var.prefixe : "${var.prefixe}-${var.suffixe}"').replace('"1.0.0"','"1.1.0"'))
    (repo/'CHANGELOG.md').write_text('## 1.1.0\nOptional suffix; existing input preserved.\n'+(repo/'CHANGELOG.md').read_text())
    commit('v1.1.0')
    for p in module.glob('*.tf'):p.write_text(p.read_text().replace('prefixe','nom_projet').replace('"1.1.0"','"2.0.0"'))
    (repo/'CHANGELOG.md').write_text('## 2.0.0\nRename prefixe to nom_projet.\n'+(repo/'CHANGELOG.md').read_text());commit('v2.0.0')
    for name,ref,args in [('fige',first,'prefixe = "socle"'),('stable','v1.1.0','prefixe = "atelier"\n suffixe = "nord"'),('migre','v2.0.0','nom_projet = "chantier"')]:
        source='git::file://'+repo.as_posix()+'//etiquette?ref='+ref
        (work/name/'main.tf').write_text('module "etiquette" {\n source = '+json.dumps(source)+'\n '+args+'\n}\n')
        for tail in [('init','-input=false','-no-color'),('apply','-auto-approve','-input=false','-no-color')]:run(['terraform',*tail],work/name)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('upstream','tofu','pytest-python','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--profile',choices=PROFILES,required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('locking_lab',ROOT/'scripts/qualify-locking-lab.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    source=Path(a.upstream).resolve(strict=True);tofu=Path(a.tofu).resolve(strict=True)
    if sha(tofu)!=h.TOFU_SHA256:raise ValueError('Tool pin mismatch')
    manifest=json.loads((ROOT/'research/terraform-catalog/source-files.json').read_text());hashes={r['path']:r['sha256'] for r in manifest['files']}
    lab,count=PROFILES[a.profile];lab='labs/'+lab
    paths=['conftest.py',lab+'/challenge/tests/test_functional.py']+[n for n in hashes if n.startswith(lab+'/fixtures/')]
    for n in paths:
        if (source/n).is_symlink() or sha(source/n)!=hashes[n]:raise ValueError('Source mismatch: '+n)
    output=Path(a.output).absolute()
    for protected in (source,ROOT):
        if output.resolve().is_relative_to(protected) or protected.is_relative_to(output.resolve()):raise ValueError('Output overlaps source')
    output=h.new_output(output)
    for n in ('bin','home','tmp','work','upstream'):(output/n).mkdir()
    for n in paths:
        target=output/'upstream'/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((source/n).read_bytes())
    shutil.copytree(source/lab/'fixtures',output/'work',dirs_exist_ok=True)
    binary=output/'bin/tofu';shutil.copyfile(tofu,binary);binary.chmod(0o700)
    if sha(binary)!=h.TOFU_SHA256:raise ValueError('Copied tool differs')
    h.install_wrapper(output,binary)
    (output/'terraform.rc').write_text('disable_checkpoint = true\nprovider_installation { filesystem_mirror { path = "./no-providers" } }\n')
    env=h.clean_environment(output);env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0')
    report={'profile':a.profile,'catalog_commit':manifest['commit'],'evidence_class':'adapted_native_opentofu', 'source_hashes':{n:hashes[n] for n in paths},'harness_sha256':sha(Path(__file__)), 'commands':[], 'dsoxlab_runner_executed':False,'live_service_calls':0,'encrypted_solutions_read':False,'adaptations':['OpenTofu 1.10.0; constraints adapted explicitly where needed','Reviewed original grader; own public-contract solution','No HCP authentication/backend; only local output calculation','Documentary questionnaire values retained as historical exercise data, not current HCP verification']}
    def run(cmd,cwd,required=True):
        r=h.execute(cmd,cwd,env,timeout=90);report['commands'].append({'argv':cmd,'cwd':str(cwd),**r});h.write_json(output/'commands.json',report['commands'])
        if required and r['exit_code']!=0:raise RuntimeError('Command failed: '+str(cmd)+' '+r['stderr'][-1000:])
        return r
    test=output/'upstream'/lab/'challenge/tests/test_functional.py'
    def grade(label):
        r=run([str(Path(a.pytest_python).absolute()),'-m','pytest',str(test),'-q','--junitxml',str(output/(label+'.xml'))],output/'upstream',False)
        h.write_json(output/(label+'.json'),r)
        suite=next(ET.parse(output/(label+'.xml')).getroot().iter('testsuite'))
        return {k:int(suite.attrib[k]) for k in ('tests','errors','failures','skipped')},r['exit_code']
    try:
        report['before'],before=grade('before')
        {'versions':solve_versions,'permissions':solve_permissions,'policy':solve_policy}[a.profile](output/'work',run)
        report['after'],after=grade('after')
        report['success']=before!=0 and after==0 and report['after']=={'tests':count,'errors':0,'failures':0,'skipped':0}
        report['documentary_checks']=3 if a.profile=='policy' else 5 if a.profile=='permissions' else 0
        report['cleanup']='Only output-owned repositories and local state created; retained for replay; no service/process spawned'
    except Exception as exc:report.update(success=False,error=repr(exc))
    h.write_json(output/'receipt.json',report);print(json.dumps({k:v for k,v in report.items() if k in ('success','error','before','after')}))
    return 0 if report['success'] else 1

if __name__=='__main__':raise SystemExit(main())

"""Compare the preserved pre-refactor implementation and current runtime on a finite local corpus."""
import copy, importlib.util, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from intune_iac.graph import query_graph, QUERIES
from intune_iac.io import AppError, digest
root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('intune_iac._graph_before',root/'baseline_graph.py')
before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
graphs=json.loads((root/'graphs.json').read_text())

def outcome(fn, graph):
    try:return {'status':'accepted','digest':digest(fn(graph,'policies'))}
    except AppError as exc:return {'status':'rejected','code':exc.code,'message':exc.message}
    except Exception as exc:return {'status':'unexpected_exception','type':type(exc).__name__}

count=0;mismatches=[]
def check(graph, label):
    global count
    graph['graph_digest']=digest({k:v for k,v in graph.items() if k!='graph_digest'})
    old,new=outcome(before.query_graph,graph),outcome(query_graph,graph)
    count+=1
    if old != new:mismatches.append({'case':label,'before':old,'after':new})

for gi,base in enumerate(graphs):
    representatives={n['type']:n['id'] for n in base['nodes']}
    for index,edge in enumerate(base['edges']):
        for status in ('observed','declared','derived','referenced','unknown'):
            graph=copy.deepcopy(base);graph['edges'][index]['status']=status
            check(graph,f'{gi}:edge:{index}:status:{status}')
        for endpoint in ('source','target'):
            for kind,nid in representatives.items():
                graph=copy.deepcopy(base);graph['edges'][index][endpoint]=nid
                check(graph,f'{gi}:edge:{index}:{endpoint}:{kind}')
        graph=copy.deepcopy(base);del graph['edges'][index]
        check(graph,f'{gi}:edge:{index}:removed')
        graph=copy.deepcopy(base);graph['edges'].append(copy.deepcopy(edge))
        check(graph,f'{gi}:edge:{index}:duplicate')
    for index,node in enumerate(base['nodes']):
        for status in ('observed','declared','referenced','derived','unknown'):
            graph=copy.deepcopy(base);graph['nodes'][index]['status']=status
            check(graph,f'{gi}:node:{index}:status:{status}')
receipt={'schema_version':'graph-refactor-differential/1.0','cases':count,'matches':count-len(mismatches),'mismatches':mismatches,
         'scope':'Rehashed status/domain/range/removal/duplicate-edge mutations of six preserved graph fixtures; compare accepted output or rejection code/message to pre-refactor implementation.',
         'before_source_sha256':__import__('hashlib').sha256((root/'baseline_graph.py').read_bytes()).hexdigest()}
query_cases = 0
query_mismatches = []
for graph_index, graph in enumerate(graphs):
    subjects = [None] + [node['id'] for node in graph['nodes']]
    subjects += [node['object_uuid'] for node in graph['nodes'] if node['type'] == 'Policy']
    subjects += ['missing-subject', 1]
    for query in QUERIES:
        for subject in subjects:
            outcomes = []
            for function in (before.query_graph, query_graph):
                try:
                    outcomes.append({'digest': digest(function(graph, query, subject))})
                except AppError as error:
                    outcomes.append({'code': error.code, 'message': error.message})
            query_cases += 1
            if outcomes[0] != outcomes[1]:
                query_mismatches.append({'graph': graph_index, 'query': query,
                                         'subject': subject, 'outcomes': outcomes})
receipt['query_cases'] = query_cases
receipt['query_mismatches'] = query_mismatches
print(json.dumps(receipt, indent=2))
sys.exit(bool(mismatches or query_mismatches))

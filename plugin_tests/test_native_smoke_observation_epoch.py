"""Native smoke evidence cannot infer a command failure from a separate probe."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

from intune_iac import provider_execution as pe
from intune_iac.io import AppError

SOURCE=Path(__file__).resolve().parents[1]/'labs/production-lifecycle/native_smoke.py'
spec=importlib.util.spec_from_file_location('epoch_native_smoke',SOURCE)
smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)


class NativeSmokeObservationTests(unittest.TestCase):
    def test_trace_adds_only_fixed_env_value_and_preserves_popen_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);observation={};env={'PATH':'/usr/bin:/bin','TF_INPUT':'0'}
            original_guard=pe._network_guard
            original_popen=pe.subprocess.Popen
            original_handler=signal.getsignal(signal.SIGINT)
            original_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
            caller_mask=original_mask|{signal.SIGUSR1}
            guard_evidence=root/'guard-evidence.json'
            seen={};seen_args=[];guard_calls=[]
            def observed_guard():
                result=original_guard();guard_calls.append(result)
                def child_guard():
                    # Forked child evidence proves the ownership wrapper really
                    # delegates after restoring the caller's signal policy.
                    observed={'pid':os.getpid(),
                              'mask':sorted(int(value) for value in signal.pthread_sigmask(signal.SIG_BLOCK,set())),
                              'original_handler':signal.getsignal(signal.SIGINT) is original_handler}
                    result[0]()
                    observed['original_guard_returned']=True
                    guard_evidence.write_text(json.dumps(observed))
                return child_guard,result[1]
            def observed_popen(*args,**kwargs):
                seen_args.extend(args)
                seen.update(kwargs)
                return original_popen(*args,**kwargs)
            signal.pthread_sigmask(signal.SIG_SETMASK,caller_mask)
            try:
                with patch.object(pe.subprocess,'Popen',side_effect=observed_popen), patch.object(pe,'_network_guard',side_effect=observed_guard):
                    with smoke.observe_supervisor(root,'schema',observation,provider_trace=True):
                        result=pe._supervise([sys.executable,'-I','-S','-c','import os;print(os.environ["TF_LOG_PROVIDER"])'],
                            cwd=root,env=env,executable=sys.executable,pass_fds=())
                self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK,set()),caller_mask)
                self.assertIs(signal.getsignal(signal.SIGINT),original_handler)
            finally:
                signal.signal(signal.SIGINT,original_handler)
                signal.pthread_sigmask(signal.SIG_SETMASK,original_mask)
            self.assertIs(pe._network_guard,original_guard)
            self.assertEqual(env,{'PATH':'/usr/bin:/bin','TF_INPUT':'0'})
            self.assertEqual(seen['env'],env|{'TF_LOG_PROVIDER':'TRACE'})
            self.assertEqual(len(guard_calls),1);self.assertTrue(callable(seen['preexec_fn']))
            observed_guard_state=json.loads(guard_evidence.read_text())
            self.assertNotEqual(observed_guard_state.pop('pid'),os.getpid())
            self.assertEqual(observed_guard_state,{'mask':sorted(int(value) for value in caller_mask),
                'original_handler':True,'original_guard_returned':True})
            self.assertIs(seen['shell'],False)
            self.assertIs(seen['close_fds'],True);self.assertIs(seen['start_new_session'],True)
            self.assertEqual(seen['pass_fds'],());self.assertEqual(seen['executable'],sys.executable)
            self.assertEqual(seen_args,[[sys.executable,'-I','-S','-c','import os;print(os.environ["TF_LOG_PROVIDER"])']])
            self.assertEqual(seen['cwd'],root);self.assertEqual(seen['umask'],0o077)
            self.assertEqual(seen['stdin'],pe.subprocess.DEVNULL)
            self.assertEqual((seen['stdout'],seen['stderr']),(pe.subprocess.PIPE,pe.subprocess.PIPE))
            self.assertEqual(result,{'code':0,'stdout':b'TRACE\n'})
            self.assertEqual(observation['environment_delta'],{'TF_LOG_PROVIDER':'TRACE'})
            self.assertEqual((root/'schema.stderr').stat().st_mode & 0o777,0o600)

    def test_trace_rejects_credentials_or_arbitrary_log_configuration(self):
        for key in ('M365_CLIENT_SECRET','M365_CLIENT_ID','M365_TENANT_ID','M365_AUTH_METHOD','TF_LOG','TF_LOG_PATH','TF_LOG_PROVIDER'):
            with tempfile.TemporaryDirectory() as directory,self.subTest(key=key):
                observation={}
                with self.assertRaises(AppError) as raised:
                    with smoke.observe_supervisor(Path(directory),'schema',observation,provider_trace=True):
                        pe._supervise([sys.executable,'-I','-S','-c','pass'],cwd=directory,
                            env={'PATH':'/usr/bin:/bin',key:'synthetic'},executable=sys.executable,pass_fds=())
                self.assertEqual(raised.exception.code,'lab_trace_environment_rejected')
                self.assertIsNone(observation['exit_code'])

    def test_unix_eperm_requires_specific_observed_socket_operation(self):
        yes=[b'listen unix /tmp/plugin123: socket: operation not permitted',
             b'Error: dial unix /tmp/plugin123: connect: operation not permitted',
             json.dumps({'diagnostics':[{'detail':'plugin failed\nlisten unix /tmp/plugin: bind: operation not permitted\n'}]}).encode()]
        for value in yes:
            with self.subTest(value=value):self.assertTrue(smoke.unix_socket_eperm(b'',value))
        no=[b'provider crashed',b'operation not permitted',b'listen tcp 127.0.0.1: socket: operation not permitted',
            b'listen unix /tmp/plugin: bind: address already in use',b'listen unix /tmp/plugin: bind: permission denied',
            b'listen unix /tmp/plugin: timeout\nunrelated file: operation not permitted']
        for value in no:
            with self.subTest(value=value):self.assertFalse(smoke.unix_socket_eperm(b'',value))

    def test_unrelated_failure_and_incomplete_capture_are_never_skips(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);stdout=root/'stdout';stderr=root/'stderr';stdout.write_bytes(b'');stderr.write_bytes(b'provider crashed')
            observation={'capture_complete':True,'exit_code':1,'stdout':{'path':str(stdout)},'stderr':{'path':str(stderr)}}
            self.assertEqual(smoke.classify_failure('schema','provider_command_failed',observation)['status'],'failed')
            stderr.write_bytes(b'listen unix /tmp/plugin: socket: operation not permitted')
            self.assertEqual(smoke.classify_failure('schema','provider_command_failed',observation)['status'],'blocked')
            for name,code,changes in [('init','provider_command_failed',{}),('schema','provider_schema_pin_mismatch',{}),
                    ('schema','provider_command_failed',{'capture_complete':False}),('schema','provider_command_failed',{'exit_code':0})]:
                with self.subTest(name=name,code=code,changes=changes):
                    self.assertEqual(smoke.classify_failure(name,code,observation|changes)['status'],'failed')

    def test_original_supervisor_dispatch_and_return_preserved_with_real_pipes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);observation={};original=(pe._supervise,pe.os,pe.subprocess)
            # Harmless output-only child; no provider, tenant, file mutation or RPC.
            argv=[sys.executable,'-I','-S','-c','import sys;print("native-out");print("native-err",file=sys.stderr);sys.exit(7)']
            with smoke.observe_supervisor(root,'schema',observation):
                result=pe._supervise(argv,cwd=root,env={'PATH':'/usr/bin:/bin'},executable=sys.executable,pass_fds=())
            self.assertEqual((pe._supervise,pe.os,pe.subprocess),original)
            self.assertEqual(result,{'code':7,'stdout':b'native-out\n'})
            self.assertEqual(observation['argv'],argv);self.assertEqual(observation['exit_code'],7)
            self.assertEqual((root/'schema.stderr').read_bytes(),b'native-err\n')
            self.assertEqual((root/'schema.stdout').read_bytes(),result['stdout'])
            self.assertIs(observation['capture_complete'],True)
            self.assertIs(observation['return_stdout_matches_capture'],True)

    def test_output_limit_preserves_exception_and_bounded_partial_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);observation={};original=(pe._supervise,pe.os,pe.subprocess)
            with self.assertRaises(AppError) as raised:
                with smoke.observe_supervisor(root,'validate',observation,provider_trace=True):
                    pe._supervise([sys.executable,'-I','-S','-c','print("x"*1000)'],cwd=root,
                        env={'PATH':'/usr/bin:/bin'},executable=sys.executable,pass_fds=(),output_limit=32)
            self.assertEqual(raised.exception.code,'provider_process_output_limit')
            self.assertEqual((pe._supervise,pe.os,pe.subprocess),original)
            self.assertIs(observation['capture_complete'],False);self.assertIs(observation['capture_truncated'],True)
            self.assertEqual(sum(observation[x]['bytes'] for x in ('stdout','stderr')),32)


if __name__=='__main__':unittest.main()

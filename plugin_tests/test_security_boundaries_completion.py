"""Hostile model requests must encounter deterministic operator capabilities."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from intune_iac.io import AppError


class CaptureProxyTests(unittest.TestCase):
    def test_ambient_proxy_cannot_change_capture_route(self):
        from intune_iac.capture import GRAPH_ROOT, _http_transport
        selected = []

        def block_connection(address, *args, **kwargs):
            # Observe the real HTTPSConnection route selection, then stop
            # before DNS, external network access, TLS or credential dispatch.
            selected.append(address)
            raise OSError('fixture blocks all external connections')

        hostile = {
            key: 'http://attacker.invalid:8080'
            for key in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY',
                        'http_proxy', 'ALL_PROXY', 'all_proxy')
        }
        hostile.update({'NO_PROXY': '', 'no_proxy': '',
                        'SSL_CERT_FILE': '/nonexistent/hostile-ca.pem',
                        'SSL_CERT_DIR': '/nonexistent/hostile-ca-directory'})
        for environment in ({}, hostile):
            with self.subTest(ambient_proxy=bool(environment)):
                selected.clear()
                with patch.dict(os.environ, environment, clear=True):
                    with patch('socket.create_connection', side_effect=block_connection):
                        with self.assertRaises(AppError) as raised:
                            _http_transport('synthetic-canary')(GRAPH_ROOT, timeout=2)
                self.assertEqual(raised.exception.code, 'identity_transport_unavailable')
                self.assertEqual(selected, [('graph.microsoft.com', 443)])

        # Positive sensitivity control: this same observer must detect a
        # transport that actually consults the hostile proxy environment.
        selected.clear()
        with patch.dict(os.environ, hostile, clear=True):
            with patch('socket.create_connection', side_effect=block_connection):
                with self.assertRaises(urllib.error.URLError):
                    urllib.request.build_opener().open(GRAPH_ROOT, timeout=2)
        self.assertEqual(selected, [('attacker.invalid', 8080)])


class MCPAuthorityTests(unittest.TestCase):
    def test_without_host_capability_no_local_read(self):
        from intune_iac.mcp import call_tool
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)/'plan.json'; target.write_text('{}')
            with self.assertRaises(AppError) as raised:
                call_tool('intune_plan_review', {'input': str(target)})
            self.assertEqual(raised.exception.code, 'filesystem_authority_required')

    def test_hostile_read_write_and_capability_injection(self):
        from intune_iac.mcp import call_tool, FilesystemAuthority
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'project'; root.mkdir()
            outside=Path(td)/'private.json'; outside.write_text('{"secret":"PRIVATE-CANARY"}')
            authority=FilesystemAuthority([root], [root])
            for tool,args in [
                ('intune_plan_review', {'input': str(outside)}),
                ('intune_run_local', {'action':'generate','parameters':{'input':str(root/'in.json'),'context':str(root/'ctx.json'),'output':str(Path(td)/'outside')},'state_dir':str(root/'state')}),
                ('intune_target_compare', {'expected':str(root/'in.json'),'observed':str(root/'../private.json')}),
            ]:
                with self.subTest(tool=tool), self.assertRaises(AppError) as raised:
                    call_tool(tool,args,authority=authority)
                self.assertEqual(raised.exception.code,'filesystem_authority_denied')
            self.assertFalse((Path(td)/'outside').exists())
            with self.assertRaises(AppError):
                call_tool('intune_plan_review', {'input': str(outside), 'read_roots':[td]}, authority=authority)

    def test_legitimate_read_and_read_only_no_state_write(self):
        from intune_iac.mcp import call_tool, FilesystemAuthority
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); target=root/'plan.json'; target.write_text('{}')
            result=call_tool('intune_plan_review',{'input':str(target)},authority=FilesystemAuthority([root],[]))
            self.assertEqual(result['status'],'blocked')  # Parsed incomplete plan, not an authority failure.
            with self.assertRaises(AppError):
                call_tool('intune_run_local',{'action':'inspect','parameters':{'input':str(target),'context':str(target)},'state_dir':str(root/'state')},authority=FilesystemAuthority([root],[]))
            self.assertFalse((root/'state').exists())

    def test_symlink_and_relative_path_denied(self):
        from intune_iac.mcp import call_tool, FilesystemAuthority
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'project';root.mkdir()
            outside=Path(td)/'outside';outside.write_text('{}')
            (root/'link').symlink_to(outside)
            for name in [str(root/'link'),'plan.json']:
                with self.assertRaises(AppError):
                    call_tool('intune_plan_review',{'input':name},authority=FilesystemAuthority([root],[]))

    def test_output_cannot_place_sibling_lock_outside_write_authority(self):
        from intune_iac.mcp import call_tool, FilesystemAuthority
        repo=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'approved-output';output.mkdir()
            journal=Path(td)/'approved-journal';journal.mkdir()
            with self.assertRaises(AppError) as raised:
                call_tool('intune_run_local',{'action':'generate','parameters':{
                    'input':str(repo/'examples/supported/input/export.json'),
                    'context':str(repo/'examples/context.json'),'output':str(output)},
                    'state_dir':str(journal/'attempts')},
                    authority=FilesystemAuthority([repo],[output,journal]))
            self.assertEqual(raised.exception.code,'filesystem_authority_denied')
            self.assertEqual(list(output.iterdir()),[])
            self.assertEqual(list(journal.iterdir()),[])

    def test_initialize_roots_and_environment_cannot_grant_authority(self):
        from intune_iac.mcp import serve
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'secret.json';target.write_text('{"secret":"PRIVATE-CANARY"}')
            messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{'roots':{}},'clientInfo':{'name':'hostile','version':'1'},'read_roots':[td]}},
                      {'jsonrpc':'2.0','method':'notifications/initialized'},
                      {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'intune_plan_review','arguments':{'input':str(target)}}}]
            output=io.StringIO()
            with patch.dict(os.environ,{'INTUNE_READ_ROOTS':td}):
                serve(io.BytesIO(('\n'.join(map(json.dumps,messages))+'\n').encode()),output)
            answer=json.loads(output.getvalue().splitlines()[-1])['result']
            self.assertTrue(answer['isError'])
            self.assertIn('filesystem_authority_required',str(answer))
            self.assertNotIn('PRIVATE-CANARY',output.getvalue())

import hashlib
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('release_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-release-artifact.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ReleaseArtifactTests(unittest.TestCase):
    def archive(self,base,entries,listed=None):
        target=base/'artifact.zip'
        if listed is None:listed={name:hashlib.sha256(data).hexdigest() for name,data,mode in entries}
        with zipfile.ZipFile(target,'w') as bundle:
            for name,data,mode in entries:
                info=zipfile.ZipInfo('project/'+name);info.external_attr=mode<<16;bundle.writestr(info,data)
            info=zipfile.ZipInfo('project/SHA256SUMS');info.external_attr=(stat.S_IFREG|0o644)<<16
            bundle.writestr(info,''.join(value+'  '+name+'\n' for name,value in listed.items()))
        return target

    def test_exact_integrity_and_fresh_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);archive=self.archive(root,[('example.txt',b'contents',stat.S_IFREG|0o644)])
            result=module.verify(archive,hashlib.sha256(archive.read_bytes()).hexdigest(),root/'clean')
            self.assertEqual(result['status'],'PASS');self.assertEqual((root/'clean/project/example.txt').read_bytes(),b'contents')

    def test_paths_modes_and_case_collisions_rejected_before_writes(self):
        variants=[('../outside',b'x',stat.S_IFREG|0o644),('link',b'/etc/passwd',stat.S_IFLNK|0o777),
                  ('CON.txt',b'x',stat.S_IFREG|0o644),('a\\b',b'x',stat.S_IFREG|0o644)]
        for entry in variants:
            with self.subTest(name=entry[0]),tempfile.TemporaryDirectory() as td:
                root=Path(td);archive=self.archive(root,[entry])
                with self.assertRaises(ValueError):module.verify(archive,destination=root/'clean')
                self.assertFalse((root/'clean').exists())
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);archive=self.archive(root,[('Name',b'a',stat.S_IFREG|0o644),('name',b'b',stat.S_IFREG|0o644)])
            with self.assertRaises(ValueError):module.verify(archive)

    def test_unlisted_member_or_wrong_manifest_digest_rejected(self):
        for listed in ({},{'example.txt':'0'*64}):
            with self.subTest(listed=listed),tempfile.TemporaryDirectory() as td:
                archive=self.archive(Path(td),[('example.txt',b'contents',stat.S_IFREG|0o644)],listed)
                with self.assertRaises(ValueError):module.verify(archive)

    def test_wrong_archive_hash_and_existing_destination_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);archive=self.archive(root,[('example.txt',b'contents',stat.S_IFREG|0o644)])
            with self.assertRaises(ValueError):module.verify(archive,'0'*64)
            destination=root/'existing';destination.mkdir();keep=destination/'keep';keep.write_text('preserve')
            with self.assertRaises(ValueError):module.verify(archive,destination=destination)
            self.assertEqual(keep.read_text(),'preserve')


if __name__=='__main__':unittest.main()

"""Compound native-boundary cleanup contracts; recorded APIs, not native proof."""
import unittest
from intune_iac.io import AppError
from intune_iac import windows_storage as storage, windows_directory as directory
from plugin_tests.test_windows_storage_r4 import RecordedStorage, ROOT
from plugin_tests.test_windows_directory_r4 import RecordedAPI


class CleanupTests(unittest.TestCase):
    def test_file_cleanup_preserves_original_error_through_every_secondary_kind(self):
        for cleanup in (RuntimeError('close'),KeyboardInterrupt(),SystemExit(7)):
            class API:
                def close(self,handle):raise cleanup
            primary=AppError('primary','retain')
            try:
                with storage._owned_handle(API(),9):raise primary
            except BaseException as observed:self.assertIs(observed,primary)
            else:self.fail('primary disappeared')

    def test_directory_cleanup_attempts_every_handle_and_preserves_primary(self):
        for cleanup in (RuntimeError('close'),KeyboardInterrupt(),SystemExit(7)):
            api=RecordedAPI();closed=[]
            def close(handle):closed.append(handle);raise cleanup
            api.close=close;primary=AppError('primary','retain')
            try:
                with directory._pin(ROOT,api):raise primary
            except BaseException as observed:self.assertIs(observed,primary)
            else:self.fail('primary disappeared')
            self.assertEqual(closed,[3,2,1])

    def test_directory_lone_cleanup_cancellation_survives_after_all_close_attempts(self):
        for cleanup in (KeyboardInterrupt(),SystemExit(7)):
            api=RecordedAPI();closed=[]
            def close(handle):closed.append(handle);raise cleanup
            api.close=close
            try:
                with directory._pin(ROOT,api):pass
            except BaseException as observed:self.assertIs(observed,cleanup)
            else:self.fail('cancellation disappeared')
            self.assertEqual(closed,[3,2,1])

    def test_named_lock_release_does_not_mask_primary_and_still_closes_all_handles(self):
        for cleanup in (RuntimeError('unlock'),KeyboardInterrupt(),SystemExit(7)):
            api=RecordedStorage();original=api.unlock
            def unlock(handle,overlap):original(handle,overlap);raise cleanup
            api.unlock=unlock;primary=AppError('primary','retain')
            try:
                with storage._lock(ROOT,'qualification.lock',api):raise primary
            except BaseException as observed:self.assertIs(observed,primary)
            else:self.fail('primary disappeared')
            self.assertEqual(api.handles,{})

    def test_lone_file_cleanup_cancellation_is_not_success(self):
        for cleanup in (KeyboardInterrupt(),SystemExit(7)):
            class API:
                def close(self,handle):raise cleanup
            try:
                with storage._owned_handle(API(),9):pass
            except BaseException as observed:self.assertIs(observed,cleanup)
            else:self.fail('cancellation disappeared')


if __name__=='__main__':unittest.main()

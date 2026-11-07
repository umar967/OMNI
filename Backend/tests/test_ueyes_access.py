import unittest
from unittest.mock import Mock
from Backend.research.ueyes_selective import RangeAccess, SIZE, LIMIT


class Response:
    def __init__(self, status=206, etag='"stable"'):
        self.code=status
        self.headers={'Content-Range':f'bytes 0-0/{SIZE}','Content-Length':'1'}
        if etag is not None:
            self.headers['ETag']=etag
        self.read=Mock(return_value=b'P')
    def __enter__(self): return self
    def __exit__(self,*args): pass


class UEyesAccessTests(unittest.TestCase):
    def test_valid_one_byte_probe(self):
        response=Response()
        client=RangeAccess(Mock(open=Mock(return_value=response)))
        self.assertEqual(client.read(0,0),b'P')
        self.assertEqual(client.received,1)

    def test_full_response_or_missing_identity_never_reads_body(self):
        for response in (Response(status=200),Response(etag=None),Response(etag='W/"weak"')):
            client=RangeAccess(Mock(open=Mock(return_value=response)))
            with self.assertRaises(ValueError): client.read(0,0)
            response.read.assert_not_called()

    def test_bad_range_and_identity_change_stop(self):
        response=Response()
        response.headers['Content-Range']='bytes 0-0/999'
        client=RangeAccess(Mock(open=Mock(return_value=response)))
        with self.assertRaises(ValueError): client.read(0,0)
        response.read.assert_not_called()
        response=Response()
        client=RangeAccess(Mock(open=Mock(return_value=response)))
        client.etag='"different"'
        with self.assertRaises(ValueError): client.read(0,0)
        response.read.assert_not_called()

    def test_budget_exhaustion_prevents_network_request(self):
        opener=Mock()
        client=RangeAccess(opener)
        client.received=LIMIT
        with self.assertRaises(ValueError): client.read(0,0)
        opener.open.assert_not_called()

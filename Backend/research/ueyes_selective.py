"""Strict UEyes range probe. No retries, automatic redirects or full-body fallback."""
import hashlib
import json
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

LIMIT = 26_214_400
SIZE = 12_912_746_325
URL = 'https://zenodo.org/records/8010312/files/UEyes_dataset.zip?download=1'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RangeAccess:
    def __init__(self, opener=None):
        self.opener = opener or build_opener(NoRedirect())
        self.received = 0
        self.charged = 0
        self.requests = []
        self.etag = None

    def read(self, start, end):
        length = end-start+1
        if not 0 <= start <= end < SIZE or length > LIMIT-max(self.received,self.charged):
            raise ValueError('Range exceeds archive or remaining payload budget')
        headers = {'Range':f'bytes={start}-{end}', 'Accept-Encoding':'identity',
                   'User-Agent':'OMNI-UEyes-approved-selective-audit/1'}
        if self.etag:
            headers['If-Match'] = self.etag
        request = Request(URL, headers=headers)
        try:
            response = self.opener.open(request, timeout=25)
        except HTTPError as exc:
            response = exc  # Never follow redirects or retry an error response.
        with response:
            record = {'url':URL,'range':headers['Range'],'status':response.code,
                      'headers':{k:v for k,v in response.headers.items() if k.lower() in
                          ('content-range','content-length','content-type','content-disposition',
                           'etag','last-modified','accept-ranges','date','server')},'payload_bytes_read':0}
            self.requests.append(record)
            # Validate before reading. Unexpected bodies are closed immediately,
            # rather than consuming a possibly enormous error/full-archive body.
            if response.code != 206:
                raise ValueError(f'Range unsupported/unverified: HTTP {response.code}; body refused')
            expected = f'bytes {start}-{end}/{SIZE}'
            if response.headers.get('Content-Range') != expected:
                raise ValueError('Incorrect Content-Range; body refused')
            if response.headers.get('Content-Length') != str(length):
                raise ValueError('Incorrect/missing Content-Length; body refused')
            self.charged += length  # Charge even a refused body's possible buffering.
            if response.headers.get('Content-Encoding', 'identity') != 'identity':
                raise ValueError('Unexpected encoding; body refused')
            etag = response.headers.get('ETag')
            if not etag or etag.startswith('W/') or (self.etag and etag != self.etag):
                raise ValueError('Missing, weak or changed content identity; body refused')
            self.etag = etag
            chunks=[]
            remaining=length
            while remaining:
                block=response.read(min(65536,remaining))
                self.received += len(block)
                record['payload_bytes_read'] += len(block)
                if not block:
                    raise ValueError('Truncated range response')
                chunks.append(block)
                remaining-=len(block)
            payload=b''.join(chunks)
            record['sha256']=hashlib.sha256(payload).hexdigest()
            return payload


def main():
    access=RangeAccess()
    result={'experiment':'approved-selective-ueyes-b2a','download_limit':LIMIT,
            'extraction_limit':536_870_912,'expected_archive_bytes':SIZE,
            'published_md5':'c2d53e6af0a47e1f459416d6839ec2c1','archive_md5_verified':False,
            'extracted_bytes':0,'verdict':'partial inspection only'}
    try:
        access.read(0,0)
        result['range_probe_verified']=True
    except Exception as exc:
        result.update(verdict='partial inspection only',stop_reason=type(exc).__name__+': '+str(exc))
    result.update(downloaded_payload_bytes=access.received,budget_charge_bytes=access.charged,
        response_payload_upper_bound_bytes=access.charged,requests=access.requests,
        accounting='Charge the entire declared payload of validated range responses, even if refused before reading. '
                   'Application body bytes are counted separately. No retries/redirects; this is payload accounting, not TLS wire overhead.')
    destination=Path(__file__).with_name('ueyes_b2a_access.json')
    destination.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
